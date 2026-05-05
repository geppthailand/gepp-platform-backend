"""
Invite Service - One-time staff invite deep links
"""

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    RewardStaffInvite,
    RewardUser,
    OrganizationRewardUser,
)
from ...exceptions import NotFoundException, BadRequestException


class InviteService:
    """Handles creating and verifying one-time staff invite links."""

    def __init__(self, db: Session):
        self.db = db

    ALLOWED_EXPIRY_HOURS = {24, 168, 720, 0}  # 1d / 7d / 30d / never

    def create_invite(
        self,
        organization_id: int,
        created_by_id: int,
        expiry_hours: int | None = None,
    ) -> dict:
        """Create a one-time staff invite link (admin action).

        expiry_hours: one of {24, 168, 720, 0}. None → default 168 (7d). 0 → never expires.
        """
        hours = 168 if expiry_hours is None else int(expiry_hours)
        if hours not in self.ALLOWED_EXPIRY_HOURS:
            raise BadRequestException(
                f"expiry_hours must be one of {sorted(self.ALLOWED_EXPIRY_HOURS)}"
            )

        expires_date = None if hours == 0 else datetime.now(timezone.utc) + timedelta(hours=hours)

        invite = RewardStaffInvite(
            hash=uuid.uuid4().hex,
            organization_id=organization_id,
            created_by_id=created_by_id,
            status="pending",
            expires_date=expires_date,
        )
        self.db.add(invite)
        self.db.flush()

        return {
            "id": invite.id,
            "hash": invite.hash,
            "organization_id": invite.organization_id,
            "status": invite.status,
            "expires_date": invite.expires_date.isoformat() if invite.expires_date else None,
            "created_date": invite.created_date.isoformat() if invite.created_date else None,
        }

    def revoke_invite(self, invite_id: int, organization_id: int) -> dict:
        """Revoke a pending invite → mark as expired."""
        invite = (
            self.db.query(RewardStaffInvite)
            .filter(
                RewardStaffInvite.id == invite_id,
                RewardStaffInvite.organization_id == organization_id,
                RewardStaffInvite.deleted_date.is_(None),
            )
            .first()
        )
        if not invite:
            raise NotFoundException("Invite not found")
        if invite.status != "pending":
            raise BadRequestException(f"Cannot revoke invite with status '{invite.status}'")

        invite.status = "expired"
        self.db.flush()
        return {"id": invite.id, "status": "expired"}

    def list_invites(self, organization_id: int) -> list[dict]:
        """List all invites for an organization."""
        invites = (
            self.db.query(RewardStaffInvite)
            .filter(
                RewardStaffInvite.organization_id == organization_id,
                RewardStaffInvite.deleted_date.is_(None),
            )
            .order_by(RewardStaffInvite.created_date.desc())
            .all()
        )

        now = datetime.now(timezone.utc)
        result = []
        for inv in invites:
            # Auto-expire if past expires_date and still pending
            status = inv.status
            if status == "pending" and inv.expires_date and inv.expires_date < now:
                inv.status = "expired"
                status = "expired"
                self.db.flush()

            # Get used_by display name — fallback to line_user_id or staff sentinel
            used_by_name = None
            if inv.used_by_id:
                user = (
                    self.db.query(RewardUser)
                    .filter(RewardUser.id == inv.used_by_id)
                    .first()
                )
                if user:
                    used_by_name = user.display_name or user.line_display_name
                    if not used_by_name and user.line_user_id:
                        used_by_name = f"@{user.line_user_id[:12]}…"
                if not used_by_name:
                    used_by_name = f"User #{inv.used_by_id}"

            result.append({
                "id": inv.id,
                "hash": inv.hash,
                "status": status,
                "expires_date": inv.expires_date.isoformat() if inv.expires_date else None,
                "used_by_id": inv.used_by_id,
                "used_by_name": used_by_name,
                "used_date": inv.used_date.isoformat() if inv.used_date else None,
                "created_date": inv.created_date.isoformat() if inv.created_date else None,
            })

        return result

    def verify_invite(self, hash: str, reward_user_id: int) -> dict:
        """Verify and consume a one-time staff invite link (public action)."""
        now = datetime.now(timezone.utc)

        # 1. Find invite
        invite = (
            self.db.query(RewardStaffInvite)
            .filter(
                RewardStaffInvite.hash == hash,
                RewardStaffInvite.deleted_date.is_(None),
            )
            .first()
        )
        if not invite:
            raise NotFoundException("Invite not found")

        # 2. Check status
        if invite.status == "used":
            raise BadRequestException("This invite has already been used")
        if invite.status == "expired":
            raise BadRequestException("This invite has expired")
        if invite.status != "pending":
            raise BadRequestException(f"Invite is not available (status: {invite.status})")

        # 3. Check expiration
        if invite.expires_date and invite.expires_date < now:
            invite.status = "expired"
            self.db.flush()
            raise BadRequestException("This invite has expired")

        # 4. Find or create OrganizationRewardUser
        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == invite.organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )

        if org_user:
            org_user.role = "staff"
            org_user.is_active = True
        else:
            org_user = OrganizationRewardUser(
                reward_user_id=reward_user_id,
                organization_id=invite.organization_id,
                role="staff",
            )
            self.db.add(org_user)

        # 5. Mark invite as used
        invite.status = "used"
        invite.used_by_id = reward_user_id
        invite.used_date = now
        self.db.flush()

        return {
            "success": True,
            "organization_id": invite.organization_id,
            "role": "staff",
            "org_reward_user_id": org_user.id,
        }
