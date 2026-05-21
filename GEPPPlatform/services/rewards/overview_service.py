"""
Overview Service - Dashboard statistics for reward programs
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, distinct, and_, case
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    OrganizationRewardUser, RewardRedemption, RewardUser, Droppoint,
)
from ...models.rewards.management import (
    RewardCampaign, RewardActivityMaterial, RewardSetup,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.catalog import RewardCatalog, RewardStock
# [V3-OVERVIEW] GHG source-of-truth: materials.calc_ghg — NOT reward_activity_materials.ghg_factor
# (the latter is a denormalized column that was never populated by the create/update flow).
# All GHG aggregations join through RewardActivityMaterial.material_id → Material.calc_ghg.
from ...models.cores.references import Material
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
    def get_stats(
        self,
        organization_id: int,
        date_from=None,
        date_to=None,
        campaign_id: int | None = None,
    ) -> dict:
        """Return KPI data for the 8 cards in Overview Section 2.

        Row 1 (Operations): campaigns, members, weight, GHG
        Row 2 (Financial): points issued, budget used, waste revenue, profit/loss
        Plus fields needed by other sections (pending redemptions, etc.)

        Optional filters (all backward-compatible — None preserves prior behavior):
        - date_from / date_to: ISO date strings or datetimes; scope aggregates to that window
        - campaign_id: scope every aggregate to a single campaign
        """
        now = datetime.now(timezone.utc)
        this_month_start, last_month_start = _month_boundaries(now)
        week_ago = now - timedelta(days=7)

        date_from_dt = self._parse_iso(date_from)
        date_to_dt = self._parse_iso(date_to)

        # ── Members ──
        # When campaign_id set: count distinct participants in that campaign within range.
        # When unset: count all OrganizationRewardUser rows (current behavior).
        if campaign_id is not None:
            mq = (
                self.db.query(func.count(distinct(RewardPointTransaction.reward_user_id)))
                .filter(
                    RewardPointTransaction.organization_id == organization_id,
                    RewardPointTransaction.reward_campaign_id == campaign_id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
            )
            if date_from_dt is not None:
                mq = mq.filter(RewardPointTransaction.claimed_date >= date_from_dt)
            if date_to_dt is not None:
                mq = mq.filter(RewardPointTransaction.claimed_date <= date_to_dt)
            total_members = int(mq.scalar() or 0)
        else:
            mfilters = [
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            ]
            if date_from_dt is not None:
                mfilters.append(OrganizationRewardUser.created_date >= date_from_dt)
            if date_to_dt is not None:
                mfilters.append(OrganizationRewardUser.created_date <= date_to_dt)
            total_members = self._scalar_count(OrganizationRewardUser, *mfilters)
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
        # When a single campaign is filter-selected, total/active reduce to that one.
        if campaign_id is not None:
            c = (
                self.db.query(RewardCampaign)
                .filter(
                    RewardCampaign.organization_id == organization_id,
                    RewardCampaign.id == campaign_id,
                    RewardCampaign.deleted_date.is_(None),
                )
                .first()
            )
            total_campaigns = 1 if c else 0
            active_campaigns = 1 if (c and c.status == "active") else 0
        else:
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
            organization_id, start=date_from_dt, end=date_to_dt, campaign_id=campaign_id,
        )
        total_weight_this_month = self._sum_weight(
            organization_id, start=this_month_start, end=None, campaign_id=campaign_id,
        )
        total_weight_last_month = self._sum_weight(
            organization_id, start=last_month_start, end=this_month_start, campaign_id=campaign_id,
        )

        # ── GHG (kg CO2e) ── value × materials.calc_ghg (join activity_materials → materials)
        total_ghg_all_time = self._sum_ghg(
            organization_id, start=date_from_dt, end=date_to_dt, campaign_id=campaign_id,
        )
        total_ghg_this_month = self._sum_ghg(
            organization_id, start=this_month_start, end=None, campaign_id=campaign_id,
        )
        total_ghg_last_month = self._sum_ghg(
            organization_id, start=last_month_start, end=this_month_start, campaign_id=campaign_id,
        )

        # ── Points ──
        pi_q = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.points > 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if date_from_dt is not None:
            pi_q = pi_q.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt is not None:
            pi_q = pi_q.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        if campaign_id is not None:
            pi_q = pi_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        total_points_issued = float(pi_q.scalar() or 0)

        pr_q = (
            self.db.query(func.coalesce(func.sum(-RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "redeem",
                RewardPointTransaction.points < 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if date_from_dt is not None:
            pr_q = pr_q.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt is not None:
            pr_q = pr_q.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        if campaign_id is not None:
            pr_q = pr_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        total_points_redeemed = float(pr_q.scalar() or 0)

        # [V3-CAMPAIGN-RATE] Weighted total_redemption_value_baht — each redemption is
        # multiplied by its campaign's own rate (falling back to org rate). Pre-computed
        # so KPI #3 on Overview doesn't have to guess which rate to use when campaigns differ.
        # Resolve org-level rate (used as fallback for campaigns that don't set their own).
        org_setup_for_rate = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )
        if org_setup_for_rate and org_setup_for_rate.point_to_baht_rate is not None:
            fallback_rate = float(org_setup_for_rate.point_to_baht_rate)
        elif org_setup_for_rate and org_setup_for_rate.cost_per_point is not None:
            fallback_rate = float(org_setup_for_rate.cost_per_point)
        else:
            fallback_rate = 0.0

        per_campaign_redeem_q = (
            self.db.query(
                RewardPointTransaction.reward_campaign_id.label("campaign_id"),
                func.coalesce(func.sum(-RewardPointTransaction.points), 0).label("pts"),
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "redeem",
                RewardPointTransaction.points < 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if date_from_dt is not None:
            per_campaign_redeem_q = per_campaign_redeem_q.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt is not None:
            per_campaign_redeem_q = per_campaign_redeem_q.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        if campaign_id is not None:
            per_campaign_redeem_q = per_campaign_redeem_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        per_campaign_rows = per_campaign_redeem_q.group_by(RewardPointTransaction.reward_campaign_id).all()

        campaign_ids_for_rate = [r.campaign_id for r in per_campaign_rows if r.campaign_id is not None]
        campaign_rate_map: dict[int, float] = {}
        if campaign_ids_for_rate:
            for c in (
                self.db.query(RewardCampaign.id, RewardCampaign.point_to_baht_rate)
                .filter(RewardCampaign.id.in_(campaign_ids_for_rate))
                .all()
            ):
                if c.point_to_baht_rate is not None:
                    campaign_rate_map[c.id] = float(c.point_to_baht_rate)

        total_redemption_value_baht = 0.0
        for r in per_campaign_rows:
            pts = float(r.pts or 0)
            rate = campaign_rate_map.get(r.campaign_id, fallback_rate)
            total_redemption_value_baht += pts * rate

        # ── Redemptions ──
        red_filters = [
            RewardRedemption.organization_id == organization_id,
            RewardRedemption.deleted_date.is_(None),
        ]
        if date_from_dt is not None:
            red_filters.append(RewardRedemption.created_date >= date_from_dt)
        if date_to_dt is not None:
            red_filters.append(RewardRedemption.created_date <= date_to_dt)
        if campaign_id is not None:
            red_filters.append(RewardRedemption.reward_campaign_id == campaign_id)
        total_redemptions = self._scalar_count(RewardRedemption, *red_filters)
        pending_redemptions = self._scalar_count(
            RewardRedemption,
            *red_filters,
            RewardRedemption.status == "inprogress",
        )

        # ── Financial: Reward budget used ──
        # SUM(catalog.cost_baht × redemption.quantity) for completed redemptions
        bu_q = (
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
        )
        if date_from_dt is not None:
            bu_q = bu_q.filter(RewardRedemption.updated_date >= date_from_dt)
        if date_to_dt is not None:
            bu_q = bu_q.filter(RewardRedemption.updated_date <= date_to_dt)
        if campaign_id is not None:
            bu_q = bu_q.filter(RewardRedemption.reward_campaign_id == campaign_id)
        reward_budget_used = float(bu_q.scalar() or 0)

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
        waste_revenue_total = self._sum_waste_revenue(
            organization_id, start=date_from_dt, end=date_to_dt, campaign_id=campaign_id,
        )
        waste_revenue_this_month = self._sum_waste_revenue(
            organization_id, start=this_month_start, end=None, campaign_id=campaign_id,
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
            # [V3-CAMPAIGN-RATE] Sum of (redeemed_pts × campaign_rate) — each redemption
            # uses its own campaign's rate (org rate as fallback). Use this directly in
            # Overview KPI #3 instead of multiplying total_points_redeemed by org rate.
            "total_redemption_value_baht": round(total_redemption_value_baht, 2),
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
    def get_campaign_details(
        self,
        organization_id: int,
        date_from=None,
        date_to=None,
    ) -> list[dict]:
        """Per-campaign metrics for campaigns active within a date range.

        Filter (backward-compatible):
        - date_from / date_to: when supplied, include campaigns whose run window
          (start_date .. end_date) overlaps the requested range. When unsupplied,
          include all currently-active campaigns (legacy behavior).
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        date_from_dt = self._parse_iso(date_from)
        date_to_dt = self._parse_iso(date_to)

        cq = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
        )
        if date_from_dt is not None or date_to_dt is not None:
            # Range overlap: campaign.start_date <= date_to AND
            #                (campaign.end_date IS NULL OR campaign.end_date >= date_from)
            if date_to_dt is not None:
                cq = cq.filter(RewardCampaign.start_date <= date_to_dt)
            if date_from_dt is not None:
                cq = cq.filter(
                    (RewardCampaign.end_date.is_(None))
                    | (RewardCampaign.end_date >= date_from_dt)
                )
        else:
            # Legacy: only currently-active campaigns
            cq = cq.filter(RewardCampaign.status == "active")
        campaigns = cq.order_by(RewardCampaign.start_date.desc()).all()

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

            # GHG saved (kg CO2e) for this campaign
            # [V3-OVERVIEW] Source of truth = materials.calc_ghg (joined via material_id).
            ghg_kg = float(
                self.db.query(
                    func.coalesce(
                        func.sum(RewardPointTransaction.value * Material.calc_ghg),
                        0,
                    )
                )
                .select_from(RewardPointTransaction)
                .join(
                    RewardActivityMaterial,
                    RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
                )
                .join(
                    Material,
                    Material.id == RewardActivityMaterial.material_id,
                )
                .filter(
                    RewardPointTransaction.reward_campaign_id == c.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardActivityMaterial.type == "material",
                    Material.calc_ghg.isnot(None),
                    Material.calc_ghg > 0,
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
    def get_staff_today(
        self,
        organization_id: int,
        date_from=None,
        date_to=None,
        campaign_id: int | None = None,
    ) -> list[dict]:
        """All staff in the org, with claim activity within a date window.

        When date_from / date_to are unsupplied, defaults to "today" (legacy behavior).
        When supplied, "claims_today" / "weight_today" reflect the supplied range.
        When campaign_id is set, scope to that campaign only.

        online = has ≥1 claim within the window
        offline = no claim within the window; show last_active
        """
        now = datetime.now(timezone.utc)

        date_from_dt = self._parse_iso(date_from)
        date_to_dt = self._parse_iso(date_to)

        # Defaults: today window when no explicit range given (backward-compat)
        if date_from_dt is None and date_to_dt is None:
            window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = None
        else:
            window_start = date_from_dt
            window_end = date_to_dt

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
            # Activity within window
            tq = (
                self.db.query(
                    func.count(RewardPointTransaction.id).label("claims"),
                    func.coalesce(func.sum(RewardPointTransaction.value), 0).label("weight"),
                    func.max(RewardPointTransaction.droppoint_id).label("droppoint_id"),
                )
                .filter(
                    RewardPointTransaction.staff_id == oru.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
            )
            if window_start is not None:
                tq = tq.filter(RewardPointTransaction.claimed_date >= window_start)
            if window_end is not None:
                tq = tq.filter(RewardPointTransaction.claimed_date <= window_end)
            if campaign_id is not None:
                tq = tq.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
            today = tq.first()
            claims_today = int(today.claims or 0) if today else 0
            weight_today = float(today.weight or 0) if today else 0.0
            droppoint_id = today.droppoint_id if today else None

            # Last active (most recent claim ever, ignoring window)
            lq = (
                self.db.query(func.max(RewardPointTransaction.claimed_date))
                .filter(
                    RewardPointTransaction.staff_id == oru.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
            )
            if campaign_id is not None:
                lq = lq.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
            last = lq.scalar()

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
    # § Phase 2 — Drop Point Breakdown (Material kg / Activity count)
    # ================================================================
    def get_dropoint_breakdown(
        self,
        organization_id: int,
        metric: str = "material",
        campaign_id: int | None = None,
        date_from=None,
        date_to=None,
    ) -> dict:
        """Phase 2 endpoint powering the 2 Drop Point Breakdown cards on Overview.

        - metric='material': sum of weight (kg) per droppoint, broken down by material name.
        - metric='activity': count of activity-type claims per droppoint.

        If campaign_id provided, scope to that campaign only; otherwise aggregate all
        active campaigns. Filter by activity_material.type (Phase 4A: campaigns no
        longer carry metric_type — claims do). Optional date_from/date_to scopes to that
        window (claim.claimed_date).
        """
        if metric not in ("material", "activity"):
            metric = "material"

        date_from_dt = self._parse_iso(date_from)
        date_to_dt = self._parse_iso(date_to)

        # Resolve eligible campaigns (no metric filter — campaigns are mixed)
        eligible_q = self.db.query(RewardCampaign.id).filter(
            RewardCampaign.organization_id == organization_id,
            RewardCampaign.deleted_date.is_(None),
        )
        if campaign_id is not None:
            eligible_q = eligible_q.filter(RewardCampaign.id == campaign_id)
        eligible_ids = [row.id for row in eligible_q.all()]
        if not eligible_ids:
            return {
                "metric": metric,
                "campaigns": [],
                "rows": [],
            }

        # Build the aggregate query — common skeleton, varies by metric
        agg_expr = (
            func.coalesce(func.sum(RewardPointTransaction.value), 0)
            if metric == "material"
            else func.count(RewardPointTransaction.id)
        )
        bq = (
            self.db.query(
                RewardPointTransaction.droppoint_id.label("droppoint_id"),
                RewardActivityMaterial.id.label("material_id"),
                RewardActivityMaterial.name.label("material_name"),
                agg_expr.label("total"),
            )
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.reward_campaign_id.in_(eligible_ids),
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
                RewardActivityMaterial.type == metric,
            )
        )
        if date_from_dt is not None:
            bq = bq.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt is not None:
            bq = bq.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        rows = (
            bq.group_by(
                RewardPointTransaction.droppoint_id,
                RewardActivityMaterial.id,
                RewardActivityMaterial.name,
            ).all()
        )

        # [V3-OVERVIEW] Points per droppoint — overlaid on the breakdown chart so that
        # the location view (chart in BigTrendChart) can show 2 stacked bars per droppoint:
        # top bar = material/activity (in kg/ครั้ง), bottom bar = points issued+redeemed (in PT).
        pq = (
            self.db.query(
                RewardPointTransaction.droppoint_id.label("dp"),
                func.coalesce(
                    func.sum(case(
                        (and_(
                            RewardPointTransaction.reference_type == "claim",
                            RewardPointTransaction.points > 0,
                        ), RewardPointTransaction.points),
                        else_=0,
                    )),
                    0,
                ).label("issued"),
                func.coalesce(
                    func.sum(case(
                        (and_(
                            RewardPointTransaction.reference_type == "redeem",
                            RewardPointTransaction.points < 0,
                        ), -RewardPointTransaction.points),
                        else_=0,
                    )),
                    0,
                ).label("redeemed"),
            )
            .filter(
                RewardPointTransaction.reward_campaign_id.in_(eligible_ids),
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if date_from_dt is not None:
            pq = pq.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt is not None:
            pq = pq.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        points_rows = pq.group_by(RewardPointTransaction.droppoint_id).all()
        points_by_dp: dict[int | None, tuple[float, float]] = {
            r.dp: (float(r.issued or 0), float(r.redeemed or 0)) for r in points_rows
        }

        # Resolve droppoint names — union of dp_ids from both queries
        dp_ids: set[int] = {r.droppoint_id for r in rows if r.droppoint_id}
        for pr in points_rows:
            if pr.dp:
                dp_ids.add(pr.dp)
        dp_names: dict[int, str] = {}
        if dp_ids:
            for dp in self.db.query(Droppoint).filter(Droppoint.id.in_(dp_ids)).all():
                dp_names[dp.id] = dp.name

        # Group: { droppoint_id → { droppoint_name, total, by_material: [...] } }
        grouped: dict[int | None, dict] = {}
        for r in rows:
            dp_id = r.droppoint_id
            bucket = grouped.setdefault(dp_id, {
                "droppoint_id": dp_id,
                "droppoint_name": dp_names.get(dp_id) if dp_id else "ไม่ระบุจุดรับ",
                "total": 0.0,
                "by_material": [],
                "points_issued": 0.0,
                "points_redeemed": 0.0,
            })
            value = float(r.total or 0)
            bucket["total"] += value
            bucket["by_material"].append({
                "material_id": r.material_id,
                "material_name": r.material_name or "อื่น ๆ",
                "value": value,
            })

        # Inject points into existing buckets + add droppoints that have only points (no material/activity rows in this window)
        for dp_id, (issued, redeemed) in points_by_dp.items():
            if dp_id in grouped:
                grouped[dp_id]["points_issued"] = issued
                grouped[dp_id]["points_redeemed"] = redeemed
            elif issued > 0 or redeemed > 0:
                grouped[dp_id] = {
                    "droppoint_id": dp_id,
                    "droppoint_name": dp_names.get(dp_id) if dp_id else "ไม่ระบุจุดรับ",
                    "total": 0.0,
                    "by_material": [],
                    "points_issued": issued,
                    "points_redeemed": redeemed,
                }

        # Sort each droppoint's materials by value desc, droppoints by total desc (then by points if total ties)
        result_rows = list(grouped.values())
        for row in result_rows:
            row["by_material"].sort(key=lambda x: -x["value"])
        result_rows.sort(key=lambda x: (-x["total"], -(x.get("points_issued") or 0)))

        # Eligible campaigns metadata (for client-side dropdown)
        campaign_meta = (
            self.db.query(RewardCampaign.id, RewardCampaign.name)
            .filter(RewardCampaign.id.in_(eligible_ids))
            .all()
        )
        campaigns_payload = [{"id": c.id, "name": c.name} for c in campaign_meta]

        return {
            "metric": metric,
            "unit": "kg" if metric == "material" else "times",
            "campaigns": campaigns_payload,
            "rows": result_rows,
        }

    # ================================================================
    # § 5 — Trends (6-month time-series) + § 6 Environmental Impact
    # ================================================================
    def get_trends(
        self,
        organization_id: int,
        months: int = 6,
        date_from=None,
        date_to=None,
        campaign_id: int | None = None,
    ) -> dict:
        """Return monthly aggregates for the chart series.

        Charts covered:
        - Chart 1 (dual-axis): waste_by_month + ghg_by_month
        - Chart 2 (stacked):   budget_by_month + revenue_by_month
        - Chart 3 (donut):     waste_by_type
        - Chart 4 (dual-line): points_issued_by_month + points_redeemed_by_month
        - Chart 5 (bar):       new_members_by_month
        - New (V3-OVERVIEW):   activity_count_by_month (count of activity-type claims)

        Filters (all backward-compatible):
        - months: when no date_from/date_to is supplied, defines window length (default 6)
        - date_from / date_to: ISO date strings; when supplied, month buckets span this range
        - campaign_id: scope every series to a single campaign
        """
        now = datetime.now(timezone.utc)

        date_from_dt = self._parse_iso(date_from)
        date_to_dt = self._parse_iso(date_to)

        # ── Determine window for month buckets ──
        # Priority: explicit date range > months window
        if date_from_dt is not None or date_to_dt is not None:
            # Use the supplied range; clamp to month boundaries
            window_end = date_to_dt or now
            window_end_month = window_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # advance to the first day of the NEXT month so the bucket containing date_to is included
            if window_end.month == 12:
                window_end_next = window_end_month.replace(year=window_end_month.year + 1, month=1)
            else:
                window_end_next = window_end_month.replace(month=window_end_month.month + 1)

            window_start = date_from_dt or window_end_next - timedelta(days=180)
            start = window_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            cursor = start
            buckets: list[tuple[datetime, datetime, str]] = []
            while cursor < window_end_next:
                if cursor.month == 12:
                    nxt = cursor.replace(year=cursor.year + 1, month=1)
                else:
                    nxt = cursor.replace(month=cursor.month + 1)
                buckets.append((cursor, nxt, cursor.strftime("%Y-%m")))
                cursor = nxt
        else:
            # Legacy: walk back `months - 1` from the current month
            this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start = this_month_start
            for _ in range(months - 1):
                start = (start - timedelta(days=1)).replace(day=1)
            buckets = []
            cursor = start
            for _ in range(months):
                if cursor.month == 12:
                    next_month = cursor.replace(year=cursor.year + 1, month=1)
                else:
                    next_month = cursor.replace(month=cursor.month + 1)
                buckets.append((cursor, next_month, cursor.strftime("%Y-%m")))
                cursor = next_month

        # Waste + GHG + points issued by month (from reward_point_transactions)
        waste_by_month = []
        ghg_by_month = []
        points_issued_by_month = []
        points_redeemed_by_month = []
        activity_count_by_month = []
        budget_by_month = []
        revenue_by_month = []
        new_members_by_month = []

        for (bucket_start, bucket_end, label) in buckets:
            # Waste (kg)
            w = self._sum_weight(
                organization_id, start=bucket_start, end=bucket_end, campaign_id=campaign_id,
            )
            waste_by_month.append({"month": label, "weight": float(w)})

            # GHG (kg CO2e)
            g = self._sum_ghg(
                organization_id, start=bucket_start, end=bucket_end, campaign_id=campaign_id,
            )
            ghg_by_month.append({"month": label, "ghg_kg": float(g)})

            # Revenue
            r = self._sum_waste_revenue(
                organization_id, start=bucket_start, end=bucket_end, campaign_id=campaign_id,
            )
            revenue_by_month.append({"month": label, "revenue": float(r)})

            # Activity count (claims tied to ActivityMaterials of type='activity')
            ac = self._count_activity_claims(
                organization_id, start=bucket_start, end=bucket_end, campaign_id=campaign_id,
            )
            activity_count_by_month.append({"month": label, "count": int(ac)})

            # Points issued (positive, claim)
            pi_q = (
                self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
                .filter(
                    RewardPointTransaction.organization_id == organization_id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.points > 0,
                    RewardPointTransaction.claimed_date >= bucket_start,
                    RewardPointTransaction.claimed_date < bucket_end,
                    RewardPointTransaction.deleted_date.is_(None),
                )
            )
            if campaign_id is not None:
                pi_q = pi_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
            pts_in = float(pi_q.scalar() or 0)
            points_issued_by_month.append({"month": label, "points": pts_in})

            # Points redeemed (abs value of negative redeem)
            pr_q = (
                self.db.query(func.coalesce(func.sum(-RewardPointTransaction.points), 0))
                .filter(
                    RewardPointTransaction.organization_id == organization_id,
                    RewardPointTransaction.reference_type == "redeem",
                    RewardPointTransaction.points < 0,
                    RewardPointTransaction.claimed_date >= bucket_start,
                    RewardPointTransaction.claimed_date < bucket_end,
                    RewardPointTransaction.deleted_date.is_(None),
                )
            )
            if campaign_id is not None:
                pr_q = pr_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
            pts_out = float(pr_q.scalar() or 0)
            points_redeemed_by_month.append({"month": label, "points": pts_out})

            # Budget used (cost_baht × qty for completed redemptions in this bucket)
            bu_q = (
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
            )
            if campaign_id is not None:
                bu_q = bu_q.filter(RewardRedemption.reward_campaign_id == campaign_id)
            b = float(bu_q.scalar() or 0)
            budget_by_month.append({"month": label, "budget_used": b})

            # New members in this bucket — not campaign-scoped
            nm = self._scalar_count(
                OrganizationRewardUser,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.created_date >= bucket_start,
                OrganizationRewardUser.created_date < bucket_end,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            new_members_by_month.append({"month": label, "count": nm})

        # Waste by type (group by activity material) — also respects filter
        wbt_q = (
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
        )
        if date_from_dt is not None:
            wbt_q = wbt_q.filter(RewardPointTransaction.claimed_date >= date_from_dt)
        if date_to_dt is not None:
            wbt_q = wbt_q.filter(RewardPointTransaction.claimed_date <= date_to_dt)
        if campaign_id is not None:
            wbt_q = wbt_q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        waste_by_type_rows = (
            wbt_q
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
            "activity_count_by_month": activity_count_by_month,
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
    def get_top_members(
        self,
        organization_id: int,
        limit: int = 5,
        date_from=None,
        date_to=None,
        campaign_id: int | None = None,
    ) -> list[dict]:
        """Return top N members ranked by points earned in a window.

        When no date range supplied, defaults to "today" (legacy behavior).
        When campaign_id supplied, scope to that campaign only.
        """
        now = datetime.now(timezone.utc)

        date_from_dt = self._parse_iso(date_from)
        date_to_dt = self._parse_iso(date_to)

        if date_from_dt is None and date_to_dt is None:
            window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = None
            scope_label = "today"
        else:
            window_start = date_from_dt
            window_end = date_to_dt
            scope_label = "range"

        q = (
            self.db.query(
                RewardPointTransaction.reward_user_id.label("reward_user_id"),
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("total_points"),
                func.count(RewardPointTransaction.id).label("claims_count"),
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.points > 0,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if window_start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= window_start)
        if window_end is not None:
            q = q.filter(RewardPointTransaction.claimed_date <= window_end)
        if campaign_id is not None:
            q = q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)

        rows = (
            q.group_by(RewardPointTransaction.reward_user_id)
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
                "scope": scope_label,
            })
        return result

    # ================================================================
    # Helpers
    # ================================================================
    def _scalar_count(self, model, *filters) -> int:
        return int(
            self.db.query(func.count(model.id)).filter(*filters).scalar() or 0
        )

    def _sum_weight(self, organization_id: int, start, end, campaign_id=None) -> float:
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
        if campaign_id is not None:
            q = q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        return float(q.scalar() or 0)

    def _sum_ghg(self, organization_id: int, start, end, campaign_id=None) -> float:
        """GHG in kg CO2e.

        [V3-OVERVIEW] Source of truth: `materials.calc_ghg` (entered by admins via the
        main Materials UI in the V3 core system). We join through
        `RewardActivityMaterial.material_id → Material.id` to read it. Activity-type
        ActivityMaterials (no `material_id`) yield no GHG by design.
        """
        q = (
            self.db.query(
                func.coalesce(
                    func.sum(RewardPointTransaction.value * Material.calc_ghg),
                    0,
                )
            )
            .select_from(RewardPointTransaction)
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .join(
                Material,
                Material.id == RewardActivityMaterial.material_id,
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardActivityMaterial.type == "material",
                Material.calc_ghg.isnot(None),
                Material.calc_ghg > 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= start)
        if end is not None:
            q = q.filter(RewardPointTransaction.claimed_date < end)
        if campaign_id is not None:
            q = q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        return float(q.scalar() or 0)

    def _sum_waste_revenue(self, organization_id: int, start, end, campaign_id=None) -> float:
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
        if campaign_id is not None:
            q = q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        return float(q.scalar() or 0)

    def _count_activity_claims(self, organization_id: int, start, end, campaign_id=None) -> int:
        """Count of claim transactions tied to ActivityMaterials of type='activity'.
        Used as the 'activity_count' chart metric series on the Overview trend chart.
        """
        q = (
            self.db.query(func.count(RewardPointTransaction.id))
            .select_from(RewardPointTransaction)
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
                RewardActivityMaterial.type == "activity",
            )
        )
        if start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= start)
        if end is not None:
            q = q.filter(RewardPointTransaction.claimed_date < end)
        if campaign_id is not None:
            q = q.filter(RewardPointTransaction.reward_campaign_id == campaign_id)
        return int(q.scalar() or 0)

    def _parse_iso(self, value):
        """Parse ISO date string (YYYY-MM-DD or full ISO timestamp) to aware datetime.
        Returns None if value is falsy.
        """
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        s = str(value).strip()
        if not s:
            return None
        # Common shapes: 2026-05-20, 2026-05-20T00:00:00, 2026-05-20T00:00:00Z
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            # Fallback: just date
            try:
                dt = datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
