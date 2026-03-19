"""
Public Service - LIFF/public user registration and profile
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    Droppoint,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.management import RewardCampaign, RewardCampaignDroppoint
from ...exceptions import NotFoundException, BadRequestException, UnauthorizedException


class PublicRewardService:
    """Handles public/LIFF user registration and profile."""

    def __init__(self, db: Session):
        self.db = db

    def register_user(self, line_data: dict) -> dict:
        """Register or update a reward user from LINE profile data."""
        line_user_id = line_data.get("line_user_id")
        if not line_user_id:
            raise BadRequestException("line_user_id is required")

        # Check existing user
        user = (
            self.db.query(RewardUser)
            .filter(
                RewardUser.line_user_id == line_user_id,
                RewardUser.deleted_date.is_(None),
            )
            .first()
        )

        if user:
            # Update display info
            if line_data.get("display_name"):
                user.line_display_name = line_data["display_name"]
                if not user.display_name:
                    user.display_name = line_data["display_name"]
            if line_data.get("picture_url"):
                user.line_picture_url = line_data["picture_url"]
            if line_data.get("status_message"):
                user.line_status_message = line_data["status_message"]
            if line_data.get("email"):
                user.email = line_data["email"]
            if line_data.get("phone_number"):
                user.phone_number = line_data["phone_number"]
            self.db.flush()
        else:
            # Create new user
            user = RewardUser(
                line_user_id=line_user_id,
                display_name=line_data.get("display_name"),
                line_display_name=line_data.get("display_name"),
                line_picture_url=line_data.get("picture_url"),
                line_status_message=line_data.get("status_message"),
                email=line_data.get("email"),
                phone_number=line_data.get("phone_number"),
            )
            self.db.add(user)
            self.db.flush()

        return {
            "id": user.id,
            "line_user_id": user.line_user_id,
            "display_name": user.display_name or user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "email": user.email,
            "phone_number": user.phone_number,
            "created_date": user.created_date.isoformat() if user.created_date else None,
        }

    def get_profile(self, reward_user_id: int, organization_id: int = None) -> dict:
        """Get user profile, optionally with organization-specific point balances."""
        user = (
            self.db.query(RewardUser)
            .filter(RewardUser.id == reward_user_id, RewardUser.deleted_date.is_(None))
            .first()
        )
        if not user:
            raise NotFoundException("User not found")

        profile = {
            "id": user.id,
            "display_name": user.display_name or user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "email": user.email,
            "phone_number": user.phone_number,
        }

        if organization_id:
            org_user = (
                self.db.query(OrganizationRewardUser)
                .filter(
                    OrganizationRewardUser.reward_user_id == reward_user_id,
                    OrganizationRewardUser.organization_id == organization_id,
                    OrganizationRewardUser.deleted_date.is_(None),
                )
                .first()
            )

            profile["organization"] = {
                "org_reward_user_id": org_user.id if org_user else None,
                "role": org_user.role if org_user else None,
                "is_active": org_user.is_active if org_user else None,
                "is_member": org_user is not None,
            }

            # Point balance per campaign
            campaign_balances = (
                self.db.query(
                    RewardPointTransaction.reward_campaign_id,
                    RewardCampaign.name.label("campaign_name"),
                    func.coalesce(func.sum(RewardPointTransaction.points), 0).label("balance"),
                )
                .join(
                    RewardCampaign,
                    RewardCampaign.id == RewardPointTransaction.reward_campaign_id,
                )
                .filter(
                    RewardPointTransaction.reward_user_id == reward_user_id,
                    RewardPointTransaction.organization_id == organization_id,
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .group_by(
                    RewardPointTransaction.reward_campaign_id,
                    RewardCampaign.name,
                )
                .all()
            )

            profile["campaign_balances"] = [
                {
                    "campaign_id": row.reward_campaign_id,
                    "campaign_name": row.campaign_name,
                    "balance": float(row.balance),
                }
                for row in campaign_balances
            ]

        return profile

    def verify_staff(self, reward_user_id: int, droppoint_hash: str) -> dict:
        """Verify a user is staff. Tries campaign-droppoint hash first (returns campaign context),
        then falls back to plain droppoint hash (backward compat)."""

        campaign_id = None
        campaign_name = None
        droppoint = None

        # 1. Try campaign-droppoint hash first (new QR: locks campaign + droppoint)
        cd_link = (
            self.db.query(RewardCampaignDroppoint)
            .filter(
                RewardCampaignDroppoint.hash == droppoint_hash,
                RewardCampaignDroppoint.deleted_date.is_(None),
            )
            .first()
        )

        if cd_link:
            droppoint = (
                self.db.query(Droppoint)
                .filter(Droppoint.id == cd_link.droppoint_id, Droppoint.deleted_date.is_(None))
                .first()
            )
            campaign = (
                self.db.query(RewardCampaign)
                .filter(RewardCampaign.id == cd_link.campaign_id)
                .first()
            )
            campaign_id = cd_link.campaign_id
            campaign_name = campaign.name if campaign else None
        else:
            # 2. Fallback: plain droppoint hash (backward compat)
            droppoint = (
                self.db.query(Droppoint)
                .filter(Droppoint.hash == droppoint_hash, Droppoint.deleted_date.is_(None))
                .first()
            )

        if not droppoint:
            raise NotFoundException("Droppoint not found")

        # 3. Verify staff membership
        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == droppoint.organization_id,
                OrganizationRewardUser.role == "staff",
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not org_user:
            raise UnauthorizedException("Not a staff member")
        if not org_user.is_active:
            raise UnauthorizedException("Staff account is inactive")

        result = {
            "organization_id": droppoint.organization_id,
            "droppoint_id": droppoint.id,
            "droppoint_name": droppoint.name,
            "org_reward_user_id": org_user.id,
        }
        if campaign_id:
            result["campaign_id"] = campaign_id
            result["campaign_name"] = campaign_name

        return result
