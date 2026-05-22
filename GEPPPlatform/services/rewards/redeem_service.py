"""
Redeem Service - User redeeming rewards from catalog
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, distinct, or_
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardActivityMaterial,
    RewardCampaign,
    RewardCampaignCatalog,
)
from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import RewardRedemption, OrganizationRewardUser
from ...exceptions import NotFoundException, BadRequestException


# ─────────────────────────────────────────────────────────────────────────
# Gamification constants — kept in this module so backend is the single
# source of truth. Frontend mirrors these via API response.
# ─────────────────────────────────────────────────────────────────────────
RANK_LEVELS = [
    {"level": 1, "tier_name": "เมล็ดพันธุ์", "emoji": "🌱", "min_kg": 0.0},
    {"level": 2, "tier_name": "ต้นกล้า",     "emoji": "🌿", "min_kg": 10.0},
    {"level": 3, "tier_name": "ต้นไม้",      "emoji": "🌳", "min_kg": 50.0},
    {"level": 4, "tier_name": "ป่าใหญ่",     "emoji": "🌲", "min_kg": 200.0},
    {"level": 5, "tier_name": "ผู้พิทักษ์",  "emoji": "🏔️", "min_kg": 500.0},
]

# GHG factors (kg CO2e per kg of material). Mirrors frontend ghg-calculator.ts
# DEFAULT_GHG_FACTORS so cross-stack calculation matches.
GHG_FACTORS = {
    "pet": 1.5,
    "hdpe": 1.4,
    "aluminum": 9.0,
    "paper": 0.9,
    "glass": 0.3,
    "general": 1.5,
}

# Trees: 1 tree absorbs ~22 kg CO2e per year
# Driving: 0.21 kg CO2e per km (avg passenger car)
GHG_TO_TREES = 22.0
GHG_TO_KM = 0.21


def _is_weight_unit(unit) -> bool:
    if not unit:
        return False
    u = str(unit).lower()
    return (
        u in ("kg", "kgs", "kilogram", "kilograms")
        or "กก" in u
        or "กิโล" in u
    )


def _estimate_ghg_per_kg(name) -> float:
    """Estimate GHG factor from material name (case-insensitive substring match)."""
    if not name:
        return GHG_FACTORS["general"]
    key = str(name).lower()
    if "pet" in key:
        return GHG_FACTORS["pet"]
    if "hdpe" in key:
        return GHG_FACTORS["hdpe"]
    if "alumin" in key or "อลูม" in key:
        return GHG_FACTORS["aluminum"]
    if "paper" in key or "กระดาษ" in key:
        return GHG_FACTORS["paper"]
    if "glass" in key or "แก้ว" in key:
        return GHG_FACTORS["glass"]
    return GHG_FACTORS["general"]


def _get_rank(kg: float) -> dict:
    """Return rank dict for a lifetime kg total. Mirrors getUserRank() in
    gamification.ts but produces backend response shape."""
    kg = max(0.0, float(kg))
    current_idx = 0
    for i in range(len(RANK_LEVELS) - 1, -1, -1):
        if kg >= RANK_LEVELS[i]["min_kg"]:
            current_idx = i
            break
    current = RANK_LEVELS[current_idx]
    next_tier = RANK_LEVELS[current_idx + 1] if current_idx + 1 < len(RANK_LEVELS) else None
    if not next_tier:
        return {
            "level": current["level"],
            "tier_name": current["tier_name"],
            "emoji": current["emoji"],
            "min_kg": current["min_kg"],
            "next_min_kg": None,
            "progress_pct": 100,
            "kg_to_next": 0.0,
        }
    span = next_tier["min_kg"] - current["min_kg"]
    gained = kg - current["min_kg"]
    progress_pct = min(100, max(0, round((gained / span) * 100))) if span > 0 else 0
    kg_to_next = round((next_tier["min_kg"] - kg) * 10) / 10
    return {
        "level": current["level"],
        "tier_name": current["tier_name"],
        "emoji": current["emoji"],
        "min_kg": current["min_kg"],
        "next_min_kg": next_tier["min_kg"],
        "progress_pct": progress_pct,
        "kg_to_next": kg_to_next,
    }


def _iso_week_key(d) -> str:
    """ISO-week key (Asia/Bangkok). datetime → 'YYYY-W##'."""
    from datetime import timedelta as _td
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    # Convert to UTC+7
    bkk = d + _td(hours=7) - _td(hours=0 if d.utcoffset() is None else int(d.utcoffset().total_seconds() / 3600))
    year, week, _ = bkk.isocalendar()
    return f"{year}-W{week:02d}"


def _prev_week_key(key: str) -> str:
    from datetime import date as _date, timedelta as _td
    year_str, week_str = key.split("-W")
    year, week = int(year_str), int(week_str)
    # Anchor to Monday of that week then subtract 7 days
    monday = _date.fromisocalendar(year, week, 1) - _td(days=7)
    py, pw, _ = monday.isocalendar()
    return f"{py}-W{pw:02d}"


def _calc_streak_weekly(claim_dates: list) -> dict:
    """Consecutive ISO weeks with ≥1 claim. Mirrors calculateStreak() in
    gamification.ts but week-only."""
    if not claim_dates:
        return {
            "current": 0,
            "longest": 0,
            "is_active_this_period": False,
            "last_claim_date": None,
        }
    sorted_dates = sorted(claim_dates, reverse=True)
    last = sorted_dates[0]
    buckets = set(_iso_week_key(d) for d in claim_dates)
    now = datetime.now(timezone.utc)
    now_key = _iso_week_key(now)
    is_active = now_key in buckets
    anchor = now_key if is_active else _prev_week_key(now_key)
    current = 0
    if anchor in buckets:
        while anchor in buckets:
            current += 1
            anchor = _prev_week_key(anchor)
    # Longest
    sorted_keys = sorted(buckets)
    longest = 0
    run = 0
    prev_k = None
    for k in sorted_keys:
        if prev_k is None or _prev_week_key(k) == prev_k:
            run += 1
        else:
            run = 1
        if run > longest:
            longest = run
        prev_k = k
    return {
        "current": current,
        "longest": longest,
        "is_active_this_period": is_active,
        "last_claim_date": last.isoformat() if hasattr(last, "isoformat") else last,
    }


class RedeemService:
    """Handles user redeeming rewards."""

    def __init__(self, db: Session):
        self.db = db

    def submit_redemption(
        self,
        reward_user_id: int,
        organization_id: int,
        campaign_id: int,
        items: list[dict],
    ) -> dict:
        """
        Submit a redemption request.
        items = [{"catalog_id": int, "quantity": int}, ...]
        """
        if not items:
            raise BadRequestException("At least one item is required")

        # 0. Verify campaign is active AND not past end_date (ended = computed)
        now = datetime.now(timezone.utc)
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == campaign_id,
                RewardCampaign.status == "active",
                or_(RewardCampaign.end_date.is_(None), RewardCampaign.end_date >= now),
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise BadRequestException("Campaign not active, ended, or not found")

        # [V3] Block redemptions for members whose org membership is deactivated.
        # Mirrors the same guard in claim_service.claim_points so the "Active" toggle on
        # the admin Members tab actually freezes the user's account end-to-end.
        membership = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not membership:
            raise BadRequestException("Member is not registered with this organization")
        if not membership.is_active:
            raise BadRequestException("Member account is deactivated — contact admin to reactivate")

        # 1. Lock the user's point rows for this campaign to prevent concurrent overdraw,
        #    then calculate balance. FOR UPDATE cannot be used with aggregate functions,
        #    so we lock first, then SUM separately.
        self.db.query(RewardPointTransaction.id).filter(
            RewardPointTransaction.reward_user_id == reward_user_id,
            RewardPointTransaction.organization_id == organization_id,
            RewardPointTransaction.reward_campaign_id == campaign_id,
            RewardPointTransaction.deleted_date.is_(None),
        ).with_for_update().all()

        available_points = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reward_campaign_id == campaign_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        )
        available_points = Decimal(str(available_points))

        total_cost = Decimal("0")
        redemption_items = []

        for item in items:
            catalog_id = item.get("catalog_id")
            quantity = item.get("quantity", 1)

            if not catalog_id or quantity <= 0:
                raise BadRequestException("Each item requires catalog_id and positive quantity")

            # 2a. Get campaign catalog link
            campaign_catalog = (
                self.db.query(RewardCampaignCatalog)
                .filter(
                    RewardCampaignCatalog.campaign_id == campaign_id,
                    RewardCampaignCatalog.catalog_id == catalog_id,
                    RewardCampaignCatalog.status == "active",
                    RewardCampaignCatalog.deleted_date.is_(None),
                )
                .first()
            )
            if not campaign_catalog:
                raise NotFoundException(f"Catalog item {catalog_id} not available in this campaign")

            # 2b. Calculate cost
            points_cost = campaign_catalog.points_cost
            item_cost = Decimal(str(points_cost)) * quantity
            total_cost += item_cost

            # 2c. Check stock (campaign-specific + global)
            current_stock = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == catalog_id,
                    or_(
                        RewardStock.reward_campaign_id == campaign_id,
                        RewardStock.reward_campaign_id.is_(None),
                    ),
                    RewardStock.deleted_date.is_(None),
                )
                .scalar()
            )
            if int(current_stock) < quantity:
                catalog = (
                    self.db.query(RewardCatalog)
                    .filter(RewardCatalog.id == catalog_id)
                    .first()
                )
                name = catalog.name if catalog else f"ID {catalog_id}"
                raise BadRequestException(f"Insufficient stock for '{name}'")

            redemption_items.append({
                "catalog_id": catalog_id,
                "quantity": quantity,
                "points_cost": points_cost,
                "item_cost": item_cost,
                "campaign_catalog": campaign_catalog,
            })

        # 3. Check total cost against available points
        if total_cost > available_points:
            raise BadRequestException(
                f"Insufficient points. Available: {float(available_points)}, required: {float(total_cost)}"
            )

        # 4. Create redemption records with shared group hash (NO stock withdrawal yet)
        group_hash = uuid.uuid4().hex
        redemptions = []
        for ri in redemption_items:
            redemption = RewardRedemption(
                organization_id=organization_id,
                reward_user_id=reward_user_id,
                reward_campaign_id=campaign_id,
                catalog_id=ri["catalog_id"],
                points_redeemed=int(ri["item_cost"]),
                quantity=ri["quantity"],
                status="inprogress",
                stock_action_id=None,  # stock deducted at confirm time
                hash=uuid.uuid4().hex,  # per-item hash (backward compat)
                redemption_group_hash=group_hash,  # shared cart hash
            )
            self.db.add(redemption)
            self.db.flush()

            catalog = (
                self.db.query(RewardCatalog)
                .filter(RewardCatalog.id == ri["catalog_id"])
                .first()
            )

            redemptions.append({
                "hash": redemption.hash,
                "catalog_name": catalog.name if catalog else None,
                "quantity": ri["quantity"],
                "points_cost": ri["points_cost"],
            })

        # 5. Deduct points
        point_txn = RewardPointTransaction(
            organization_id=organization_id,
            reward_user_id=reward_user_id,
            points=-total_cost,
            reward_campaign_id=campaign_id,
            claimed_date=datetime.now(timezone.utc),
            reference_type="redeem",
        )
        self.db.add(point_txn)
        self.db.flush()

        return {
            "success": True,
            "group_hash": group_hash,
            "redemptions": redemptions,
        }

    def cancel_redemption(self, reward_user_id: int, redemption_id: int) -> dict:
        """Cancel an inprogress redemption and refund points."""
        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.id == redemption_id,
                RewardRedemption.reward_user_id == reward_user_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .first()
        )
        if not redemption:
            raise NotFoundException("Redemption not found")
        if redemption.status != "inprogress":
            raise BadRequestException(f"Cannot cancel redemption with status '{redemption.status}'")

        # 1. Set status to canceled
        redemption.status = "canceled"
        redemption.updated_date = datetime.now(timezone.utc)
        self.db.flush()

        # 2. Refund points (positive transaction)
        refund_txn = RewardPointTransaction(
            organization_id=redemption.organization_id,
            reward_user_id=reward_user_id,
            points=redemption.points_redeemed,
            reward_campaign_id=redemption.reward_campaign_id,
            claimed_date=datetime.now(timezone.utc),
            reference_type="refund",
        )
        self.db.add(refund_txn)
        self.db.flush()

        return {
            "success": True,
            "refunded_points": redemption.points_redeemed,
            "redemption_id": redemption.id,
        }

    def reject_redemption_by_hash(self, hash: str, note: str = None) -> dict:
        """Staff rejects redemption(s) by hash or group_hash — cancel + refund points."""
        # Try group_hash first
        redemptions = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.redemption_group_hash == hash,
                RewardRedemption.status == "inprogress",
                RewardRedemption.deleted_date.is_(None),
            )
            .all()
        )
        if not redemptions:
            # Fallback to single hash
            single = (
                self.db.query(RewardRedemption)
                .filter(
                    RewardRedemption.hash == hash,
                    RewardRedemption.status == "inprogress",
                    RewardRedemption.deleted_date.is_(None),
                )
                .first()
            )
            if not single:
                raise NotFoundException("No inprogress redemption found for this QR")
            redemptions = [single]

        now = datetime.now(timezone.utc)
        total_refunded = 0

        for r in redemptions:
            r.status = "canceled"
            r.note = note or "Rejected by staff"
            r.updated_date = now
            self.db.flush()

            refund_txn = RewardPointTransaction(
                organization_id=r.organization_id,
                reward_user_id=r.reward_user_id,
                points=r.points_redeemed,
                reward_campaign_id=r.reward_campaign_id,
                claimed_date=now,
                reference_type="refund",
            )
            self.db.add(refund_txn)
            self.db.flush()
            total_refunded += r.points_redeemed

        return {
            "success": True,
            "canceled_count": len(redemptions),
            "total_refunded_points": total_refunded,
        }

    def get_user_organizations(self, reward_user_id: int) -> list[dict]:
        """Get organizations the user is linked to OR has earned points in.

        Includes deactivated memberships (is_active=False) so the LIFF can
        render them grayed out instead of silently hiding — admin de-activation
        becomes visible to the user.

        Returns each org with:
          - is_active: from OrganizationRewardUser.is_active (true=can interact)
          - has_membership: true if there's an org_reward_user row at all
            (false = user has past points but no current membership)
        """
        from ...models.subscriptions.organizations import Organization

        # 1. Orgs the user has memberships in (active OR deactivated)
        memberships = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .all()
        )
        membership_by_org = {m.organization_id: m for m in memberships}

        # 2. Orgs the user has earned points in (catches edge case where
        #    membership was hard-deleted but tx history remains)
        tx_rows = (
            self.db.query(
                RewardPointTransaction.organization_id,
                func.max(RewardPointTransaction.claimed_date).label("last_claim"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.organization_id)
            .all()
        )
        last_claim_by_org = {row.organization_id: row.last_claim for row in tx_rows}

        all_org_ids = set(membership_by_org.keys()) | set(last_claim_by_org.keys())

        result = []
        for org_id in all_org_ids:
            org = self.db.query(Organization).filter(Organization.id == org_id).first()
            m = membership_by_org.get(org_id)
            result.append({
                "organization_id": org_id,
                "organization_name": org.name if org else None,
                "is_active": bool(m.is_active) if m else False,
                "has_membership": m is not None,
                "role": m.role if m else None,
                "last_claim": last_claim_by_org.get(org_id).isoformat()
                              if last_claim_by_org.get(org_id) else None,
            })

        # Sort by last_claim desc (orgs with no claim go to the bottom)
        result.sort(
            key=lambda r: r["last_claim"] or "",
            reverse=True,
        )
        return result

    def get_user_balance_summary(self, reward_user_id: int) -> dict:
        """Per-campaign + total balance breakdown.

        The hero card on the LIFF home page wants a "spendable balance" — sum
        of points from campaigns the user can actually redeem in right now.
        Points from ended/canceled/archived campaigns are stranded and should
        be shown separately (grayed) so the user understands what happened.

        Returns:
          {
            "available_balance": <int>,  # spendable across active campaigns
            "expired_balance": <int>,    # stranded in ended/canceled campaigns
            "lifetime_earned": <int>,    # all earn txs ever
            "redeemed_total": <int>,     # all redeem txs (abs)
            "by_campaign": [
              {campaign_id, name, status, ended_date, balance, organization_id, ...}
            ]
          }
        """
        now = datetime.now(timezone.utc)

        # Sum points per campaign (earn + redeem netted)
        rows = (
            self.db.query(
                RewardPointTransaction.reward_campaign_id,
                RewardPointTransaction.organization_id,
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("balance"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.reward_campaign_id.isnot(None),
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(
                RewardPointTransaction.reward_campaign_id,
                RewardPointTransaction.organization_id,
            )
            .all()
        )

        # Lifetime totals — don't filter by campaign status, just by tx type
        lifetime_earned = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.points > 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        ) or 0
        redeemed_total = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.points < 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        ) or 0
        redeemed_total = abs(int(redeemed_total))

        available_balance = 0
        expired_balance = 0
        by_campaign = []

        for row in rows:
            campaign = (
                self.db.query(RewardCampaign)
                .filter(
                    RewardCampaign.id == row.reward_campaign_id,
                    RewardCampaign.deleted_date.is_(None),
                )
                .first()
            )
            balance = int(row.balance or 0)
            if balance <= 0:
                continue

            # A campaign is "active" (redeemable) if status='active' AND
            # (no end_date OR end_date >= now). Anything else is "expired" from
            # the user's redeem perspective: paused / ended / archived / past
            # end_date / catalog deleted.
            is_redeemable = bool(
                campaign
                and campaign.status == "active"
                and (campaign.end_date is None or campaign.end_date >= now)
            )

            if is_redeemable:
                available_balance += balance
            else:
                expired_balance += balance

            by_campaign.append({
                "campaign_id": row.reward_campaign_id,
                "organization_id": row.organization_id,
                "name": campaign.name if campaign else None,
                "status": campaign.status if campaign else "deleted",
                "end_date": campaign.end_date.isoformat() if campaign and campaign.end_date else None,
                "balance": balance,
                "is_redeemable": is_redeemable,
            })

        # Sort: redeemable first, then by balance desc
        by_campaign.sort(key=lambda c: (not c["is_redeemable"], -c["balance"]))

        return {
            "available_balance": int(available_balance),
            "expired_balance": int(expired_balance),
            "lifetime_earned": int(lifetime_earned),
            "redeemed_total": int(redeemed_total),
            "by_campaign": by_campaign,
        }

    def get_gamification_summary(self, reward_user_id: int) -> dict:
        """Three-layer gamification breakdown:
          - lifetime: cross-org CO2 identity (the "how much did you help the planet" number)
          - global_badges_earned: achievements that span orgs
          - by_org: per-org rank + streak + per-org badges + stats

        Lifetime metrics include tx from ended/archived campaigns (the recycling
        happened, kg already accumulated) but exclude soft-deleted campaigns
        and cancelled redemptions. Per-org rank counts only `type='material'`
        activity materials (activity claims don't represent recycling volume).
        """
        from ...models.subscriptions.organizations import Organization

        # 1. Fetch all claim tx for this user — single query, join activity_materials
        #    to know material vs activity type.
        tx_rows = (
            self.db.query(
                RewardPointTransaction.id,
                RewardPointTransaction.organization_id,
                RewardPointTransaction.reward_campaign_id,
                RewardPointTransaction.reward_activity_materials_id,
                RewardPointTransaction.points,
                RewardPointTransaction.value,
                RewardPointTransaction.unit,
                RewardPointTransaction.claimed_date,
                RewardPointTransaction.reference_type,
                RewardActivityMaterial.type.label("am_type"),
                RewardActivityMaterial.name.label("am_name"),
            )
            .outerjoin(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.deleted_date.is_(None),
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.points > 0,
            )
            .all()
        )

        # Filter out tx whose campaign is soft-deleted. Bulk-fetch campaigns to
        # avoid N+1.
        campaign_ids = {r.reward_campaign_id for r in tx_rows if r.reward_campaign_id}
        live_campaign_ids = set()
        if campaign_ids:
            live_campaign_ids = {
                cid
                for (cid,) in self.db.query(RewardCampaign.id)
                .filter(
                    RewardCampaign.id.in_(campaign_ids),
                    RewardCampaign.deleted_date.is_(None),
                )
                .all()
            }
        valid_tx = [
            r for r in tx_rows
            if r.reward_campaign_id is None or r.reward_campaign_id in live_campaign_ids
        ]

        # 2. Lifetime aggregates (cross-org)
        lifetime_kg = 0.0
        lifetime_ghg = 0.0
        lifetime_first_date = None
        lifetime_last_date = None
        per_org_data = {}   # org_id -> accumulator
        for r in valid_tx:
            qty = float(r.value or 0)
            is_weight = _is_weight_unit(r.unit) and qty > 0
            is_material = (r.am_type == "material") if r.am_type else False

            if is_weight:
                kg = qty
                ghg = kg * _estimate_ghg_per_kg(r.am_name)
                lifetime_kg += kg
                lifetime_ghg += ghg
            if r.claimed_date:
                if lifetime_first_date is None or r.claimed_date < lifetime_first_date:
                    lifetime_first_date = r.claimed_date
                if lifetime_last_date is None or r.claimed_date > lifetime_last_date:
                    lifetime_last_date = r.claimed_date

            # Per-org accumulator
            org_id = r.organization_id
            if org_id not in per_org_data:
                per_org_data[org_id] = {
                    "kg": 0.0,
                    "ghg": 0.0,
                    "claims_count": 0,
                    "materials": set(),
                    "first_date": None,
                    "last_date": None,
                    "claim_dates": [],
                }
            acc = per_org_data[org_id]
            # rank/kg counts only material-kind claims with weight unit
            if is_weight and is_material:
                acc["kg"] += qty
                acc["ghg"] += qty * _estimate_ghg_per_kg(r.am_name)
            acc["claims_count"] += 1
            if r.reward_activity_materials_id:
                acc["materials"].add(r.reward_activity_materials_id)
            if r.claimed_date:
                acc["claim_dates"].append(r.claimed_date)
                if acc["first_date"] is None or r.claimed_date < acc["first_date"]:
                    acc["first_date"] = r.claimed_date
                if acc["last_date"] is None or r.claimed_date > acc["last_date"]:
                    acc["last_date"] = r.claimed_date

        # 3. Redemption count for `first_redeem_ever` global badge
        redemption_count = (
            self.db.query(func.count(RewardRedemption.id))
            .filter(
                RewardRedemption.reward_user_id == reward_user_id,
                RewardRedemption.status != "canceled",
                RewardRedemption.deleted_date.is_(None),
            )
            .scalar()
        ) or 0

        # 4. Fetch org names + membership is_active for orgs that appeared in tx
        org_ids = list(per_org_data.keys())
        orgs_map = {}
        if org_ids:
            for o in self.db.query(Organization).filter(Organization.id.in_(org_ids)).all():
                orgs_map[o.id] = o
        memberships = {}
        if org_ids:
            for m in (
                self.db.query(OrganizationRewardUser)
                .filter(
                    OrganizationRewardUser.reward_user_id == reward_user_id,
                    OrganizationRewardUser.organization_id.in_(org_ids),
                    OrganizationRewardUser.deleted_date.is_(None),
                )
                .all()
            ):
                memberships[m.organization_id] = m

        # 5. Build per-org payload
        trees_total = int(lifetime_ghg / GHG_TO_TREES) if lifetime_ghg > 0 else 0
        km_total = int(lifetime_ghg / GHG_TO_KM) if lifetime_ghg > 0 else 0

        by_org = []
        for org_id, acc in per_org_data.items():
            rank = _get_rank(acc["kg"])
            streak = _calc_streak_weekly(acc["claim_dates"])
            org = orgs_map.get(org_id)
            membership = memberships.get(org_id)

            badges_earned = self._compute_org_badges(
                claims_count=acc["claims_count"],
                streak_current=streak["current"],
                rank_level=rank["level"],
                kg_recycled=acc["kg"],
                unique_materials=len(acc["materials"]),
            )

            by_org.append({
                "organization_id": org_id,
                "organization_name": org.name if org else None,
                "is_active": bool(membership.is_active) if membership else False,
                "has_membership": membership is not None,
                "stats": {
                    "kg_recycled": round(acc["kg"], 2),
                    "ghg_kg_co2": round(acc["ghg"], 2),
                    "claims_count": acc["claims_count"],
                    "unique_materials": len(acc["materials"]),
                    "first_claim_date": acc["first_date"].isoformat() if acc["first_date"] else None,
                    "last_claim_date": acc["last_date"].isoformat() if acc["last_date"] else None,
                },
                "rank": rank,
                "streak_weekly": streak,
                "badges_earned": badges_earned,
            })

        # Sort by_org: active first, then by last_claim desc (most recently active org floats up)
        by_org.sort(
            key=lambda o: (
                not o["is_active"],
                -(datetime.fromisoformat(o["stats"]["last_claim_date"]).timestamp()
                  if o["stats"]["last_claim_date"] else 0),
            ),
        )

        global_badges = self._compute_global_badges(
            lifetime_kg=lifetime_kg,
            lifetime_ghg=lifetime_ghg,
            trees=trees_total,
            redemption_count=int(redemption_count),
            total_orgs=len(per_org_data),
        )

        return {
            "lifetime": {
                "kg_recycled": round(lifetime_kg, 2),
                "ghg_kg_co2": round(lifetime_ghg, 2),
                "trees_equivalent": trees_total,
                "km_driven_avoided": km_total,
                "first_claim_date": lifetime_first_date.isoformat() if lifetime_first_date else None,
                "total_claims": len(valid_tx),
                "total_orgs": len(per_org_data),
            },
            "global_badges_earned": global_badges,
            "by_org": by_org,
        }

    # ─── Badge rule definitions ───────────────────────────────────────────
    def _compute_global_badges(
        self,
        lifetime_kg: float,
        lifetime_ghg: float,
        trees: int,
        redemption_count: int,
        total_orgs: int,
    ) -> list[dict]:
        """Cross-org achievements — the "lifetime impact" badge set."""
        defs = [
            {
                "id": "first_redeem_ever",
                "label": "แลกครั้งแรก",
                "description": "แลกของรางวัลครั้งแรก",
                "icon": "🎉",
                "earned": redemption_count >= 1,
                "progress": {"current": min(redemption_count, 1), "target": 1},
            },
            {
                "id": "lifetime_100kg",
                "label": "100 กก. รวม",
                "description": "สะสมขยะรีไซเคิลรวม 100 กก. ข้ามทุกชุมชน",
                "icon": "💯",
                "earned": lifetime_kg >= 100,
                "progress": {"current": int(min(lifetime_kg, 100)), "target": 100},
            },
            {
                "id": "lifetime_co2_50",
                "label": "ลด CO₂ 50 กก.",
                "description": "ลดการปล่อย CO₂e รวม 50 กก.",
                "icon": "🌍",
                "earned": lifetime_ghg >= 50,
                "progress": {"current": int(min(lifetime_ghg, 50)), "target": 50},
            },
            {
                "id": "trees_5",
                "label": "เทียบเท่า 5 ต้น",
                "description": "ลด CO₂ เทียบเท่าปลูกต้นไม้ 5 ต้น",
                "icon": "🌳",
                "earned": trees >= 5,
                "progress": {"current": min(trees, 5), "target": 5},
            },
            {
                "id": "multi_org",
                "label": "หลายชุมชน",
                "description": "เข้าร่วมตั้งแต่ 2 องค์กรขึ้นไป",
                "icon": "🏘️",
                "earned": total_orgs >= 2,
                "progress": {"current": min(total_orgs, 2), "target": 2},
            },
        ]
        return defs

    def _compute_org_badges(
        self,
        claims_count: int,
        streak_current: int,
        rank_level: int,
        kg_recycled: float,
        unique_materials: int,
    ) -> list[dict]:
        """Per-org achievements — scoped within one community."""
        return [
            {
                "id": "first_claim_org",
                "label": "เริ่มต้น",
                "description": "ส่งขยะครั้งแรกในชุมชนนี้",
                "icon": "🌱",
                "earned": claims_count >= 1,
                "progress": {"current": min(claims_count, 1), "target": 1},
            },
            {
                "id": "streak_4w_org",
                "label": "Streak 4 สัปดาห์",
                "description": "สะสมต่อเนื่อง 4 สัปดาห์ในชุมชนนี้",
                "icon": "🔥",
                "earned": streak_current >= 4,
                "progress": {"current": min(streak_current, 4), "target": 4},
            },
            {
                "id": "rank_tier_org",
                "label": "เลื่อนขั้น",
                "description": "เลื่อนขั้นเป็นต้นกล้าหรือสูงกว่า",
                "icon": "⭐",
                "earned": rank_level >= 2,
                "progress": {"current": min(rank_level, 2), "target": 2},
            },
            {
                "id": "kg_100_org",
                "label": "100 กก.",
                "description": "รีไซเคิลครบ 100 กก. ในชุมชนนี้",
                "icon": "💯",
                "earned": kg_recycled >= 100,
                "progress": {"current": int(min(kg_recycled, 100)), "target": 100},
            },
            {
                "id": "5_materials_org",
                "label": "5 วัสดุ",
                "description": "รีไซเคิลวัสดุครบ 5 ชนิดในชุมชนนี้",
                "icon": "🎨",
                "earned": unique_materials >= 5,
                "progress": {"current": min(unique_materials, 5), "target": 5},
            },
        ]

    def get_user_campaigns_for_redeem(
        self, reward_user_id: int, organization_id: int
    ) -> list[dict]:
        """Get campaigns the user has points in, with available balances.

        Only returns campaigns that are still redeemable — active status and
        not past their end_date — so the LIFF picker matches submit_redemption
        validation.
        """
        rows = (
            self.db.query(
                RewardPointTransaction.reward_campaign_id,
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("available_points"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reward_campaign_id.isnot(None),
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_campaign_id)
            .all()
        )

        now = datetime.now(timezone.utc)
        result = []
        for row in rows:
            available = float(row.available_points)
            if available <= 0:
                continue

            campaign = (
                self.db.query(RewardCampaign)
                .filter(
                    RewardCampaign.id == row.reward_campaign_id,
                    RewardCampaign.status == "active",
                    or_(RewardCampaign.end_date.is_(None), RewardCampaign.end_date >= now),
                    RewardCampaign.deleted_date.is_(None),
                )
                .first()
            )
            if not campaign:
                continue
            result.append({
                "campaign_id": row.reward_campaign_id,
                "name": campaign.name,
                "available_points": available,
            })

        return result

    def get_campaign_catalog_for_redeem(
        self, campaign_id: int, reward_user_id: int
    ) -> dict:
        """Get redeemable catalog items for a campaign with stock and user balance."""
        # Validate campaign is still redeemable — same check as submit_redemption
        now = datetime.now(timezone.utc)
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == campaign_id,
                RewardCampaign.status == "active",
                or_(RewardCampaign.end_date.is_(None), RewardCampaign.end_date >= now),
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise BadRequestException("Campaign not active, ended, or not found")

        # User available points for this campaign
        available_points = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.reward_campaign_id == campaign_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        )

        # Campaign catalog items
        links = (
            self.db.query(RewardCampaignCatalog)
            .filter(
                RewardCampaignCatalog.campaign_id == campaign_id,
                RewardCampaignCatalog.status == "active",
                RewardCampaignCatalog.deleted_date.is_(None),
            )
            .all()
        )

        catalog_items = []
        for link in links:
            catalog = (
                self.db.query(RewardCatalog)
                .filter(
                    RewardCatalog.id == link.catalog_id,
                    RewardCatalog.deleted_date.is_(None),
                )
                .first()
            )
            if not catalog:
                continue

            # Stock = campaign-specific + global (campaign_id=NULL)
            stock_remaining = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == link.catalog_id,
                    or_(
                        RewardStock.reward_campaign_id == campaign_id,
                        RewardStock.reward_campaign_id.is_(None),
                    ),
                    RewardStock.deleted_date.is_(None),
                )
                .scalar()
            )

            catalog_items.append({
                "id": link.id,
                "catalog_id": catalog.id,
                "name": catalog.name,
                "description": catalog.description,
                "thumbnail_id": catalog.thumbnail_id,
                "points_cost": link.points_cost,
                "stock_remaining": int(stock_remaining),
                "unit": catalog.unit,
            })

        return {
            "available_points": float(available_points),
            "catalog": catalog_items,
        }
