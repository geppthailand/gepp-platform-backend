"""
Member Service - Manage organization reward members
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    RewardRedemption,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.catalog import RewardCatalog
from ...models.rewards.management import RewardCampaign
from ...exceptions import NotFoundException, BadRequestException


class MemberService:
    def __init__(self, db: Session):
        self.db = db

    def list_members(self, organization_id: int) -> list[dict]:
        """List all reward members for an organization with claimed points."""
        # Sub-query for total claimed points per user
        points_sq = (
            self.db.query(
                RewardPointTransaction.reward_user_id,
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("claimed_points"),
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_user_id)
            .subquery()
        )

        rows = (
            self.db.query(
                OrganizationRewardUser,
                RewardUser,
                points_sq.c.claimed_points,
            )
            .join(RewardUser, RewardUser.id == OrganizationRewardUser.reward_user_id)
            .outerjoin(points_sq, points_sq.c.reward_user_id == RewardUser.id)
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .order_by(OrganizationRewardUser.id.desc())
            .all()
        )

        return [
            {
                "id": org_user.id,
                "reward_user_id": org_user.reward_user_id,
                "display_name": user.display_name or user.line_display_name,
                "line_picture_url": user.line_picture_url,
                "role": org_user.role,
                "is_active": org_user.is_active,
                "created_date": org_user.created_date.isoformat() if org_user.created_date else None,
                "claimed_points": float(claimed_points) if claimed_points else 0,
            }
            for org_user, user, claimed_points in rows
        ]

    def get_detail(self, org_reward_user_id: int, organization_id: int) -> dict:
        """Get detailed member profile with point and redemption breakdowns."""
        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.id == org_reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not org_user:
            raise NotFoundException("Member not found")

        user = (
            self.db.query(RewardUser)
            .filter(RewardUser.id == org_user.reward_user_id)
            .first()
        )
        if not user:
            raise NotFoundException("Reward user not found")

        # Points grouped by campaign
        points_by_campaign = (
            self.db.query(
                RewardCampaign.id.label("campaign_id"),
                RewardCampaign.name.label("campaign_name"),
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("total_points"),
            )
            .join(
                RewardPointTransaction,
                RewardPointTransaction.reward_campaign_id == RewardCampaign.id,
            )
            .filter(
                RewardPointTransaction.reward_user_id == org_user.reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardCampaign.id, RewardCampaign.name)
            .all()
        )

        claimed_points_list = [
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "total_points": float(row.total_points),
            }
            for row in points_by_campaign
        ]

        # Redemptions
        redemptions = (
            self.db.query(
                RewardRedemption,
                RewardCatalog.name.label("catalog_name"),
                RewardCampaign.name.label("campaign_name"),
            )
            .join(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
            .join(RewardCampaign, RewardCampaign.id == RewardRedemption.reward_campaign_id)
            .filter(
                RewardRedemption.reward_user_id == org_user.reward_user_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .order_by(RewardRedemption.created_date.desc())
            .all()
        )

        redemption_list = [
            {
                "id": r.id,
                "catalog_name": catalog_name,
                "campaign_name": campaign_name,
                "quantity": r.quantity,
                "points_redeemed": r.points_redeemed,
                "status": r.status,
                "hash": r.hash,
                "created_date": r.created_date.isoformat() if r.created_date else None,
            }
            for r, catalog_name, campaign_name in redemptions
        ]

        return {
            "id": org_user.id,
            "reward_user_id": user.id,
            "display_name": user.display_name or user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "email": user.email,
            "phone_number": user.phone_number,
            "role": org_user.role,
            "is_active": org_user.is_active,
            "created_date": org_user.created_date.isoformat() if org_user.created_date else None,
            "claimed_points_list": claimed_points_list,
            "redemption_list": redemption_list,
        }

    def update_role(self, org_reward_user_id: int, role: str) -> dict:
        """Update member role (user or staff)."""
        if role not in ("user", "staff"):
            raise BadRequestException("Role must be 'user' or 'staff'")

        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.id == org_reward_user_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not org_user:
            raise NotFoundException("Member not found")

        org_user.role = role
        self.db.flush()

        return {"id": org_user.id, "role": org_user.role}

    def toggle_active(self, org_reward_user_id: int) -> dict:
        """Toggle member active status."""
        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.id == org_reward_user_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not org_user:
            raise NotFoundException("Member not found")

        org_user.is_active = not org_user.is_active
        self.db.flush()

        return {"id": org_user.id, "is_active": org_user.is_active}
