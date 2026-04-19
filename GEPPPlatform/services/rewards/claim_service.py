"""
Claim Service - Staff claiming points on behalf of users at droppoints
Creates both reward point transactions AND real transactions in the main system
"""

import math
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardSetup,
    RewardCampaign,
    RewardCampaignClaim,
    RewardCampaignDroppoint,
    RewardActivityMaterial,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import OrganizationRewardUser, Droppoint
from ...models.transactions.transactions import Transaction, TransactionStatus
from ...models.transactions.transaction_records import TransactionRecord
from ...models.cores.references import Material
from ...exceptions import NotFoundException, BadRequestException


class ClaimService:
    """Handles staff claiming points on behalf of users at droppoints."""

    def __init__(self, db: Session):
        self.db = db

    def claim_points(
        self,
        staff_org_user_id: int,
        reward_user_id: int,
        campaign_id: int,
        items: list[dict],
        droppoint_id: int,
        image_ids: list[int] | None = None,
    ) -> dict:
        """
        Claim points for a user.
        items = [{"activity_material_id": int, "value": float}, ...]
        Also creates a real Transaction + TransactionRecords when material is linked.
        """
        # 1. Verify campaign is active AND not past end_date (ended = computed)
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
            raise NotFoundException("Campaign not found, not active, or has ended")

        # Verify droppoint is linked to campaign
        dp_link = (
            self.db.query(RewardCampaignDroppoint)
            .filter(
                RewardCampaignDroppoint.campaign_id == campaign_id,
                RewardCampaignDroppoint.droppoint_id == droppoint_id,
                RewardCampaignDroppoint.deleted_date.is_(None),
            )
            .first()
        )
        if not dp_link:
            raise BadRequestException("Droppoint is not linked to this campaign")

        # Get droppoint for origin_id mapping
        droppoint = (
            self.db.query(Droppoint)
            .filter(Droppoint.id == droppoint_id)
            .first()
        )

        total_points = Decimal("0")
        total_weight = Decimal("0")
        items_claimed = []
        now = datetime.now(timezone.utc)

        # Load setup once for rounding + timezone
        setup = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == campaign.organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )
        rounding_method = setup.points_rounding_method if setup else "floor"
        setup_tz = setup.timezone if setup else "UTC"

        # Pre-compute today's total for per-day limit check
        local_now = now.astimezone(ZoneInfo(setup_tz))
        local_today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_today_start = local_today_start.astimezone(timezone.utc)

        today_total = Decimal("0")
        if campaign.points_per_day_limit is not None:
            today_total = Decimal(str(
                self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
                .filter(
                    RewardPointTransaction.reward_user_id == reward_user_id,
                    RewardPointTransaction.reward_campaign_id == campaign_id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.claimed_date >= utc_today_start,
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar()
            ))

        # Collect TransactionRecord data first, create Transaction after
        pending_records = []

        for item in items:
            activity_material_id = item.get("activity_material_id")
            value = Decimal(str(item.get("value", 0)))

            if not activity_material_id or value <= 0:
                raise BadRequestException("Each item requires activity_material_id and a positive value")

            # 2a. Get claim rule for campaign + activity_material
            claim_rule = (
                self.db.query(RewardCampaignClaim)
                .filter(
                    RewardCampaignClaim.campaign_id == campaign_id,
                    RewardCampaignClaim.activity_material_id == activity_material_id,
                    RewardCampaignClaim.deleted_date.is_(None),
                )
                .first()
            )
            if not claim_rule:
                raise NotFoundException(
                    f"No claim rule for activity_material_id={activity_material_id} in this campaign"
                )

            # 2b. Check max_claims_total
            if claim_rule.max_claims_total is not None:
                total_claims = (
                    self.db.query(func.count(RewardPointTransaction.id))
                    .filter(
                        RewardPointTransaction.reward_campaign_id == campaign_id,
                        RewardPointTransaction.reward_activity_materials_id == activity_material_id,
                        RewardPointTransaction.reference_type == "claim",
                        RewardPointTransaction.deleted_date.is_(None),
                    )
                    .scalar()
                ) or 0
                if total_claims >= claim_rule.max_claims_total:
                    raise BadRequestException(
                        f"Total claim limit reached for activity_material_id={activity_material_id}"
                    )

            # 2c. Check max_claims_per_user
            if claim_rule.max_claims_per_user is not None:
                user_claims = (
                    self.db.query(func.count(RewardPointTransaction.id))
                    .filter(
                        RewardPointTransaction.reward_user_id == reward_user_id,
                        RewardPointTransaction.reward_campaign_id == campaign_id,
                        RewardPointTransaction.reward_activity_materials_id == activity_material_id,
                        RewardPointTransaction.reference_type == "claim",
                        RewardPointTransaction.deleted_date.is_(None),
                    )
                    .scalar()
                ) or 0
                if user_claims >= claim_rule.max_claims_per_user:
                    raise BadRequestException(
                        f"Per-user claim limit reached for activity_material_id={activity_material_id}"
                    )

            # 2d. Calculate points, apply rounding, then enforce limits
            points = claim_rule.points * value
            if rounding_method == "ceil":
                points = Decimal(str(math.ceil(points)))
            elif rounding_method == "round":
                points = Decimal(str(round(points)))
            else:  # floor (default)
                points = Decimal(str(math.floor(points)))

            # 2e. Per-transaction limit
            if campaign.points_per_transaction_limit is not None:
                points = min(points, Decimal(str(campaign.points_per_transaction_limit)))

            # 2f. Per-day limit
            if campaign.points_per_day_limit is not None:
                remaining_daily = Decimal(str(campaign.points_per_day_limit)) - today_total
                points = min(points, max(Decimal("0"), remaining_daily))
                if points <= 0:
                    raise BadRequestException("Daily point limit reached for this campaign")
                today_total += points  # track accumulation across items in this request

            # Get activity material for unit snapshot and material_id
            activity_mat = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == activity_material_id)
                .first()
            )

            # Resolve main_material_id and category_id from linked material
            linked_material_id = activity_mat.material_id if activity_mat else None
            main_material_id = None
            category_id = None
            if linked_material_id:
                mat = self.db.query(Material).filter(Material.id == linked_material_id).first()
                if mat:
                    main_material_id = mat.main_material_id
                    category_id = mat.category_id

            # Collect record data if material linkage is complete
            if main_material_id and category_id:
                pending_records.append({
                    "material_id": linked_material_id,
                    "main_material_id": main_material_id,
                    "category_id": category_id,
                    "value": value,
                    "unit": activity_mat.name if activity_mat else "kg",
                })

            # 2e. Create reward point transaction (always — this is the core reward logic)
            txn = RewardPointTransaction(
                organization_id=campaign.organization_id,
                reward_user_id=reward_user_id,
                points=points,
                reward_activity_materials_id=activity_material_id,
                reward_campaign_id=campaign_id,
                value=value,
                unit=activity_mat.name if activity_mat else None,
                claimed_date=now,
                staff_id=staff_org_user_id,
                droppoint_id=droppoint_id,
                reference_type="claim",
                image_ids=image_ids,
            )
            self.db.add(txn)
            self.db.flush()

            total_points += points
            total_weight += value
            items_claimed.append({
                "activity_material_id": activity_material_id,
                "value": float(value),
                "points": float(points),
                "point_transaction_id": txn.id,
            })

        # 3. Create Transaction + TransactionRecords in main system
        #    (only if there are resolvable material links)
        transaction_id = None
        if pending_records:
            origin_id = droppoint.user_location_id if droppoint and droppoint.user_location_id else None
            transaction = Transaction(
                transaction_method="reward",
                status=TransactionStatus.completed,
                organization_id=campaign.organization_id,
                origin_id=origin_id,
                transaction_date=now,
                weight_kg=total_weight,
                images=image_ids or [],
                notes=f"Reward claim - Campaign: {campaign.name}",
            )
            self.db.add(transaction)
            self.db.flush()
            transaction_id = transaction.id

            record_ids = []
            for rec in pending_records:
                tx_record = TransactionRecord(
                    status="completed",
                    created_transaction_id=transaction.id,
                    transaction_type="rewards",
                    material_id=rec["material_id"],
                    main_material_id=rec["main_material_id"],
                    category_id=rec["category_id"],
                    origin_quantity=rec["value"],
                    origin_weight_kg=rec["value"],
                    unit=rec["unit"],
                    created_by_id=origin_id or staff_org_user_id,
                    transaction_date=now,
                    completed_date=now,
                )
                self.db.add(tx_record)
                self.db.flush()
                record_ids.append(tx_record.id)

            transaction.transaction_records = record_ids
            self.db.flush()

        # 4. Auto-register user in organization if not already a member
        #    Use try/except to handle race condition (concurrent first-time claims)
        existing_membership = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == campaign.organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not existing_membership:
            try:
                nested = self.db.begin_nested()  # SAVEPOINT
                new_membership = OrganizationRewardUser(
                    reward_user_id=reward_user_id,
                    organization_id=campaign.organization_id,
                    role="user",
                )
                self.db.add(new_membership)
                self.db.flush()
            except Exception:
                # Unique constraint violation = another concurrent request created it first
                nested.rollback()  # rollback only the savepoint, not the whole transaction

        return {
            "success": True,
            "total_points": float(total_points),
            "total_weight_kg": float(total_weight),
            "transaction_id": transaction_id,
            "items_claimed": items_claimed,
        }
