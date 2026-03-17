"""
Overview Service - Dashboard statistics for reward programs
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import OrganizationRewardUser, RewardRedemption
from ...models.rewards.management import RewardCampaign
from ...models.rewards.points import RewardPointTransaction
from ...exceptions import APIException


class OverviewService:
    def __init__(self, db: Session):
        self.db = db

    def get_stats(self, organization_id: int) -> dict:
        """Return high-level reward program statistics for an organization."""
        total_members = (
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .scalar()
        ) or 0

        active_campaigns = (
            self.db.query(func.count(RewardCampaign.id))
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.status == "active",
                RewardCampaign.deleted_date.is_(None),
            )
            .scalar()
        ) or 0

        total_points_issued = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.points > 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        )

        total_redemptions = (
            self.db.query(func.count(RewardRedemption.id))
            .filter(
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .scalar()
        ) or 0

        return {
            "total_members": total_members,
            "active_campaigns": active_campaigns,
            "total_points_issued": float(total_points_issued),
            "total_redemptions": total_redemptions,
        }
