"""
Catalog Service - Master reward items available for redemption
"""

from __future__ import annotations  # required: list() method shadows built-in list

from datetime import datetime, timezone
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.catalog import RewardCatalog, RewardCatalogCategory, RewardStock
from ...exceptions import NotFoundException, BadRequestException


class CatalogService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCatalog, category_name: str | None = None) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "thumbnail_id": item.thumbnail_id,
            "images": item.images,
            "price": float(item.price) if item.price is not None else None,
            "cost_baht": float(item.cost_baht) if item.cost_baht is not None else None,
            "unit": item.unit,
            "category_id": item.category_id,
            "category_name": category_name,
            "min_threshold": item.min_threshold or 0,
            "limit_per_user_per_campaign": item.limit_per_user_per_campaign,
            "status": item.status,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }

    def list(self, organization_id: int, include_archived: bool = True) -> list[dict]:
        """Return catalog items for an organization with category name joined."""
        q = (
            self.db.query(RewardCatalog, RewardCatalogCategory.name)
            .outerjoin(
                RewardCatalogCategory,
                RewardCatalogCategory.id == RewardCatalog.category_id,
            )
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
        )
        if not include_archived:
            q = q.filter(RewardCatalog.status == "active")

        rows = q.order_by(RewardCatalog.id.desc()).all()
        return [self._to_dict(item, cat_name) for item, cat_name in rows]

    def create(self, organization_id: int, data: dict) -> dict:
        if not data.get("name"):
            raise BadRequestException("Name is required")

        item = RewardCatalog(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            thumbnail_id=data.get("thumbnail_id"),
            images=data.get("images"),
            price=data.get("price"),
            cost_baht=data.get("cost_baht"),
            unit=data.get("unit"),
            category_id=data.get("category_id"),
            min_threshold=data.get("min_threshold") or 0,
            limit_per_user_per_campaign=data.get("limit_per_user_per_campaign"),
            status=data.get("status") or "active",
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        item = (
            self.db.query(RewardCatalog)
            .filter(RewardCatalog.id == id, RewardCatalog.deleted_date.is_(None))
            .first()
        )
        if not item:
            raise NotFoundException("Catalog item not found")

        editable = (
            "name", "description", "thumbnail_id", "images",
            "price", "cost_baht", "unit",
            "category_id", "min_threshold", "limit_per_user_per_campaign", "status",
        )
        for field in editable:
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a catalog item (hard remove from listing)."""
        item = (
            self.db.query(RewardCatalog)
            .filter(RewardCatalog.id == id, RewardCatalog.deleted_date.is_(None))
            .first()
        )
        if not item:
            raise NotFoundException("Catalog item not found")
        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}

    # ── Archive flow ──────────────────────────────────────────────────────

    def archive_check(self, id: int, organization_id: int) -> dict:
        """Check remaining stock before archiving — does NOT modify data.
        Returns: { has_remaining_stock, global_stock, campaign_stocks: [{campaign_id, campaign_name, remaining}] }
        """
        from ...models.rewards.management import RewardCampaign  # avoid circular

        item = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.id == id,
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Catalog item not found")

        global_stock = int(
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .filter(
                RewardStock.reward_catalog_id == id,
                RewardStock.reward_campaign_id.is_(None),
                RewardStock.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        # Per-campaign remaining stock
        campaign_rows = (
            self.db.query(
                RewardStock.reward_campaign_id,
                RewardCampaign.name,
                func.coalesce(func.sum(RewardStock.values), 0).label("remaining"),
            )
            .join(RewardCampaign, RewardCampaign.id == RewardStock.reward_campaign_id)
            .filter(
                RewardStock.reward_catalog_id == id,
                RewardStock.reward_campaign_id.isnot(None),
                RewardStock.deleted_date.is_(None),
            )
            .group_by(RewardStock.reward_campaign_id, RewardCampaign.name)
            .having(func.sum(RewardStock.values) > 0)
            .all()
        )
        campaign_stocks = [
            {"campaign_id": cid, "campaign_name": cname, "remaining": int(rem)}
            for cid, cname, rem in campaign_rows
        ]

        has_remaining = global_stock > 0 or any(c["remaining"] > 0 for c in campaign_stocks)
        return {
            "catalog_id": id,
            "has_remaining_stock": has_remaining,
            "global_stock": global_stock,
            "campaign_stocks": campaign_stocks,
        }

    def archive_confirm(
        self,
        id: int,
        organization_id: int,
        return_to_global: bool,
        admin_user_id: int | None = None,
    ) -> dict:
        """Archive the catalog item.
        If return_to_global=True, create 'return' ledger entries moving all campaign stock back to Global first.
        """
        check = self.archive_check(id, organization_id)
        item = (
            self.db.query(RewardCatalog)
            .filter(RewardCatalog.id == id, RewardCatalog.deleted_date.is_(None))
            .first()
        )

        if return_to_global and check["has_remaining_stock"]:
            for c in check["campaign_stocks"]:
                qty = c["remaining"]
                if qty <= 0:
                    continue
                group_id = uuid.uuid4()
                # Remove from campaign
                out_row = RewardStock(
                    reward_catalog_id=id,
                    values=-qty,
                    reward_campaign_id=c["campaign_id"],
                    ledger_type="return",
                    transfer_group_id=group_id,
                    note=f"[return to global] archive item #{id}",
                    admin_user_id=admin_user_id,
                )
                # Add to global
                in_row = RewardStock(
                    reward_catalog_id=id,
                    values=qty,
                    reward_campaign_id=None,
                    ledger_type="return",
                    transfer_group_id=group_id,
                    note=f"[return to global] archive item #{id}",
                    admin_user_id=admin_user_id,
                )
                self.db.add(out_row)
                self.db.add(in_row)

        item.status = "archived"
        self.db.flush()
        return {
            "id": id,
            "status": "archived",
            "returned_to_global": return_to_global and check["has_remaining_stock"],
        }
