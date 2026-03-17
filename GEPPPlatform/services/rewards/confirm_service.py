"""
Confirm Service - Staff confirming redemptions
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.redemptions import RewardRedemption, OrganizationRewardUser
from ...exceptions import NotFoundException, BadRequestException


class ConfirmService:
    """Handles staff confirming redemptions."""

    def __init__(self, db: Session):
        self.db = db

    def confirm_redemption(self, hash: str, staff_org_user_id: int) -> dict:
        """Confirm a redemption by its hash."""
        # 1. Lookup redemption
        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.hash == hash,
                RewardRedemption.deleted_date.is_(None),
            )
            .first()
        )
        if not redemption:
            raise NotFoundException("Redemption not found")

        # 2. Already completed
        if redemption.status == "completed":
            staff_info = None
            if redemption.staff_id:
                staff_org_user = (
                    self.db.query(OrganizationRewardUser)
                    .filter(OrganizationRewardUser.id == redemption.staff_id)
                    .first()
                )
                if staff_org_user:
                    staff_info = {
                        "org_reward_user_id": staff_org_user.id,
                        "reward_user_id": staff_org_user.reward_user_id,
                    }

            return {
                "already_completed": True,
                "completed_at": redemption.updated_date.isoformat() if redemption.updated_date else None,
                "staff_info": staff_info,
            }

        # 3. Canceled
        if redemption.status == "canceled":
            raise BadRequestException("Redemption was canceled")

        # 4. In progress - confirm it
        if redemption.status == "inprogress":
            redemption.status = "completed"
            redemption.staff_id = staff_org_user_id
            redemption.updated_date = datetime.now(timezone.utc)
            self.db.flush()

            return {
                "success": True,
                "id": redemption.id,
                "hash": redemption.hash,
                "catalog_id": redemption.catalog_id,
                "quantity": redemption.quantity,
                "points_redeemed": redemption.points_redeemed,
                "status": redemption.status,
                "staff_id": staff_org_user_id,
                "confirmed_at": redemption.updated_date.isoformat(),
            }

        # Unexpected status
        raise BadRequestException(f"Unexpected redemption status: {redemption.status}")
