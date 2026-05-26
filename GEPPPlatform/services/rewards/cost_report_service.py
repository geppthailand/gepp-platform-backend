"""
Cost Report Service — Profit/Loss, ROI, and vendor breakdown for the rewards inventory.

Phase 2: powers the Cost Report destination page (full-page route from Inventory tab).
"""

from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardSetup, RewardCampaign, RewardCampaignExpense, RewardExpenseCategory,
)
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
        campaign_id: int | None = None,
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
        # [V3-COST-AUDIT] Apply campaign_id filter when provided. RewardStock.reward_campaign_id
        # is set on deposits that go directly to a specific campaign (NULL = Global pool).
        # When admin filters by campaign, total_spend now reflects "money spent directly buying
        # inventory for this campaign" — not Global → transfer flows.
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
        if campaign_id is not None:
            spend_q = spend_q.filter(RewardStock.reward_campaign_id == campaign_id)
        total_spend = float(spend_q.scalar() or 0)

        # ── Redemption value (points + baht equivalent) ──
        # [V3-CAMPAIGN-RATE] Aggregate per-campaign so each redemption is multiplied by
        # the campaign's own rate; fall back to the org rate when the campaign hasn't set one.
        # [V3-COST-AUDIT] When campaign_id filter is provided, scope the entire aggregation
        # to that single campaign — previously the per_campaign_q ran across all campaigns
        # and only the rate-lookup was per-campaign, which inflated redeem_pt / redeem_count.
        per_campaign_q = self.db.query(
            RewardPointTransaction.reward_campaign_id.label("campaign_id"),
            func.coalesce(func.sum(RewardPointTransaction.points), 0).label("points"),
            func.count(RewardPointTransaction.id).label("count"),
        ).filter(
            RewardPointTransaction.organization_id == organization_id,
            RewardPointTransaction.reference_type == "redeem",
            RewardPointTransaction.deleted_date.is_(None),
        )
        if date_from_dt:
            per_campaign_q = per_campaign_q.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt:
            per_campaign_q = per_campaign_q.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        if campaign_id is not None:
            per_campaign_q = per_campaign_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        per_campaign_rows = per_campaign_q.group_by(RewardPointTransaction.reward_campaign_id).all()

        # Resolve each campaign's rate (campaign override > org rate fallback)
        campaign_ids_seen = {r.campaign_id for r in per_campaign_rows if r.campaign_id is not None}
        campaign_rate_lookup: dict[int, float] = {}
        if campaign_ids_seen:
            for c in (
                self.db.query(RewardCampaign.id, RewardCampaign.point_to_baht_rate)
                .filter(RewardCampaign.id.in_(campaign_ids_seen))
                .all()
            ):
                if c.point_to_baht_rate is not None:
                    campaign_rate_lookup[c.id] = float(c.point_to_baht_rate)

        redeem_pt = 0
        redeem_count = 0
        redemption_value_baht = 0.0
        for r in per_campaign_rows:
            pts = abs(int(r.points or 0))  # redeems stored as negatives
            redeem_pt += pts
            redeem_count += int(r.count or 0)
            cam_rate = campaign_rate_lookup.get(r.campaign_id, rate)
            redemption_value_baht += pts * cam_rate

        # ── Redemption cost (TRUE FIFO per lot) ──
        # [V3-COST-FIFO] Walks each catalog's full ledger chronologically and consumes
        # the oldest lot first, accumulating COGS only for redemptions inside the filter
        # window. Earlier version used a weighted-average across all deposits, which is
        # wrong when lot prices differ — e.g., Lot1 @10฿ + Lot2 @11฿ and only Lot1 is
        # consumed would compute COGS at 10.5฿/unit instead of the actual 10฿/unit.
        redemption_cost_baht = 0.0
        top_costly: list[dict] = []
        for cid in catalog_ids:
            cogs, qty = self._fifo_cogs_per_catalog(cid, date_from_dt, date_to_dt, campaign_id)
            if qty == 0:
                continue
            redemption_cost_baht += cogs
            cat = self.db.query(RewardCatalog).filter(RewardCatalog.id == cid).first()
            top_costly.append({
                "catalog_id": cid,
                "name": cat.name if cat else f"#{cid}",
                "units_redeemed": qty,
                "cost_baht": round(cogs, 2),
                "avg_unit_cost": round(cogs / qty if qty > 0 else 0.0, 2),
            })
        top_costly.sort(key=lambda r: -r["cost_baht"])
        top_costly = top_costly[:10]

        # ── Profit & ROI ──
        profit = redemption_value_baht - redemption_cost_baht
        roi_pct = round(profit / redemption_cost_baht * 100, 2) if redemption_cost_baht > 0 else None

        # ── Vendor breakdown ──
        # [V3-COST-AUDIT] Apply same date + campaign filters as total_spend so the breakdown
        # sums to the headline number. Previously vendor totals could exceed total_spend
        # when a date range was set.
        vendor_q = self.db.query(
            RewardStock.vendor.label("vendor"),
            func.coalesce(func.sum(RewardStock.total_price), 0).label("spend"),
            func.count(RewardStock.id).label("count"),
        ).filter(
            RewardStock.reward_catalog_id.in_(catalog_ids),
            RewardStock.ledger_type == "deposit",
            RewardStock.deleted_date.is_(None),
        )
        if date_from_dt:
            vendor_q = vendor_q.filter(RewardStock.created_date >= date_from_dt)
        if date_to_dt:
            vendor_q = vendor_q.filter(RewardStock.created_date <= date_to_dt)
        if campaign_id is not None:
            vendor_q = vendor_q.filter(RewardStock.reward_campaign_id == campaign_id)
        vendor_rows = vendor_q.group_by(RewardStock.vendor).all()
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
        # [V3-COST-CASHBASED] Bar chart now combines stock purchases + ledger expenses,
        # so the sum of bars equals total_cost_all_in_baht (matching the headline KPI).
        monthly = self._monthly_spend(
            catalog_ids,
            organization_id=organization_id,
            date_from_dt=date_from_dt,
            date_to_dt=date_to_dt,
            campaign_id=campaign_id,
        )

        # ── [V3-COST-LEDGER] Expense ledger aggregation (Manpower / Transport / Marketing / etc.)
        # The "ของรางวัล" category in the report is reported separately as inventory cost
        # (redemption_cost_baht above) — it does NOT have entries in the ledger. Other
        # categories are summed from the ledger.
        exp_q = (
            self.db.query(
                RewardExpenseCategory.id.label("category_id"),
                RewardExpenseCategory.name.label("category_name"),
                RewardExpenseCategory.is_inventory.label("is_inventory"),
                RewardExpenseCategory.sort_order.label("sort_order"),
                func.coalesce(func.sum(RewardCampaignExpense.amount_baht), 0).label("amount"),
            )
            .outerjoin(
                RewardCampaignExpense,
                (RewardCampaignExpense.expense_category_id == RewardExpenseCategory.id)
                & (RewardCampaignExpense.deleted_date.is_(None)),
            )
            .filter(
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.deleted_date.is_(None),
            )
        )
        # Constrain expense join to the date / campaign window (note: inventory category
        # rows are kept even with zero amount so the report shows them with their auto-computed cost).
        if date_from_dt is not None:
            exp_q = exp_q.filter(
                (RewardCampaignExpense.expense_date.is_(None))
                | (RewardCampaignExpense.expense_date >= date_from_dt)
            )
        if date_to_dt is not None:
            exp_q = exp_q.filter(
                (RewardCampaignExpense.expense_date.is_(None))
                | (RewardCampaignExpense.expense_date <= date_to_dt)
            )
        if campaign_id is not None:
            exp_q = exp_q.filter(
                (RewardCampaignExpense.reward_campaign_id.is_(None))
                | (RewardCampaignExpense.reward_campaign_id == campaign_id)
            )

        exp_rows = exp_q.group_by(
            RewardExpenseCategory.id,
            RewardExpenseCategory.name,
            RewardExpenseCategory.is_inventory,
            RewardExpenseCategory.sort_order,
        ).order_by(RewardExpenseCategory.sort_order.asc()).all()

        expense_by_category: list[dict] = []
        total_other_expenses = 0.0
        for r in exp_rows:
            amount = float(r.amount or 0)
            # [V3-COST-CASHBASED] The inventory category reports total purchase spend
            # (cash out for stock) — not COGS of redeemed items. So the doughnut sums
            # to total_cost_all_in_baht, matching the headline KPI.
            if r.is_inventory:
                amount = round(total_spend, 2)
            expense_by_category.append({
                "category_id": int(r.category_id),
                "category_name": r.category_name,
                "is_inventory": bool(r.is_inventory),
                "amount_baht": round(amount, 2),
            })
            if not r.is_inventory:
                total_other_expenses += amount

        # [V3-COST-CASHBASED] Cost = cash actually spent (stock purchases + ledger expenses).
        # Profit = gross margin from redemptions only (revenue − FIFO COGS of items redeemed).
        # ROI = profit / total_cost_all_in × 100 — measured against ALL cash out (including
        # stock still in the warehouse). Picked over the COGS-only denominator because COGS
        # is frequently 0 when stock is added without a recorded purchase price, producing
        # an undefined ROI; total_cost_all_in is always populated and easier for admins to
        # reconcile against actual cash flow.
        total_cost_all_in = total_spend + total_other_expenses
        profit_all_in = redemption_value_baht - redemption_cost_baht
        roi_pct_all_in = (
            round(profit_all_in / total_cost_all_in * 100, 2)
            if total_cost_all_in > 0
            else None
        )

        return {
            "conversion_rate": rate,
            "total_spend": round(total_spend, 2),
            "redemption_cost_baht": round(redemption_cost_baht, 2),
            "redemption_value_pt": redeem_pt,
            "redemption_value_baht": round(redemption_value_baht, 2),
            "redemption_count": redeem_count,
            # Inventory-only P&L (kept for backwards-compat with old UI)
            "profit": round(profit, 2),
            "roi_pct": roi_pct,
            # [V3-COST-LEDGER] All-in P&L including expense ledger
            "total_other_expenses_baht": round(total_other_expenses, 2),
            "total_cost_all_in_baht": round(total_cost_all_in, 2),
            "profit_all_in_baht": round(profit_all_in, 2),
            "roi_pct_all_in": roi_pct_all_in,
            "expense_by_category": expense_by_category,
            "vendor_breakdown": vendor_breakdown,
            "top_costly_items": top_costly,
            "monthly_spend": monthly,
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    def _fifo_cogs_per_catalog(
        self,
        catalog_id: int,
        date_from_dt: datetime | None,
        date_to_dt: datetime | None,
        campaign_id: int | None,
    ) -> tuple[float, int]:
        """True FIFO: walk the catalog's ledger chronologically, consume oldest lots
        first, and sum COGS only for redemptions inside the filter window.

        Returns (cogs_in_window, qty_in_window).
        """
        q = self.db.query(
            RewardStock.id,
            RewardStock.created_date,
            RewardStock.ledger_type,
            RewardStock.values,
            RewardStock.total_price,
        ).filter(
            RewardStock.reward_catalog_id == catalog_id,
            RewardStock.ledger_type.in_(("deposit", "redeem")),
            RewardStock.deleted_date.is_(None),
        )
        if campaign_id is not None:
            q = q.filter(RewardStock.reward_campaign_id == campaign_id)
        rows = q.order_by(RewardStock.created_date.asc(), RewardStock.id.asc()).all()

        lots: list[list[float]] = []  # [[qty_remaining, unit_cost], ...]
        cogs_in_window = 0.0
        qty_in_window = 0

        for r in rows:
            qty = int(r.values or 0)
            if r.ledger_type == "deposit":
                if qty <= 0:
                    continue
                total_price = float(r.total_price or 0)
                unit_cost = total_price / qty if qty > 0 else 0.0
                lots.append([float(qty), unit_cost])
            elif r.ledger_type == "redeem":
                remaining = abs(qty)
                if remaining <= 0:
                    continue
                in_window = True
                if date_from_dt is not None and r.created_date < date_from_dt:
                    in_window = False
                if date_to_dt is not None and r.created_date > date_to_dt:
                    in_window = False
                while remaining > 0 and lots:
                    lot = lots[0]
                    consume = min(remaining, lot[0])
                    if in_window:
                        cogs_in_window += consume * lot[1]
                        qty_in_window += int(consume)
                    lot[0] -= consume
                    remaining -= consume
                    if lot[0] <= 0:
                        lots.pop(0)
                # Note: if lots run out before redemption is satisfied, the leftover
                # has unknown cost basis (data integrity issue). We silently skip it
                # rather than fabricating a cost.

        return cogs_in_window, qty_in_window

    def _monthly_spend(
        self,
        catalog_ids: list[int],
        organization_id: int,
        date_from_dt: datetime | None = None,
        date_to_dt: datetime | None = None,
        campaign_id: int | None = None,
    ) -> list[dict]:
        """Combined monthly cash-out: stock deposits + ledger expenses (non-inventory).
        Sum across all months = total_cost_all_in_baht headline.
        """
        # Stock deposit spend per month
        dep_q = (
            self.db.query(
                func.to_char(func.date_trunc('month', RewardStock.created_date), 'YYYY-MM').label("month"),
                func.coalesce(func.sum(RewardStock.total_price), 0).label("spend"),
            )
            .filter(
                RewardStock.reward_catalog_id.in_(catalog_ids),
                RewardStock.ledger_type == "deposit",
                RewardStock.deleted_date.is_(None),
            )
        )
        if date_from_dt:
            dep_q = dep_q.filter(RewardStock.created_date >= date_from_dt)
        if date_to_dt:
            dep_q = dep_q.filter(RewardStock.created_date <= date_to_dt)
        if campaign_id is not None:
            dep_q = dep_q.filter(RewardStock.reward_campaign_id == campaign_id)
        dep_rows = dep_q.group_by("month").all()

        # Ledger expense per month (excludes the auto-computed inventory category)
        exp_q = (
            self.db.query(
                func.to_char(func.date_trunc('month', RewardCampaignExpense.expense_date), 'YYYY-MM').label("month"),
                func.coalesce(func.sum(RewardCampaignExpense.amount_baht), 0).label("spend"),
            )
            .join(
                RewardExpenseCategory,
                RewardExpenseCategory.id == RewardCampaignExpense.expense_category_id,
            )
            .filter(
                RewardExpenseCategory.organization_id == organization_id,
                RewardExpenseCategory.is_inventory.is_(False),
                RewardCampaignExpense.deleted_date.is_(None),
            )
        )
        if date_from_dt:
            exp_q = exp_q.filter(RewardCampaignExpense.expense_date >= date_from_dt)
        if date_to_dt:
            exp_q = exp_q.filter(RewardCampaignExpense.expense_date <= date_to_dt)
        if campaign_id is not None:
            exp_q = exp_q.filter(RewardCampaignExpense.reward_campaign_id == campaign_id)
        exp_rows = exp_q.group_by("month").all()

        monthly: dict[str, float] = defaultdict(float)
        for r in dep_rows:
            monthly[r.month] += float(r.spend or 0)
        for r in exp_rows:
            monthly[r.month] += float(r.spend or 0)

        result = sorted(
            [{"month": m, "spend": round(s, 2)} for m, s in monthly.items()],
            key=lambda x: x["month"],
        )
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
        # [V3-COST-LEDGER]
        "total_other_expenses_baht": 0.0,
        "total_cost_all_in_baht": 0.0,
        "profit_all_in_baht": 0.0,
        "roi_pct_all_in": None,
        "expense_by_category": [],
        "vendor_breakdown": [],
        "top_costly_items": [],
        "monthly_spend": [],
    }
