"""
Cost Report Service — Profit/Loss, ROI, and vendor breakdown for the rewards inventory.

Phase 2: powers the Cost Report destination page (full-page route from Inventory tab).
"""

from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.management import RewardSetup, RewardCampaign
from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...models.rewards.points import RewardPointTransaction
from ...exceptions import APIException


class CostReportService:
    def __init__(self, db: Session):
        self.db = db

    def get_report(
        self,
        organization_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """Aggregate cost analytics for the org.

        Returns:
          {
            conversion_rate: float (1 pt = X baht),
            total_spend: float (sum of deposit total_price),
            redemption_cost_baht: float (FIFO cost of items redeemed),
            redemption_value_pt: int (sum of points redeemed),
            redemption_value_baht: float (points × conversion_rate),
            profit: float (value - cost),
            roi_pct: float | null,
            vendor_breakdown: [{vendor, spend, count}],
            top_costly_items: [{catalog_id, name, units_redeemed, cost_baht}],
            monthly_spend: [{month: 'YYYY-MM', spend, redemption_cost}],
          }
        """
        # ── Resolve conversion rate from setup ──
        setup = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )
        if setup and setup.point_to_baht_rate is not None:
            rate = float(setup.point_to_baht_rate)
        elif setup and setup.cost_per_point is not None:
            rate = float(setup.cost_per_point)
        else:
            rate = 0.5

        # ── Date filters (optional) ──
        date_from_dt = _parse_date(date_from)
        date_to_dt = _parse_date(date_to)

        # ── Org's catalog item ids (scope filter for stock + redemptions) ──
        catalog_ids = [
            row.id for row in self.db.query(RewardCatalog.id).filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            ).all()
        ]
        if not catalog_ids:
            return _empty_report(rate)

        # ── Total spend = sum of deposit total_price for this org's catalog ──
        spend_q = self.db.query(
            func.coalesce(func.sum(RewardStock.total_price), 0)
        ).filter(
            RewardStock.reward_catalog_id.in_(catalog_ids),
            RewardStock.ledger_type == "deposit",
            RewardStock.deleted_date.is_(None),
        )
        if date_from_dt:
            spend_q = spend_q.filter(RewardStock.created_date >= date_from_dt)
        if date_to_dt:
            spend_q = spend_q.filter(RewardStock.created_date <= date_to_dt)
        total_spend = float(spend_q.scalar() or 0)

        # ── Redemption value (points + baht equivalent) ──
        redeem_q = self.db.query(
            func.coalesce(func.sum(RewardPointTransaction.points), 0).label("points"),
            func.count(RewardPointTransaction.id).label("count"),
        ).filter(
            RewardPointTransaction.organization_id == organization_id,
            RewardPointTransaction.reference_type == "redeem",
            RewardPointTransaction.deleted_date.is_(None),
        )
        if date_from_dt:
            redeem_q = redeem_q.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt:
            redeem_q = redeem_q.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        redeem_row = redeem_q.first()
        redeem_pt = abs(int(redeem_row.points or 0))  # redeems are stored as negatives
        redeem_count = int(redeem_row.count or 0)
        redemption_value_baht = redeem_pt * rate

        # ── Redemption cost (FIFO-approx via avg unit cost × qty redeemed) ──
        # NOTE: full FIFO traceability per redemption is expensive; using average-cost approximation.
        redemption_cost_baht = 0.0
        top_costly: list[dict] = []
        for cid in catalog_ids:
            avg_cost = self._avg_unit_cost(cid)
            if avg_cost <= 0:
                continue
            redeemed_qty = self._redeemed_qty(cid, date_from_dt, date_to_dt)
            if redeemed_qty == 0:
                continue
            cost_baht = avg_cost * redeemed_qty
            redemption_cost_baht += cost_baht
            cat = self.db.query(RewardCatalog).filter(RewardCatalog.id == cid).first()
            top_costly.append({
                "catalog_id": cid,
                "name": cat.name if cat else f"#{cid}",
                "units_redeemed": redeemed_qty,
                "cost_baht": round(cost_baht, 2),
                "avg_unit_cost": round(avg_cost, 2),
            })
        top_costly.sort(key=lambda r: -r["cost_baht"])
        top_costly = top_costly[:10]

        # ── Profit & ROI ──
        profit = redemption_value_baht - redemption_cost_baht
        roi_pct = round(profit / redemption_cost_baht * 100, 2) if redemption_cost_baht > 0 else None

        # ── Vendor breakdown ──
        vendor_rows = self.db.query(
            RewardStock.vendor.label("vendor"),
            func.coalesce(func.sum(RewardStock.total_price), 0).label("spend"),
            func.count(RewardStock.id).label("count"),
        ).filter(
            RewardStock.reward_catalog_id.in_(catalog_ids),
            RewardStock.ledger_type == "deposit",
            RewardStock.deleted_date.is_(None),
        ).group_by(RewardStock.vendor).all()
        vendor_breakdown = [
            {
                "vendor": (v.vendor or "ไม่ระบุ"),
                "spend": float(v.spend or 0),
                "count": int(v.count or 0),
            }
            for v in vendor_rows
        ]
        vendor_breakdown.sort(key=lambda r: -r["spend"])

        # ── Monthly spend (last 6 months) ──
        monthly = self._monthly_spend(catalog_ids, organization_id)

        return {
            "conversion_rate": rate,
            "total_spend": round(total_spend, 2),
            "redemption_cost_baht": round(redemption_cost_baht, 2),
            "redemption_value_pt": redeem_pt,
            "redemption_value_baht": round(redemption_value_baht, 2),
            "redemption_count": redeem_count,
            "profit": round(profit, 2),
            "roi_pct": roi_pct,
            "vendor_breakdown": vendor_breakdown,
            "top_costly_items": top_costly,
            "monthly_spend": monthly,
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    def _avg_unit_cost(self, catalog_id: int) -> float:
        row = self.db.query(
            func.coalesce(func.sum(RewardStock.total_price), 0).label("spend"),
            func.coalesce(func.sum(RewardStock.values), 0).label("qty"),
        ).filter(
            RewardStock.reward_catalog_id == catalog_id,
            RewardStock.ledger_type == "deposit",
            RewardStock.deleted_date.is_(None),
        ).first()
        spend = float(row.spend or 0)
        qty = int(row.qty or 0)
        return (spend / qty) if qty > 0 else 0.0

    def _redeemed_qty(
        self,
        catalog_id: int,
        date_from_dt: datetime | None,
        date_to_dt: datetime | None,
    ) -> int:
        q = self.db.query(
            func.coalesce(func.sum(func.abs(RewardStock.values)), 0)
        ).filter(
            RewardStock.reward_catalog_id == catalog_id,
            RewardStock.ledger_type == "redeem",
            RewardStock.deleted_date.is_(None),
        )
        if date_from_dt:
            q = q.filter(RewardStock.created_date >= date_from_dt)
        if date_to_dt:
            q = q.filter(RewardStock.created_date <= date_to_dt)
        return int(q.scalar() or 0)

    def _monthly_spend(self, catalog_ids: list[int], organization_id: int) -> list[dict]:
        # Group by year-month; PostgreSQL date_trunc → 'YYYY-MM-01' string
        rows = (
            self.db.query(
                func.to_char(func.date_trunc('month', RewardStock.created_date), 'YYYY-MM').label("month"),
                func.coalesce(func.sum(RewardStock.total_price), 0).label("spend"),
            )
            .filter(
                RewardStock.reward_catalog_id.in_(catalog_ids),
                RewardStock.ledger_type == "deposit",
                RewardStock.deleted_date.is_(None),
            )
            .group_by("month")
            .order_by("month")
            .all()
        )
        result = [{"month": r.month, "spend": float(r.spend or 0)} for r in rows]
        # Keep last 6 months
        return result[-6:] if len(result) > 6 else result


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _empty_report(rate: float) -> dict:
    return {
        "conversion_rate": rate,
        "total_spend": 0.0,
        "redemption_cost_baht": 0.0,
        "redemption_value_pt": 0,
        "redemption_value_baht": 0.0,
        "redemption_count": 0,
        "profit": 0.0,
        "roi_pct": None,
        "vendor_breakdown": [],
        "top_costly_items": [],
        "monthly_spend": [],
    }
