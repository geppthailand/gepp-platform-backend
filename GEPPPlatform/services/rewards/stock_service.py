"""
Stock Service - Inventory ledger for reward catalog items
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...models.rewards.management import RewardCampaign
from ...exceptions import NotFoundException, BadRequestException


class StockService:
    def __init__(self, db: Session):
        self.db = db

    def _stock_to_dict(self, item: RewardStock) -> dict:
        return {
            "id": item.id,
            "reward_catalog_id": item.reward_catalog_id,
            "values": item.values,
            "reward_campaign_id": item.reward_campaign_id,
            "note": item.note,
            "reward_user_id": item.reward_user_id,
            "user_location_id": item.user_location_id,
            "created_date": item.created_date.isoformat() if item.created_date else None,
        }

    def get_summary(self, organization_id: int) -> list[dict]:
        """For each catalog item in org, return total stock."""
        results = (
            self.db.query(
                RewardCatalog.id,
                RewardCatalog.name,
                RewardCatalog.unit,
                func.coalesce(func.sum(RewardStock.values), 0).label("total_stock"),
            )
            .outerjoin(
                RewardStock,
                (RewardStock.reward_catalog_id == RewardCatalog.id)
                & (RewardStock.deleted_date.is_(None)),
            )
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
            .group_by(RewardCatalog.id, RewardCatalog.name, RewardCatalog.unit)
            .order_by(RewardCatalog.id.desc())
            .all()
        )

        return [
            {
                "catalog_id": row.id,
                "name": row.name,
                "unit": row.unit,
                "total_stock": int(row.total_stock),
            }
            for row in results
        ]

    def get_ledger(self, catalog_id: int, campaign_id: int = None) -> list[dict]:
        """Return all stock records for a catalog item, optionally filtered by campaign."""
        catalog = (
            self.db.query(RewardCatalog)
            .filter(RewardCatalog.id == catalog_id, RewardCatalog.deleted_date.is_(None))
            .first()
        )
        if not catalog:
            raise NotFoundException("Catalog item not found")

        query = (
            self.db.query(RewardStock)
            .filter(
                RewardStock.reward_catalog_id == catalog_id,
                RewardStock.deleted_date.is_(None),
            )
        )

        if campaign_id is not None:
            query = query.filter(RewardStock.reward_campaign_id == campaign_id)

        items = query.order_by(RewardStock.created_date.desc()).all()
        return [self._stock_to_dict(i) for i in items]

    def deposit_or_withdraw(self, data: dict, organization_id: int = None) -> dict:
        """Create a stock ledger entry. Positive values = deposit, negative = withdraw."""
        catalog_id = data.get("reward_catalog_id")
        values = data.get("values")

        if catalog_id is None or values is None:
            raise BadRequestException("reward_catalog_id and values are required")

        query = self.db.query(RewardCatalog).filter(
            RewardCatalog.id == catalog_id, RewardCatalog.deleted_date.is_(None)
        )
        if organization_id is not None:
            query = query.filter(RewardCatalog.organization_id == organization_id)
        catalog = query.first()
        if not catalog:
            raise NotFoundException("Catalog item not found or not in your organization")

        # For withdrawals, verify sufficient stock
        if values < 0:
            current_stock = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == catalog_id,
                    RewardStock.deleted_date.is_(None),
                )
                .scalar()
            )
            if int(current_stock) < abs(values):
                raise BadRequestException(
                    f"Insufficient stock. Current: {int(current_stock)}, requested withdraw: {abs(values)}"
                )

        item = RewardStock(
            reward_catalog_id=catalog_id,
            values=values,
            reward_campaign_id=data.get("reward_campaign_id"),
            note=data.get("note"),
            reward_user_id=data.get("reward_user_id"),
            user_location_id=data.get("user_location_id"),
        )
        self.db.add(item)
        self.db.flush()

        return self._stock_to_dict(item)
