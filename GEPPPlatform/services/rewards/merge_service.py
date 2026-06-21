"""Merge Service — combine two reward_users into one.

Used when a walk-in (phone-only) member and a LINE member turn out to be the same
person (auto-merge from LIFF profile completion), or when an admin manually merges
two accounts.

The merge re-points EVERY foreign-key reference to the victim onto the survivor:
  1. reward_point_transactions.reward_user_id
  2. reward_redemptions.reward_user_id
  3. reward_stocks.reward_user_id
  4. reward_staff_invites.used_by_id
  5. organization_reward_users.reward_user_id   (with per-org dedupe — see below)
then backfills the survivor's empty profile fields, soft-deletes the victim, and
writes a reward_user_merges audit row.

Atomicity: all work happens on the caller's session and is flushed at the end. The
route handler commits once on success; any exception bubbles up and the framework
rolls the whole transaction back, so a merge is all-or-nothing.

No automatic unmerge — the audit row records what moved for manual recovery.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.catalog import RewardStock
from ...models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    RewardRedemption,
    RewardStaffInvite,
    RewardUserMerge,
)
from ...exceptions import BadRequestException, NotFoundException


class MergeService:
    """Combine two reward_users (victim -> survivor) and record an audit trail."""

    def __init__(self, db: Session):
        self.db = db

    def merge(
        self,
        survivor_id: int,
        victim_id: int,
        merge_type: str,
        performed_by_user_id: int | None = None,
        performed_by_staff_id: int | None = None,
        organization_id: int | None = None,
    ) -> dict:
        if survivor_id == victim_id:
            raise BadRequestException("Cannot merge a member into itself")

        survivor = self._get_live_user(survivor_id)
        victim = self._get_live_user(victim_id)

        moved = {"point_tx": 0, "redemptions": 0, "stocks": 0, "invites": 0, "memberships": 0}

        # 1-2-3-4. Re-point the simple ledger/reference tables (bulk update).
        moved["point_tx"] = (
            self.db.query(RewardPointTransaction)
            .filter(RewardPointTransaction.reward_user_id == victim_id)
            .update({RewardPointTransaction.reward_user_id: survivor_id}, synchronize_session=False)
        )
        moved["redemptions"] = (
            self.db.query(RewardRedemption)
            .filter(RewardRedemption.reward_user_id == victim_id)
            .update({RewardRedemption.reward_user_id: survivor_id}, synchronize_session=False)
        )
        moved["stocks"] = (
            self.db.query(RewardStock)
            .filter(RewardStock.reward_user_id == victim_id)
            .update({RewardStock.reward_user_id: survivor_id}, synchronize_session=False)
        )
        moved["invites"] = (
            self.db.query(RewardStaffInvite)
            .filter(RewardStaffInvite.used_by_id == victim_id)
            .update({RewardStaffInvite.used_by_id: survivor_id}, synchronize_session=False)
        )

        # 5. Org memberships — dedupe per org (no DB unique constraint exists).
        moved["memberships"] = self._merge_memberships(survivor_id, victim_id)

        # Backfill survivor's empty fields from victim (never overwrites existing values —
        # so a name the user just typed on the survivor wins per product decision #4).
        self._backfill_profile(survivor, victim)

        # Soft-delete the victim.
        now = datetime.now(timezone.utc)
        victim.deleted_date = now
        victim.is_active = False

        # Audit.
        audit = RewardUserMerge(
            survivor_user_id=survivor_id,
            victim_user_id=victim_id,
            organization_id=organization_id,
            merge_type=merge_type,
            moved_counts=moved,
            performed_by_user_id=performed_by_user_id,
            performed_by_staff_id=performed_by_staff_id,
        )
        self.db.add(audit)
        self.db.flush()

        return {
            "success": True,
            "survivor_user_id": survivor_id,
            "victim_user_id": victim_id,
            "moved_counts": moved,
        }

    # ── helpers ─────────────────────────────────────────────────────────────

    def _get_live_user(self, user_id: int) -> RewardUser:
        user = (
            self.db.query(RewardUser)
            .filter(RewardUser.id == user_id, RewardUser.deleted_date.is_(None))
            .first()
        )
        if not user:
            raise NotFoundException(f"Reward user {user_id} not found or already merged")
        return user

    def _live_memberships(self, user_id: int) -> list[OrganizationRewardUser]:
        return (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == user_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .all()
        )

    def _merge_memberships(self, survivor_id: int, victim_id: int) -> int:
        """Move victim's org memberships to survivor without creating duplicates.

        For each org where the survivor ALSO has a membership: fold role/active state
        into the survivor's row (staff > user; active OR active) and soft-delete the
        victim's. For orgs the survivor isn't in yet: re-point the victim's row.
        """
        survivor_by_org: dict[int, OrganizationRewardUser] = {}
        for m in self._live_memberships(survivor_id):
            survivor_by_org.setdefault(m.organization_id, m)

        now = datetime.now(timezone.utc)
        processed = 0
        for vm in self._live_memberships(victim_id):
            sm = survivor_by_org.get(vm.organization_id)
            if sm is None:
                # Survivor not in this org — re-point victim's membership.
                vm.reward_user_id = survivor_id
                survivor_by_org[vm.organization_id] = vm
            else:
                # Both in this org — merge into survivor's row, retire victim's.
                if vm.role == "staff" and sm.role != "staff":
                    sm.role = "staff"
                if vm.is_active and not sm.is_active:
                    sm.is_active = True
                vm.deleted_date = now
                vm.is_active = False
            processed += 1

        self.db.flush()
        return processed

    def _backfill_profile(self, survivor: RewardUser, victim: RewardUser) -> None:
        if not survivor.phone_number and victim.phone_number:
            survivor.phone_number = victim.phone_number
        if not survivor.display_name and victim.display_name:
            survivor.display_name = victim.display_name
        if not survivor.date_of_birth and victim.date_of_birth:
            survivor.date_of_birth = victim.date_of_birth
        if not survivor.pdpa_consent_at and victim.pdpa_consent_at:
            survivor.pdpa_consent_at = victim.pdpa_consent_at
        if not survivor.email and victim.email:
            survivor.email = victim.email
