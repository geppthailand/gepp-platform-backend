"""
Claim Service - Staff claiming points on behalf of users at droppoints
Creates both reward point transactions AND real transactions in the main system
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
from ...models.rewards.redemptions import OrganizationRewardUser, Droppoint
from ...models.transactions.transactions import Transaction, TransactionStatus
from ...models.transactions.transaction_records import TransactionRecord
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
        Also creates a real Transaction + TransactionRecords in the main system.
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

        # 2. Create main Transaction (method='reward')
        transaction = Transaction(
            transaction_method="reward",
            status=TransactionStatus.completed,
            organization_id=campaign.organization_id,
            origin_id=droppoint.user_location_id if droppoint else None,
            transaction_date=now,
            images=image_ids or [],
            notes=f"Reward claim - Campaign: {campaign.name}",
            created_by_id=droppoint.user_location_id if droppoint else None,
        )
        self.db.add(transaction)
        self.db.flush()

        record_ids = []

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

            # Get activity material for unit snapshot and material_id
            activity_mat = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == activity_material_id)
                .first()
            )

            # 2e. Create TransactionRecord in main system
            tx_record = TransactionRecord(
                status="completed",
                created_transaction_id=transaction.id,
                transaction_type="rewards",
                material_id=activity_mat.material_id if activity_mat else None,
                origin_quantity=value,
                origin_weight_kg=value,
                unit=activity_mat.name if activity_mat else "kg",
                created_by_id=droppoint.user_location_id if droppoint else None,
                transaction_date=now,
                completed_date=now,
            )
            self.db.add(tx_record)
            self.db.flush()
            record_ids.append(tx_record.id)

            # 2f. Create reward point transaction
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
                "transaction_id": txn.id,
                "record_id": tx_record.id,
            })

        # 3. Update Transaction with record IDs and weight
        transaction.transaction_records = record_ids
        transaction.weight_kg = total_weight
        self.db.flush()

        # 4. Auto-register user in organization if not already a member
        existing_membership = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == campaign.organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        _is_new_member = not existing_membership
        if _is_new_member:
            new_membership = OrganizationRewardUser(
                reward_user_id=reward_user_id,
                organization_id=campaign.organization_id,
                role="user",
            )
            self.db.add(new_membership)
            self.db.flush()

        # ── CRM: emit reward_claimed + points_earned (+ campaign_joined on first claim) ──
        try:
            from GEPPPlatform.services.admin.crm.crm_service import emit_event
            _props = {
                'campaign_id': campaign_id,
                'transaction_id': transaction.id,
                'total_points': float(total_points),
                'total_weight_kg': float(total_weight),
            }
            emit_event(
                self.db, event_type='reward_claimed', event_category='reward',
                organization_id=campaign.organization_id,
                user_location_id=staff_org_user_id,
                properties=_props, event_source='server', commit=False,
            )
            emit_event(
                self.db, event_type='points_earned', event_category='reward',
                organization_id=campaign.organization_id,
                user_location_id=staff_org_user_id,
                properties=_props, event_source='server', commit=False,
            )
            if _is_new_member:
                emit_event(
                    self.db, event_type='campaign_joined', event_category='reward',
                    organization_id=campaign.organization_id,
                    user_location_id=staff_org_user_id,
                    properties={'campaign_id': campaign_id}, event_source='server', commit=False,
                )
        except Exception as _exc:
            import logging as _log
            _log.getLogger(__name__).warning("CRM emit_event non-fatal (claim): %s", _exc)

        return {
            "success": True,
            "total_points": float(total_points),
            "total_weight_kg": float(total_weight),
            "transaction_id": transaction.id,
            "items_claimed": items_claimed,
        }
