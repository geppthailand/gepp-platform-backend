"""
Claim Service - Staff claiming points on behalf of users at droppoints
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardCampaign,
    RewardCampaignClaim,
    RewardCampaignDroppoint,
    RewardActivityMaterial,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import OrganizationRewardUser
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
    ) -> dict:
        """
        Claim points for a user.
        items = [{"activity_material_id": int, "value": float}, ...]
        """
        # 1. Verify campaign is active
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == campaign_id,
                RewardCampaign.status == "active",
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise NotFoundException("Campaign not found or not active")

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

        total_points = Decimal("0")
        items_claimed = []
        now = datetime.now(timezone.utc)

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

            # 2d. Calculate points
            points = claim_rule.points * value

            # Get activity material for unit snapshot
            activity_mat = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == activity_material_id)
                .first()
            )

            # 2e. Create point transaction
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
            )
            self.db.add(txn)
            self.db.flush()

            total_points += points
            items_claimed.append({
                "activity_material_id": activity_material_id,
                "value": float(value),
                "points": float(points),
                "transaction_id": txn.id,
            })

        # 3. Auto-register user in organization if not already a member
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
            new_membership = OrganizationRewardUser(
                reward_user_id=reward_user_id,
                organization_id=campaign.organization_id,
                role="user",
            )
            self.db.add(new_membership)
            self.db.flush()

        return {
            "success": True,
            "total_points": float(total_points),
            "items_claimed": items_claimed,
        }
