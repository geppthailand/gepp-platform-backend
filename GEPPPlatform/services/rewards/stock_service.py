"""
Stock Service - Inventory ledger for reward catalog items
"""

from __future__ import annotations  # needed: method names shadow built-ins

from datetime import datetime, timezone
import uuid

from sqlalchemy import func, and_, or_, case
from sqlalchemy.orm import Session

from ...models.rewards.catalog import RewardCatalog, RewardCatalogCategory, RewardStock
from ...models.rewards.management import RewardCampaign
from ...exceptions import NotFoundException, BadRequestException


class StockService:
    def __init__(self, db: Session):
        self.db = db

    # ── FIFO lot tracking ──────────────────────────────────────────────────

    def compute_lots(self, catalog_id: int) -> list[dict]:
        """Compute FIFO lots for a catalog item.
        Each deposit row = a lot. Real outflows (redeem + withdraw) consume oldest lot first.
        Transfer + return = internal moves, don't consume lots.

        Returns [{id, created_date, original_qty, unit_price, total_price, vendor,
                  remaining_qty, is_active}] ordered oldest → newest.
        """
        deposits = (
            self.db.query(RewardStock)
            .filter(
                RewardStock.reward_catalog_id == catalog_id,
                RewardStock.ledger_type == "deposit",
                RewardStock.values > 0,
                RewardStock.deleted_date.is_(None),
            )
            .order_by(RewardStock.created_date.asc(), RewardStock.id.asc())
            .all()
        )

        total_outflow = int(
            self.db.query(func.coalesce(func.sum(-RewardStock.values), 0))
            .filter(
                RewardStock.reward_catalog_id == catalog_id,
                RewardStock.ledger_type.in_(["redeem", "withdraw"]),
                RewardStock.values < 0,
                RewardStock.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        lots: list[dict] = []
        remaining_outflow = total_outflow
        for d in deposits:
            original = int(d.values)
            consumed = min(original, remaining_outflow)
            remaining_outflow -= consumed
            remaining_qty = original - consumed
            lots.append({
                "id": d.id,
                "created_date": d.created_date.isoformat() if d.created_date else None,
                "original_qty": original,
                "remaining_qty": remaining_qty,
                "unit_price": float(d.unit_price) if d.unit_price is not None else None,
                "total_price": float(d.total_price) if d.total_price is not None else None,
                "vendor": d.vendor,
                "receipt_file_id": d.receipt_file_id,
                "is_active": remaining_qty > 0,
            })
        return lots

    def get_cost_stats(self, catalog_id: int) -> dict:
        """Derive cost stats from FIFO lots — weighted avg of active lots + last deposit's unit_price."""
        lots = self.compute_lots(catalog_id)
        active = [l for l in lots if l["is_active"] and l["unit_price"] is not None]

        # Weighted average = SUM(remaining × unit_price) / SUM(remaining)
        total_val = sum(l["remaining_qty"] * (l["unit_price"] or 0) for l in active)
        total_qty = sum(l["remaining_qty"] for l in active)
        avg_cost = (total_val / total_qty) if total_qty > 0 else None

        # Last deposit (regardless of whether lot is active)
        priced = [l for l in lots if l["unit_price"] is not None]
        last = priced[-1] if priced else None

        return {
            "avg_unit_cost": avg_cost,
            "last_unit_cost": last["unit_price"] if last else None,
            "last_deposit_date": last["created_date"] if last else None,
            "current_inventory_value_baht": total_val,  # valid even if some units have no price (contributes 0)
        }

    def _stock_to_dict(self, item: RewardStock) -> dict:
        return {
            "id": item.id,
            "reward_catalog_id": item.reward_catalog_id,
            "values": item.values,
            "reward_campaign_id": item.reward_campaign_id,
            "note": item.note,
            "reward_user_id": item.reward_user_id,
            "user_location_id": item.user_location_id,
            "ledger_type": item.ledger_type,
            "transfer_group_id": str(item.transfer_group_id) if item.transfer_group_id else None,
            "vendor": item.vendor,
            "unit_price": float(item.unit_price) if item.unit_price is not None else None,
            "total_price": float(item.total_price) if item.total_price is not None else None,
            "receipt_file_id": item.receipt_file_id,
            "admin_user_id": item.admin_user_id,
            "created_date": item.created_date.isoformat() if item.created_date else None,
        }

    # ── Summary ─────────────────────────────────────────────────────────────

    def get_summary(self, organization_id: int, include_archived: bool = True) -> list[dict]:
        """For each catalog item in org: catalog fields + total + global + assigned + per-campaign breakdown + threshold flag."""
        q = (
            self.db.query(RewardCatalog, RewardCatalogCategory.name.label("category_name"))
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

        result = []
        for c, cat_name in rows:
            global_stock = int(
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == c.id,
                    RewardStock.reward_campaign_id.is_(None),
                    RewardStock.deleted_date.is_(None),
                )
                .scalar() or 0
            )

            # Per-campaign breakdown: assigned (sum of positive transfer ins + negative outs),
            # redeemed (sum of negative redeem rows), remaining = sum(all rows for that campaign).
            breakdown = []
            rows = (
                self.db.query(
                    RewardStock.reward_campaign_id,
                    RewardCampaign.name,
                    func.coalesce(
                        func.sum(func.greatest(RewardStock.values, 0)), 0
                    ).label("assigned_in"),
                    func.coalesce(
                        func.sum(
                            case((RewardStock.ledger_type == "redeem", -RewardStock.values), else_=0)
                        ), 0
                    ).label("redeemed"),
                    func.coalesce(func.sum(RewardStock.values), 0).label("remaining"),
                )
                .join(RewardCampaign, RewardCampaign.id == RewardStock.reward_campaign_id)
                .filter(
                    RewardStock.reward_catalog_id == c.id,
                    RewardStock.reward_campaign_id.isnot(None),
                    RewardStock.deleted_date.is_(None),
                )
                .group_by(RewardStock.reward_campaign_id, RewardCampaign.name)
                .all()
            )
            for cid, cname, assigned_in, redeemed, remaining in rows:
                # Skip empty (never had any activity)
                if int(assigned_in) == 0 and int(redeemed) == 0:
                    continue
                breakdown.append({
                    "campaign_id": cid,
                    "campaign_name": cname,
                    "assigned": int(assigned_in),
                    "redeemed": int(redeemed),
                    "remaining": int(remaining),
                })

            assigned_stock = sum(b["remaining"] for b in breakdown)
            total_stock = global_stock + assigned_stock
            min_thr = c.min_threshold or 0

            # FIFO cost stats (avg, last, inventory value)
            cost = self.get_cost_stats(c.id)

            result.append({
                # Catalog fields (for table rendering)
                "catalog_id": c.id,
                "name": c.name,
                "description": c.description,
                "thumbnail_id": c.thumbnail_id,
                "price": float(c.price) if c.price is not None else None,
                "cost_baht": float(c.cost_baht) if c.cost_baht is not None else None,  # legacy, unused in UI
                "unit": c.unit,
                "category_id": c.category_id,
                "category_name": cat_name,
                "min_threshold": min_thr,
                "limit_per_user_per_campaign": c.limit_per_user_per_campaign,
                "status": c.status,
                # Stock stats
                "total_stock": total_stock,
                "global_stock": global_stock,
                "assigned_stock": assigned_stock,
                "is_below_threshold": min_thr > 0 and total_stock < min_thr,
                "campaign_breakdown": breakdown,
                # FIFO cost stats
                "avg_unit_cost": cost["avg_unit_cost"],
                "last_unit_cost": cost["last_unit_cost"],
                "last_deposit_date": cost["last_deposit_date"],
                "current_inventory_value_baht": cost["current_inventory_value_baht"],
            })
        return result

    def get_ledger(self, catalog_id: int, campaign_id: int | None = None) -> list[dict]:
        """Legacy: all ledger rows for a single catalog item (optionally by campaign)."""
        catalog = (
            self.db.query(RewardCatalog)
            .filter(RewardCatalog.id == catalog_id, RewardCatalog.deleted_date.is_(None))
            .first()
        )
        if not catalog:
            raise NotFoundException("Catalog item not found")

        q = self.db.query(RewardStock).filter(
            RewardStock.reward_catalog_id == catalog_id,
            RewardStock.deleted_date.is_(None),
        )
        if campaign_id is not None:
            q = q.filter(RewardStock.reward_campaign_id == campaign_id)
        items = q.order_by(RewardStock.created_date.desc()).all()
        return [self._stock_to_dict(i) for i in items]

    # ── Mutations ───────────────────────────────────────────────────────────

    def deposit(self, data: dict, organization_id: int, admin_user_id: int | None = None) -> dict:
        """Create a deposit ledger entry (into Global pool by default, or direct into a campaign).
        Optional receipt: vendor, unit_price, total_price, receipt_file_id.
        """
        catalog_id = data.get("reward_catalog_id")
        quantity = data.get("quantity") or data.get("values")
        if catalog_id is None or quantity is None:
            raise BadRequestException("reward_catalog_id and quantity are required")
        if int(quantity) <= 0:
            raise BadRequestException("quantity must be positive")

        catalog = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.id == catalog_id,
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not catalog:
            raise NotFoundException("Catalog item not found in your organization")
        if catalog.status == "archived":
            raise BadRequestException("Cannot deposit stock to an archived item")

        row = RewardStock(
            reward_catalog_id=catalog_id,
            values=int(quantity),
            reward_campaign_id=data.get("reward_campaign_id"),  # None = Global
            ledger_type="deposit",
            note=data.get("note"),
            vendor=data.get("vendor"),
            unit_price=data.get("unit_price"),
            total_price=data.get("total_price"),
            receipt_file_id=data.get("receipt_file_id"),
            admin_user_id=admin_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return self._stock_to_dict(row)

    def transfer(self, data: dict, organization_id: int, admin_user_id: int | None = None) -> dict:
        """Move stock between Global pool and a campaign.
        from/to: 'global' or {'campaign_id': int}
        Direct Campaign→Campaign transfers are blocked.
        """
        catalog_id = data.get("reward_catalog_id")
        from_src = data.get("from")
        to_src = data.get("to")
        quantity = int(data.get("quantity") or 0)
        note = data.get("note")

        if catalog_id is None or from_src is None or to_src is None or quantity <= 0:
            raise BadRequestException("reward_catalog_id, from, to, and positive quantity are required")

        def _parse(src):
            if src == "global" or src is None or src == {}:
                return None
            if isinstance(src, dict) and "campaign_id" in src:
                return int(src["campaign_id"])
            if isinstance(src, (int, str)) and str(src).isdigit():
                return int(src)
            raise BadRequestException(f"Invalid source: {src}")

        from_campaign = _parse(from_src)
        to_campaign = _parse(to_src)

        if from_campaign == to_campaign:
            raise BadRequestException("From and To cannot be the same")
        if from_campaign is not None and to_campaign is not None:
            raise BadRequestException(
                "Direct Campaign→Campaign transfer is not allowed. Route through Global pool."
            )

        # Verify ownership
        catalog = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.id == catalog_id,
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not catalog:
            raise NotFoundException("Catalog item not found in your organization")

        # Verify sufficient stock at source
        source_filter = (
            RewardStock.reward_campaign_id.is_(None)
            if from_campaign is None
            else RewardStock.reward_campaign_id == from_campaign
        )
        source_stock = int(
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .filter(
                RewardStock.reward_catalog_id == catalog_id,
                source_filter,
                RewardStock.deleted_date.is_(None),
            )
            .scalar() or 0
        )
        if source_stock < quantity:
            src_label = "Global" if from_campaign is None else f"campaign #{from_campaign}"
            raise BadRequestException(
                f"Insufficient stock in {src_label}: {source_stock} available, {quantity} requested"
            )

        group_id = uuid.uuid4()
        out_row = RewardStock(
            reward_catalog_id=catalog_id,
            values=-quantity,
            reward_campaign_id=from_campaign,
            ledger_type="transfer",
            transfer_group_id=group_id,
            note=f"[transfer out] {note or ''}".strip(),
            admin_user_id=admin_user_id,
        )
        in_row = RewardStock(
            reward_catalog_id=catalog_id,
            values=quantity,
            reward_campaign_id=to_campaign,
            ledger_type="transfer",
            transfer_group_id=group_id,
            note=f"[transfer in] {note or ''}".strip(),
            admin_user_id=admin_user_id,
        )
        self.db.add(out_row)
        self.db.add(in_row)
        self.db.flush()

        return {
            "catalog_id": catalog_id,
            "from_campaign_id": from_campaign,
            "to_campaign_id": to_campaign,
            "quantity": quantity,
            "transfer_group_id": str(group_id),
        }

    # Legacy method — kept for backward compat with existing callers
    def deposit_or_withdraw(self, data: dict, organization_id: int = None) -> dict:
        """Legacy: positive=deposit, negative=withdraw. Prefer deposit() / transfer()."""
        catalog_id = data.get("reward_catalog_id")
        values = data.get("values")
        if catalog_id is None or values is None:
            raise BadRequestException("reward_catalog_id and values are required")

        q = self.db.query(RewardCatalog).filter(
            RewardCatalog.id == catalog_id, RewardCatalog.deleted_date.is_(None)
        )
        if organization_id is not None:
            q = q.filter(RewardCatalog.organization_id == organization_id)
        catalog = q.first()
        if not catalog:
            raise NotFoundException("Catalog item not found or not in your organization")

        if values < 0:
            current_stock = int(
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == catalog_id,
                    RewardStock.deleted_date.is_(None),
                )
                .scalar() or 0
            )
            if current_stock < abs(values):
                raise BadRequestException(
                    f"Insufficient stock. Current: {current_stock}, requested withdraw: {abs(values)}"
                )

        item = RewardStock(
            reward_catalog_id=catalog_id,
            values=values,
            reward_campaign_id=data.get("reward_campaign_id"),
            ledger_type="deposit" if values > 0 else "withdraw",
            note=data.get("note"),
            reward_user_id=data.get("reward_user_id"),
            user_location_id=data.get("user_location_id"),
        )
        self.db.add(item)
        self.db.flush()
        return self._stock_to_dict(item)

    def assign_to_campaign(self, data: dict, organization_id: int = None) -> dict:
        """Legacy wrapper — delegates to transfer(global → campaign)."""
        return self.transfer(
            {
                "reward_catalog_id": data.get("reward_catalog_id"),
                "from": "global",
                "to": {"campaign_id": data.get("reward_campaign_id")},
                "quantity": data.get("values"),
                "note": data.get("note"),
            },
            organization_id=organization_id,
        )

    # ── KPIs ────────────────────────────────────────────────────────────────

    def get_inventory_kpis(self, organization_id: int) -> dict:
        """Aggregate KPIs for Inventory dashboard."""
        active_items = (
            self.db.query(func.count(RewardCatalog.id))
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
                RewardCatalog.status == "active",
            )
            .scalar() or 0
        )
        archived_items = (
            self.db.query(func.count(RewardCatalog.id))
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
                RewardCatalog.status == "archived",
            )
            .scalar() or 0
        )

        # Sum of all stock for this org's catalogs
        global_pool = int(
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .join(RewardCatalog, RewardCatalog.id == RewardStock.reward_catalog_id)
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
                RewardStock.reward_campaign_id.is_(None),
                RewardStock.deleted_date.is_(None),
            )
            .scalar() or 0
        )
        in_campaigns = int(
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .join(RewardCatalog, RewardCatalog.id == RewardStock.reward_catalog_id)
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
                RewardStock.reward_campaign_id.isnot(None),
                RewardStock.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        campaign_count = int(
            self.db.query(func.count(func.distinct(RewardStock.reward_campaign_id)))
            .join(RewardCatalog, RewardCatalog.id == RewardStock.reward_catalog_id)
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
                RewardStock.reward_campaign_id.isnot(None),
                RewardStock.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        # Low stock count + total inventory value (FIFO-based)
        summary = self.get_summary(organization_id, include_archived=False)
        low_stock_count = sum(1 for s in summary if s["is_below_threshold"])
        # Total value: GAAP-style current inventory = SUM across items of (active lots × unit_price)
        total_value = float(sum(s.get("current_inventory_value_baht") or 0 for s in summary))

        return {
            "total_items": active_items,
            "archived_items": archived_items,
            "total_pieces": global_pool + in_campaigns,
            "global_pool": global_pool,
            "in_campaigns": in_campaigns,
            "campaign_count": campaign_count,
            "low_stock_count": low_stock_count,
            "total_value_baht": total_value,
        }

    # ── Ledger query with filters ──────────────────────────────────────────

    def list_ledger(self, organization_id: int, filters: dict) -> dict:
        """Paginated ledger query with multi-filter support."""
        page = max(1, int(filters.get("page") or 1))
        page_size = max(1, min(200, int(filters.get("page_size") or 20)))
        offset = (page - 1) * page_size

        q = (
            self.db.query(RewardStock, RewardCatalog.name.label("catalog_name"), RewardCampaign.name.label("campaign_name"))
            .join(RewardCatalog, RewardCatalog.id == RewardStock.reward_catalog_id)
            .outerjoin(RewardCampaign, RewardCampaign.id == RewardStock.reward_campaign_id)
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardStock.deleted_date.is_(None),
            )
        )

        if filters.get("catalog_id"):
            q = q.filter(RewardStock.reward_catalog_id == int(filters["catalog_id"]))
        if filters.get("campaign_id"):
            q = q.filter(RewardStock.reward_campaign_id == int(filters["campaign_id"]))
        types = filters.get("types")
        if types:
            if isinstance(types, str):
                types = [t.strip() for t in types.split(",") if t.strip()]
            if types:
                q = q.filter(RewardStock.ledger_type.in_(types))
        if filters.get("date_from"):
            q = q.filter(RewardStock.created_date >= filters["date_from"])
        if filters.get("date_to"):
            q = q.filter(RewardStock.created_date <= filters["date_to"])
        if filters.get("q"):
            like = f"%{filters['q']}%"
            q = q.filter(or_(RewardCatalog.name.ilike(like), RewardStock.note.ilike(like)))

        total = q.count()
        rows = (
            q.order_by(RewardStock.created_date.desc(), RewardStock.id.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        items = []
        for stock, cat_name, cam_name in rows:
            entry = self._stock_to_dict(stock)
            entry["catalog_name"] = cat_name
            entry["campaign_name"] = cam_name  # nullable
            items.append(entry)

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
        }
