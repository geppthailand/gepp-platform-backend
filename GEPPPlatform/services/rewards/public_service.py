"""
Public Service - LIFF/public user registration and profile
"""

from datetime import date, datetime, timezone

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    Droppoint,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.management import RewardCampaign, RewardCampaignDroppoint
from ...exceptions import NotFoundException, BadRequestException, UnauthorizedException
from ._phone import normalize_thai_phone, is_valid_thai_mobile, normalize_and_validate_thai_mobile


class PublicRewardService:
    """Handles public/LIFF user registration and profile."""

    def __init__(self, db: Session):
        self.db = db

    def resolve_user_by_line_id(self, line_user_id: str) -> int:
        """Resolve reward_user_id from line_user_id. Raises 401 if not found."""
        if not line_user_id:
            raise UnauthorizedException("X-Line-User-Id header is required")
        user = (
            self.db.query(RewardUser)
            .filter(
                RewardUser.line_user_id == line_user_id,
                RewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not user:
            raise UnauthorizedException("Unknown LINE user")
        return user.id

    def resolve_staff_by_line_id(self, line_user_id: str, organization_id: int) -> int:
        """Resolve org_reward_user.id for a staff member from line_user_id + org.
        Raises 401 if not a staff member of the given org."""
        reward_user_id = self.resolve_user_by_line_id(line_user_id)
        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.role == "staff",
                OrganizationRewardUser.is_active == True,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not org_user:
            raise UnauthorizedException("Caller is not a staff member of this organization")
        return org_user.id

    def resolve_staff_for_campaign(self, line_user_id: str, campaign_id: int) -> int:
        """Resolve org_reward_user.id for a staff member from line_user_id + campaign.
        Derives organization_id from the campaign."""
        campaign = (
            self.db.query(RewardCampaign)
            .filter(RewardCampaign.id == campaign_id, RewardCampaign.deleted_date.is_(None))
            .first()
        )
        if not campaign:
            raise NotFoundException("Campaign not found")
        return self.resolve_staff_by_line_id(line_user_id, campaign.organization_id)

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

    # ── Walk-in (phone-based) members ─────────────────────────────────────────

    def resolve_user_by_phone(
        self,
        phone: str,
        organization_id: int | None = None,
        exclude_user_id: int | None = None,
    ) -> dict | None:
        """Find a live member by normalized phone. Returns a preview dict or None.

        Phone values written by this system (walk-in register / profile completion)
        are always stored normalized, so an exact match on the normalized form is
        the reliable lookup key.
        """
        normalized = normalize_thai_phone(phone)
        if not is_valid_thai_mobile(normalized):
            return None
        q = self.db.query(RewardUser).filter(
            RewardUser.phone_number == normalized,
            RewardUser.deleted_date.is_(None),
        )
        if exclude_user_id:
            q = q.filter(RewardUser.id != exclude_user_id)
        user = q.order_by(RewardUser.created_date.asc()).first()
        if not user:
            return None
        return self._user_preview(user, organization_id)

    def register_walkin(
        self,
        staff_org_user_id: int,
        organization_id: int,
        display_name: str,
        phone: str,
        date_of_birth: str | None = None,
        pdpa_consent: bool = False,
    ) -> dict:
        """Staff registers a walk-in (non-LINE) member by phone.

        Idempotent on phone: if a member already exists with this number we return
        them (with ``existing=True``) and just ensure org membership — never a dup.
        """
        if not display_name or not display_name.strip():
            raise BadRequestException("display_name is required")
        if not pdpa_consent:
            raise BadRequestException("PDPA consent is required")
        normalized = normalize_and_validate_thai_mobile(phone)

        existing = (
            self.db.query(RewardUser)
            .filter(RewardUser.phone_number == normalized, RewardUser.deleted_date.is_(None))
            .order_by(RewardUser.created_date.asc())
            .first()
        )
        if existing:
            self._ensure_membership(existing.id, organization_id)
            self.db.flush()
            preview = self._user_preview(existing, organization_id)
            preview["existing"] = True
            return preview

        user = RewardUser(
            display_name=display_name.strip(),
            phone_number=normalized,
            date_of_birth=self._parse_dob(date_of_birth),
            created_via="staff_walkin",
            created_by_staff_id=staff_org_user_id,
            pdpa_consent_at=datetime.now(timezone.utc),
        )
        self.db.add(user)
        self.db.flush()
        self._ensure_membership(user.id, organization_id)
        self.db.flush()
        preview = self._user_preview(user, organization_id)
        preview["existing"] = False
        return preview

    def complete_profile(
        self,
        reward_user_id: int,
        display_name: str,
        phone: str,
        date_of_birth: str | None = None,
        pdpa_consent: bool = False,
        confirm_merge: bool = False,
    ) -> dict:
        """LINE user fills in name + phone (+ DOB) after auto-create.

        If the phone matches an existing walk-in account, returns ``needs_merge``
        (with a preview) so the LIFF can confirm; on ``confirm_merge=True`` the
        walk-in is merged into this LINE account. A phone already bound to a
        DIFFERENT LINE account is refused (anti-hijack).
        """
        user = self._live_user(reward_user_id)
        if not display_name or not display_name.strip():
            raise BadRequestException("display_name is required")
        if not pdpa_consent and not user.pdpa_consent_at:
            raise BadRequestException("PDPA consent is required")
        normalized = normalize_and_validate_thai_mobile(phone)

        other = (
            self.db.query(RewardUser)
            .filter(
                RewardUser.phone_number == normalized,
                RewardUser.id != reward_user_id,
                RewardUser.deleted_date.is_(None),
            )
            .order_by(RewardUser.created_date.asc())
            .first()
        )

        merged = False
        if other is not None:
            if other.line_user_id is not None:
                # Phone belongs to another LINE-linked account — refuse to take it over.
                raise BadRequestException("เบอร์นี้ผูกกับบัญชี LINE อื่นแล้ว")
            if not confirm_merge:
                return {"needs_merge": True, "walkin_preview": self._user_preview(other, None)}
            # Confirmed: set this LINE user's profile FIRST (form name wins, decision #4),
            # then merge the walk-in into it.
            self._apply_profile(user, display_name, normalized, date_of_birth, pdpa_consent)
            from .merge_service import MergeService
            MergeService(self.db).merge(
                survivor_id=user.id, victim_id=other.id, merge_type="auto_phone",
            )
            merged = True
        else:
            self._apply_profile(user, display_name, normalized, date_of_birth, pdpa_consent)

        self.db.flush()
        fresh = self._live_user(reward_user_id)
        result = self._user_preview(fresh, None)
        result["merged"] = merged
        result["needs_merge"] = False
        return result

    # ── walk-in helpers ───────────────────────────────────────────────────────

    def _live_user(self, reward_user_id: int) -> RewardUser:
        user = (
            self.db.query(RewardUser)
            .filter(RewardUser.id == reward_user_id, RewardUser.deleted_date.is_(None))
            .first()
        )
        if not user:
            raise NotFoundException("User not found")
        return user

    def _ensure_membership(self, reward_user_id: int, organization_id: int, role: str = "user"):
        """Return the user's live membership in the org, creating one if absent.

        Does NOT reactivate a membership an admin deactivated — claim logic surfaces
        that to the user with a clear message instead.
        """
        m = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if m:
            return m
        m = OrganizationRewardUser(
            reward_user_id=reward_user_id, organization_id=organization_id, role=role
        )
        self.db.add(m)
        self.db.flush()
        return m

    def _apply_profile(self, user: RewardUser, display_name: str, normalized_phone: str,
                       date_of_birth: str | None, pdpa_consent: bool) -> None:
        user.display_name = display_name.strip()
        user.phone_number = normalized_phone
        dob = self._parse_dob(date_of_birth)
        if dob is not None:
            user.date_of_birth = dob
        if pdpa_consent and not user.pdpa_consent_at:
            user.pdpa_consent_at = datetime.now(timezone.utc)

    def _user_preview(self, user: RewardUser, organization_id: int | None) -> dict:
        """Compact member card used by staff lookup + merge confirmation."""
        pts_q = self.db.query(
            func.coalesce(
                func.sum(
                    case((RewardPointTransaction.points > 0, RewardPointTransaction.points), else_=0)
                ), 0
            ).label("earned"),
            func.coalesce(func.sum(RewardPointTransaction.points), 0).label("balance"),
        ).filter(
            RewardPointTransaction.reward_user_id == user.id,
            RewardPointTransaction.deleted_date.is_(None),
        )
        if organization_id:
            pts_q = pts_q.filter(RewardPointTransaction.organization_id == organization_id)
        row = pts_q.one()
        return {
            "id": user.id,
            "display_name": user.display_name or user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "phone_number": user.phone_number,
            "has_line": user.line_user_id is not None,
            "created_via": user.created_via,
            "lifetime_earned": float(row.earned or 0),
            "current_balance": float(row.balance or 0),
        }

    @staticmethod
    def _parse_dob(value) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            raise BadRequestException("Invalid date_of_birth (expected YYYY-MM-DD)")

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

    def get_memberships(self, reward_user_id: int) -> list[dict]:
        """Get all organization memberships for a user (active AND deactivated).

        Returns deactivated rows too so the LIFF can render them grayed out
        instead of silently hiding. Caller filters by `is_active` when needed
        (e.g. staff-role detection should require is_active=True).
        """
        from ...models.subscriptions.organizations import Organization

        rows = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .all()
        )

        result = []
        for oru in rows:
            org = self.db.query(Organization).filter(Organization.id == oru.organization_id).first()
            result.append({
                "id": oru.id,
                "organization_id": oru.organization_id,
                "organization_name": org.name if org else None,
                "role": oru.role,
                "is_active": oru.is_active,
            })
        return result

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
