"""
Overview Service - Dashboard statistics for reward programs
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, distinct, and_
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    OrganizationRewardUser, RewardRedemption, RewardUser, Droppoint,
)
from ...models.rewards.management import (
    RewardCampaign, RewardActivityMaterial, RewardSetup,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.catalog import RewardCatalog, RewardStock
from .campaign_target_service import CampaignTargetService


def _month_boundaries(now: datetime):
    """Return (this_month_start, last_month_start) as UTC datetimes."""
    this_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_start = (this_start - timedelta(days=1)).replace(day=1)
    return this_start, last_start


class OverviewService:
    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # § 2 — KPI Cards data (get_stats)
    # ================================================================
    def get_stats(self, organization_id: int) -> dict:
        """Return KPI data for the 8 cards in Overview Section 2.

        Row 1 (Operations): campaigns, members, weight, GHG
        Row 2 (Financial): points issued, budget used, waste revenue, profit/loss
        Plus fields needed by other sections (pending redemptions, etc.)
        """
        now = datetime.now(timezone.utc)
        this_month_start, last_month_start = _month_boundaries(now)
        week_ago = now - timedelta(days=7)

        # ── Members ──
        total_members = self._scalar_count(
            OrganizationRewardUser,
            OrganizationRewardUser.organization_id == organization_id,
            OrganizationRewardUser.deleted_date.is_(None),
        )
        new_members_this_month = self._scalar_count(
            OrganizationRewardUser,
            OrganizationRewardUser.organization_id == organization_id,
            OrganizationRewardUser.created_date >= this_month_start,
            OrganizationRewardUser.deleted_date.is_(None),
        )
        new_members_this_week = self._scalar_count(
            OrganizationRewardUser,
            OrganizationRewardUser.organization_id == organization_id,
            OrganizationRewardUser.created_date >= week_ago,
            OrganizationRewardUser.deleted_date.is_(None),
        )

        # ── Campaigns ──
        active_campaigns = self._scalar_count(
            RewardCampaign,
            RewardCampaign.organization_id == organization_id,
            RewardCampaign.status == "active",
            RewardCampaign.deleted_date.is_(None),
        )
        total_campaigns = self._scalar_count(
            RewardCampaign,
            RewardCampaign.organization_id == organization_id,
            RewardCampaign.deleted_date.is_(None),
        )

        # ── Weight (kg) ── SUM(value) for claim-type transactions
        total_weight_all_time = self._sum_weight(
            organization_id, start=None, end=None,
        )
        total_weight_this_month = self._sum_weight(
            organization_id, start=this_month_start, end=None,
        )
        total_weight_last_month = self._sum_weight(
            organization_id, start=last_month_start, end=this_month_start,
        )

        # ── GHG (tCO2e) ── value × ghg_factor (join activity_materials)
        total_ghg_all_time = self._sum_ghg(organization_id, start=None, end=None)
        total_ghg_this_month = self._sum_ghg(organization_id, start=this_month_start, end=None)
        total_ghg_last_month = self._sum_ghg(organization_id, start=last_month_start, end=this_month_start)

        # ── Points ──
        total_points_issued = float(
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.points > 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )
        total_points_redeemed = float(
            self.db.query(func.coalesce(func.sum(-RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "redeem",
                RewardPointTransaction.points < 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        # ── Redemptions ──
        total_redemptions = self._scalar_count(
            RewardRedemption,
            RewardRedemption.organization_id == organization_id,
            RewardRedemption.deleted_date.is_(None),
        )
        pending_redemptions = self._scalar_count(
            RewardRedemption,
            RewardRedemption.organization_id == organization_id,
            RewardRedemption.status == "inprogress",
            RewardRedemption.deleted_date.is_(None),
        )

        # ── Financial: Reward budget used ──
        # SUM(catalog.cost_baht × redemption.quantity) for completed redemptions
        reward_budget_used = float(
            self.db.query(
                func.coalesce(
                    func.sum(RewardCatalog.cost_baht * RewardRedemption.quantity), 0
                )
            )
            .select_from(RewardRedemption)
            .join(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
            .filter(
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.status == "completed",
                RewardRedemption.deleted_date.is_(None),
                RewardCatalog.cost_baht.isnot(None),
            )
            .scalar() or 0
        )

        # ── Reward budget total from setup ──
        setup = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )
        reward_budget_total = float(setup.reward_budget_total) if setup and setup.reward_budget_total else 0.0

        # ── Financial: Waste revenue ──
        # SUM(transaction.value × material.selling_price_per_kg)
        waste_revenue_total = self._sum_waste_revenue(organization_id, start=None, end=None)
        waste_revenue_this_month = self._sum_waste_revenue(
            organization_id, start=this_month_start, end=None,
        )

        return {
            # Operations
            "total_members": total_members,
            "new_members_this_week": new_members_this_week,
            "new_members_this_month": new_members_this_month,
            "active_campaigns": active_campaigns,
            "total_campaigns": total_campaigns,
            "total_weight_all_time": float(total_weight_all_time),
            "total_weight_this_month": float(total_weight_this_month),
            "total_weight_last_month": float(total_weight_last_month),
            "total_ghg_all_time": float(total_ghg_all_time),
            "total_ghg_this_month": float(total_ghg_this_month),
            "total_ghg_last_month": float(total_ghg_last_month),
            # Points
            "total_points_issued": total_points_issued,
            "total_points_redeemed": total_points_redeemed,
            # Redemptions
            "total_redemptions": total_redemptions,
            "pending_redemptions": pending_redemptions,
            # Financial
            "reward_budget_used": reward_budget_used,
            "reward_budget_total": reward_budget_total,
            "waste_revenue_total": waste_revenue_total,
            "waste_revenue_this_month": waste_revenue_this_month,
        }

    # ================================================================
    # § 1 — Alerts
    # ================================================================
    def get_alerts(self, organization_id: int) -> dict:
        """Return actionable alerts for the Summary Banner.

        - low_stock: catalog items with total_stock < threshold
        - expiring_campaigns: campaigns ending within 7 days
        - stale_pending: redemptions with status=inprogress > 3 days
        """
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=7)
        stale_cutoff = now - timedelta(days=3)

        # Low-stock items — use per-item min_threshold (0 = no alert for that item)
        stock_sum = (
            self.db.query(
                RewardCatalog.id.label("catalog_id"),
                RewardCatalog.name.label("name"),
                func.coalesce(func.sum(RewardStock.values), 0).label("total_stock"),
            )
            .outerjoin(
                RewardStock,
                and_(
                    RewardStock.reward_catalog_id == RewardCatalog.id,
                    RewardStock.deleted_date.is_(None),
                ),
            )
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
                RewardCatalog.min_threshold > 0,
            )
            .group_by(RewardCatalog.id, RewardCatalog.name, RewardCatalog.min_threshold)
            .having(func.coalesce(func.sum(RewardStock.values), 0) < RewardCatalog.min_threshold)
            .all()
        )
        low_stock = [
            {
                "catalog_id": r.catalog_id,
                "name": r.name,
                "total_stock": int(r.total_stock),
            }
            for r in stock_sum
        ]

        # Expiring campaigns (within 7 days)
        expiring = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.status == "active",
                RewardCampaign.end_date.isnot(None),
                RewardCampaign.end_date <= soon,
                RewardCampaign.end_date >= now,
                RewardCampaign.deleted_date.is_(None),
            )
            .all()
        )
        expiring_campaigns = [
            {
                "id": c.id,
                "name": c.name,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "days_left": max(0, (c.end_date - now).days) if c.end_date else None,
            }
            for c in expiring
        ]

        # Stale pending redemptions (> 3 days in progress)
        stale = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.status == "inprogress",
                RewardRedemption.created_date <= stale_cutoff,
                RewardRedemption.deleted_date.is_(None),
            )
            .all()
        )
        stale_pending = [
            {
                "id": r.id,
                "catalog_id": r.catalog_id,
                "days_old": (now - r.created_date).days if r.created_date else 0,
            }
            for r in stale
        ]

        return {
            "low_stock": low_stock,
            "expiring_campaigns": expiring_campaigns,
            "stale_pending": stale_pending,
        }

    # ================================================================
    # § 3 — Active Campaign Detail Cards
    # ================================================================
    def get_campaign_details(self, organization_id: int) -> list[dict]:
        """Per-campaign metrics for active campaigns:
        participants, weight, GHG, stock per item, staff activity today."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        campaigns = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.status == "active",
                RewardCampaign.deleted_date.is_(None),
            )
            .order_by(RewardCampaign.start_date.desc())
            .all()
        )

        result = []
        for c in campaigns:
            # Participants (distinct users who have claimed in this campaign)
            participants = (
                self.db.query(func.count(distinct(RewardPointTransaction.reward_user_id)))
                .filter(
                    RewardPointTransaction.reward_campaign_id == c.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar() or 0
            )

            # Weight (kg) collected in this campaign
            weight = float(
                self.db.query(func.coalesce(func.sum(RewardPointTransaction.value), 0))
                .filter(
                    RewardPointTransaction.reward_campaign_id == c.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar() or 0
            )

            # GHG saved (tCO2e) for this campaign
            ghg_kg = float(
                self.db.query(
                    func.coalesce(
                        func.sum(RewardPointTransaction.value * RewardActivityMaterial.ghg_factor),
                        0,
                    )
                )
                .select_from(RewardPointTransaction)
                .join(
                    RewardActivityMaterial,
                    RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
                )
                .filter(
                    RewardPointTransaction.reward_campaign_id == c.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardActivityMaterial.ghg_factor.isnot(None),
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar() or 0
            )

            # Stock for this campaign (join via reward_campaign_catalog → reward_catalog)
            stock_rows = (
                self.db.query(
                    RewardCatalog.id.label("catalog_id"),
                    RewardCatalog.name.label("name"),
                    RewardCatalog.unit.label("unit"),
                    func.coalesce(
                        func.sum(RewardStock.values).filter(
                            RewardStock.reward_campaign_id == c.id
                        ),
                        0,
                    ).label("current"),
                    func.coalesce(
                        func.sum(RewardStock.values).filter(
                            and_(
                                RewardStock.reward_campaign_id == c.id,
                                RewardStock.values > 0,
                            )
                        ),
                        0,
                    ).label("initial"),
                )
                .outerjoin(
                    RewardStock,
                    and_(
                        RewardStock.reward_catalog_id == RewardCatalog.id,
                        RewardStock.deleted_date.is_(None),
                    ),
                )
                .filter(
                    RewardCatalog.organization_id == organization_id,
                    RewardCatalog.deleted_date.is_(None),
                )
                .group_by(RewardCatalog.id, RewardCatalog.name, RewardCatalog.unit)
                .having(
                    func.coalesce(
                        func.sum(RewardStock.values).filter(
                            and_(
                                RewardStock.reward_campaign_id == c.id,
                                RewardStock.values > 0,
                            )
                        ),
                        0,
                    ) > 0
                )
                .all()
            )
            stocks = [
                {
                    "catalog_id": s.catalog_id,
                    "name": s.name,
                    "unit": s.unit,
                    "current": int(s.current or 0),
                    "initial": int(s.initial or 0),
                }
                for s in stock_rows
            ]

            # Staff active today on this campaign
            staff_rows = (
                self.db.query(
                    RewardPointTransaction.staff_id.label("staff_id"),
                    func.count(RewardPointTransaction.id).label("claims_count"),
                )
                .filter(
                    RewardPointTransaction.reward_campaign_id == c.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.claimed_date >= today_start,
                    RewardPointTransaction.staff_id.isnot(None),
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .group_by(RewardPointTransaction.staff_id)
                .all()
            )
            staff = []
            for sr in staff_rows:
                # Lookup staff name via OrganizationRewardUser → RewardUser
                staff_entry = (
                    self.db.query(OrganizationRewardUser, RewardUser)
                    .join(RewardUser, RewardUser.id == OrganizationRewardUser.reward_user_id)
                    .filter(OrganizationRewardUser.id == sr.staff_id)
                    .first()
                )
                display_name = None
                if staff_entry:
                    _, user = staff_entry
                    display_name = user.display_name or user.line_display_name
                staff.append({
                    "staff_org_user_id": sr.staff_id,
                    "display_name": display_name or f"Staff #{sr.staff_id}",
                    "claims_today": int(sr.claims_count),
                })

            # Targets for this campaign (each with computed current_amount)
            targets = CampaignTargetService(self.db).list(c.id)

            result.append({
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "days_left": max(0, (c.end_date - now).days) if c.end_date else None,
                "participants_count": int(participants),
                "total_weight": weight,
                "total_ghg_kg": ghg_kg,  # keep in kg — frontend formats
                "stocks": stocks,
                "staff_today": staff,
                "targets": targets,
            })

        return result

    # ================================================================
    # § 4 — Staff Active Today
    # ================================================================
    def get_staff_today(self, organization_id: int) -> list[dict]:
        """All staff in the org, with today's claim activity + online/offline status.

        online = has ≥1 claim today
        offline = no claim today; show last_active
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # All staff of the org
        staff_entries = (
            self.db.query(OrganizationRewardUser, RewardUser)
            .join(RewardUser, RewardUser.id == OrganizationRewardUser.reward_user_id)
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.role == "staff",
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .all()
        )

        result = []
        for oru, user in staff_entries:
            # Today's activity
            today = (
                self.db.query(
                    func.count(RewardPointTransaction.id).label("claims"),
                    func.coalesce(func.sum(RewardPointTransaction.value), 0).label("weight"),
                    func.max(RewardPointTransaction.droppoint_id).label("droppoint_id"),
                )
                .filter(
                    RewardPointTransaction.staff_id == oru.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.claimed_date >= today_start,
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .first()
            )
            claims_today = int(today.claims or 0) if today else 0
            weight_today = float(today.weight or 0) if today else 0.0
            droppoint_id = today.droppoint_id if today else None

            # Last active (most recent claim ever)
            last = (
                self.db.query(func.max(RewardPointTransaction.claimed_date))
                .filter(
                    RewardPointTransaction.staff_id == oru.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar()
            )

            # Droppoint name
            dp_name = None
            if droppoint_id:
                dp = self.db.query(Droppoint).filter(Droppoint.id == droppoint_id).first()
                dp_name = dp.name if dp else None

            result.append({
                "staff_org_user_id": oru.id,
                "display_name": user.display_name or user.line_display_name or f"Staff #{oru.id}",
                "line_picture_url": user.line_picture_url,
                "is_online": claims_today > 0,
                "claims_today": claims_today,
                "weight_today": weight_today,
                "droppoint_name": dp_name,
                "last_active": last.isoformat() if last else None,
            })

        # Sort: online first, then by claims desc
        result.sort(key=lambda r: (not r["is_online"], -r["claims_today"]))
        return result

    # ================================================================
    # § 5 — Trends (6-month time-series) + § 6 Environmental Impact
    # ================================================================
    def get_trends(self, organization_id: int, months: int = 6) -> dict:
        """Return monthly aggregates for the last N months (default 6)
        for the 5 dashboard charts + breakdown data.

        Charts covered:
        - Chart 1 (dual-axis): waste_by_month + ghg_by_month
        - Chart 2 (stacked):   budget_by_month + revenue_by_month
        - Chart 3 (donut):     waste_by_type
        - Chart 4 (dual-line): points_issued_by_month + points_redeemed_by_month
        - Chart 5 (bar):       new_members_by_month
        """
        now = datetime.now(timezone.utc)
        # Start of N-th month ago (first day)
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Walk back (months - 1) months
        start = this_month_start
        for _ in range(months - 1):
            start = (start - timedelta(days=1)).replace(day=1)

        # Build month buckets: list of (bucket_start, bucket_end, label "YYYY-MM")
        buckets: list[tuple[datetime, datetime, str]] = []
        cursor = start
        for _ in range(months):
            if cursor.month == 12:
                next_month = cursor.replace(year=cursor.year + 1, month=1)
            else:
                next_month = cursor.replace(month=cursor.month + 1)
            label = cursor.strftime("%Y-%m")
            buckets.append((cursor, next_month, label))
            cursor = next_month

        # Waste + GHG + points issued by month (from reward_point_transactions)
        waste_by_month = []
        ghg_by_month = []
        points_issued_by_month = []
        points_redeemed_by_month = []
        budget_by_month = []
        revenue_by_month = []
        new_members_by_month = []

        for (bucket_start, bucket_end, label) in buckets:
            # Waste (kg)
            w = self._sum_weight(organization_id, start=bucket_start, end=bucket_end)
            waste_by_month.append({"month": label, "weight": float(w)})

            # GHG (kg CO2e)
            g = self._sum_ghg(organization_id, start=bucket_start, end=bucket_end)
            ghg_by_month.append({"month": label, "ghg_kg": float(g)})

            # Revenue
            r = self._sum_waste_revenue(organization_id, start=bucket_start, end=bucket_end)
            revenue_by_month.append({"month": label, "revenue": float(r)})

            # Points issued (positive, claim)
            pts_in = float(
                self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
                .filter(
                    RewardPointTransaction.organization_id == organization_id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.points > 0,
                    RewardPointTransaction.claimed_date >= bucket_start,
                    RewardPointTransaction.claimed_date < bucket_end,
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar() or 0
            )
            points_issued_by_month.append({"month": label, "points": pts_in})

            # Points redeemed (abs value of negative redeem)
            pts_out = float(
                self.db.query(func.coalesce(func.sum(-RewardPointTransaction.points), 0))
                .filter(
                    RewardPointTransaction.organization_id == organization_id,
                    RewardPointTransaction.reference_type == "redeem",
                    RewardPointTransaction.points < 0,
                    RewardPointTransaction.claimed_date >= bucket_start,
                    RewardPointTransaction.claimed_date < bucket_end,
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar() or 0
            )
            points_redeemed_by_month.append({"month": label, "points": pts_out})

            # Budget used (cost_baht × qty for completed redemptions in this bucket)
            b = float(
                self.db.query(
                    func.coalesce(
                        func.sum(RewardCatalog.cost_baht * RewardRedemption.quantity), 0
                    )
                )
                .select_from(RewardRedemption)
                .join(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
                .filter(
                    RewardRedemption.organization_id == organization_id,
                    RewardRedemption.status == "completed",
                    RewardRedemption.deleted_date.is_(None),
                    RewardCatalog.cost_baht.isnot(None),
                    RewardRedemption.updated_date >= bucket_start,
                    RewardRedemption.updated_date < bucket_end,
                )
                .scalar() or 0
            )
            budget_by_month.append({"month": label, "budget_used": b})

            # New members in this bucket
            nm = self._scalar_count(
                OrganizationRewardUser,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.created_date >= bucket_start,
                OrganizationRewardUser.created_date < bucket_end,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            new_members_by_month.append({"month": label, "count": nm})

        # Waste by type (all-time, group by activity material)
        waste_by_type_rows = (
            self.db.query(
                RewardActivityMaterial.id.label("material_id"),
                RewardActivityMaterial.name.label("name"),
                func.coalesce(func.sum(RewardPointTransaction.value), 0).label("weight"),
            )
            .select_from(RewardPointTransaction)
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardActivityMaterial.id, RewardActivityMaterial.name)
            .order_by(func.sum(RewardPointTransaction.value).desc())
            .all()
        )
        waste_by_type = [
            {
                "material_id": r.material_id,
                "name": r.name,
                "weight": float(r.weight or 0),
            }
            for r in waste_by_type_rows if r.weight and r.weight > 0
        ]

        return {
            "months": [b[2] for b in buckets],
            "waste_by_month": waste_by_month,
            "ghg_by_month": ghg_by_month,
            "budget_by_month": budget_by_month,
            "revenue_by_month": revenue_by_month,
            "waste_by_type": waste_by_type,
            "points_issued_by_month": points_issued_by_month,
            "points_redeemed_by_month": points_redeemed_by_month,
            "new_members_by_month": new_members_by_month,
        }

    # ================================================================
    # § 7 — Stock Pivot Matrix (catalog × campaign)
    # ================================================================
    def get_stock_matrix(self, organization_id: int) -> list[dict]:
        """Return each catalog item with its total stock + breakdown per campaign.
        Used by Overview § 7 Stock Pivot Table.

        Low-stock flag uses per-item ``RewardCatalog.min_threshold`` (0 = no alert).
        """
        # List all active campaigns in the org (for consistent column ordering)
        campaigns = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .order_by(RewardCampaign.start_date.desc())
            .all()
        )

        # All catalog items in the org
        catalogs = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
            .order_by(RewardCatalog.name.asc())
            .all()
        )

        result = []
        for cat in catalogs:
            # Total stock (all campaigns + global/NULL)
            total = int(
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == cat.id,
                    RewardStock.deleted_date.is_(None),
                )
                .scalar() or 0
            )

            # Stock per campaign
            by_campaign = []
            for c in campaigns:
                stock_in_c = int(
                    self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                    .filter(
                        RewardStock.reward_catalog_id == cat.id,
                        RewardStock.reward_campaign_id == c.id,
                        RewardStock.deleted_date.is_(None),
                    )
                    .scalar() or 0
                )
                by_campaign.append({
                    "campaign_id": c.id,
                    "campaign_name": c.name,
                    "stock": stock_in_c,
                })

            # Stock not assigned to any campaign (global pool)
            global_stock = int(
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == cat.id,
                    RewardStock.reward_campaign_id.is_(None),
                    RewardStock.deleted_date.is_(None),
                )
                .scalar() or 0
            )

            min_thr = cat.min_threshold or 0
            result.append({
                "catalog_id": cat.id,
                "name": cat.name,
                "unit": cat.unit,
                "total": total,
                "global_stock": global_stock,
                "is_low_stock": min_thr > 0 and total < min_thr,
                "min_threshold": min_thr,
                "by_campaign": by_campaign,
            })

        return result

    # ================================================================
    # § 8 — Top Members Leaderboard
    # ================================================================
    def get_top_members(self, organization_id: int, limit: int = 5) -> list[dict]:
        """Return top N members ranked by points earned TODAY (in this org)."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        rows = (
            self.db.query(
                RewardPointTransaction.reward_user_id.label("reward_user_id"),
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("total_points"),
                func.count(RewardPointTransaction.id).label("claims_count"),
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.points > 0,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= today_start,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_user_id)
            .order_by(func.sum(RewardPointTransaction.points).desc())
            .limit(limit)
            .all()
        )

        result = []
        for r in rows:
            # Get user + org membership
            user = self.db.query(RewardUser).filter(RewardUser.id == r.reward_user_id).first()
            org_user = (
                self.db.query(OrganizationRewardUser)
                .filter(
                    OrganizationRewardUser.reward_user_id == r.reward_user_id,
                    OrganizationRewardUser.organization_id == organization_id,
                    OrganizationRewardUser.deleted_date.is_(None),
                )
                .first()
            )
            name = None
            if user:
                name = user.display_name or user.line_display_name
            if not name:
                name = f"User #{r.reward_user_id}"
            result.append({
                "reward_user_id": r.reward_user_id,
                "org_reward_user_id": org_user.id if org_user else None,
                "display_name": name,
                "line_picture_url": user.line_picture_url if user else None,
                "total_points": float(r.total_points or 0),
                "claims_count": int(r.claims_count or 0),
                "scope": "today",
            })
        return result

    # ================================================================
    # Helpers
    # ================================================================
    def _scalar_count(self, model, *filters) -> int:
        return int(
            self.db.query(func.count(model.id)).filter(*filters).scalar() or 0
        )

    def _sum_weight(self, organization_id: int, start, end) -> float:
        q = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.value), 0))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= start)
        if end is not None:
            q = q.filter(RewardPointTransaction.claimed_date < end)
        return float(q.scalar() or 0)

    def _sum_ghg(self, organization_id: int, start, end) -> float:
        """GHG in kg CO2e."""
        q = (
            self.db.query(
                func.coalesce(
                    func.sum(RewardPointTransaction.value * RewardActivityMaterial.ghg_factor),
                    0,
                )
            )
            .select_from(RewardPointTransaction)
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardActivityMaterial.ghg_factor.isnot(None),
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= start)
        if end is not None:
            q = q.filter(RewardPointTransaction.claimed_date < end)
        return float(q.scalar() or 0)

    def _sum_waste_revenue(self, organization_id: int, start, end) -> float:
        q = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        RewardPointTransaction.value * RewardActivityMaterial.selling_price_per_kg
                    ),
                    0,
                )
            )
            .select_from(RewardPointTransaction)
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardActivityMaterial.selling_price_per_kg.isnot(None),
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= start)
        if end is not None:
            q = q.filter(RewardPointTransaction.claimed_date < end)
        return float(q.scalar() or 0)
