"""Integration tests for MergeService — the bug-critical reward_users merge.

Runs against an in-memory SQLite DB. The Postgres-only column types (JSONB, UUID)
are taught to compile on SQLite via @compiles shims so we can create just the
reward tables involved in a merge. SQLite FK enforcement is off by default, so we
don't need to materialize every FK target table (organizations, campaigns, ...).
"""

import pytest

from tests._reward_db import make_session
from GEPPPlatform.models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    RewardRedemption,
    RewardStaffInvite,
    RewardUserMerge,
)
from GEPPPlatform.models.rewards.points import RewardPointTransaction
from GEPPPlatform.models.rewards.catalog import RewardStock
from GEPPPlatform.services.rewards.merge_service import MergeService
from GEPPPlatform.libs.exceptions import APIException


@pytest.fixture
def session():
    s = make_session()
    try:
        yield s
    finally:
        s.close()


def _line_user(s, name="Som"):
    u = RewardUser(display_name=name, line_user_id="Uline123", created_via="line")
    s.add(u)
    s.flush()
    return u


def _walkin_user(s, name="สมศักดิ์", phone="0812345678"):
    u = RewardUser(display_name=name, phone_number=phone, created_via="staff_walkin")
    s.add(u)
    s.flush()
    return u


def test_merge_repoints_all_ledger_tables_and_softdeletes_victim(session):
    survivor = _line_user(session)
    victim = _walkin_user(session)

    session.add(RewardPointTransaction(organization_id=1, reward_user_id=victim.id, points=25))
    session.add(RewardRedemption(
        organization_id=1, reward_user_id=victim.id, reward_campaign_id=1,
        catalog_id=1, points_redeemed=10, hash="h-redeem-1",
    ))
    session.add(RewardStock(reward_catalog_id=1, values=-1, reward_user_id=victim.id, ledger_type="redeem"))
    session.add(RewardStaffInvite(hash="h-invite-1", organization_id=1, created_by_id=99, used_by_id=victim.id))
    session.flush()

    result = MergeService(session).merge(survivor.id, victim.id, merge_type="auto_phone")
    session.flush()

    # All ledgers now point at survivor.
    assert session.query(RewardPointTransaction).filter_by(reward_user_id=survivor.id).count() == 1
    assert session.query(RewardPointTransaction).filter_by(reward_user_id=victim.id).count() == 0
    assert session.query(RewardRedemption).filter_by(reward_user_id=survivor.id).count() == 1
    assert session.query(RewardStock).filter_by(reward_user_id=survivor.id).count() == 1
    assert session.query(RewardStaffInvite).filter_by(used_by_id=survivor.id).count() == 1

    # Victim soft-deleted.
    session.refresh(victim)
    assert victim.deleted_date is not None
    assert victim.is_active is False

    # Audit row written with accurate counts.
    audit = session.query(RewardUserMerge).one()
    assert audit.survivor_user_id == survivor.id
    assert audit.victim_user_id == victim.id
    assert audit.merge_type == "auto_phone"
    assert audit.moved_counts["point_tx"] == 1
    assert audit.moved_counts["redemptions"] == 1
    assert audit.moved_counts["stocks"] == 1
    assert audit.moved_counts["invites"] == 1
    assert result["moved_counts"]["memberships"] == 0


def test_merge_dedupes_memberships_and_promotes_staff(session):
    survivor = _line_user(session)
    victim = _walkin_user(session)

    # Survivor is a plain user in org 1.
    session.add(OrganizationRewardUser(reward_user_id=survivor.id, organization_id=1, role="user"))
    # Victim is STAFF in org 1 (overlap) and a user in org 2 (survivor not a member).
    session.add(OrganizationRewardUser(reward_user_id=victim.id, organization_id=1, role="staff"))
    session.add(OrganizationRewardUser(reward_user_id=victim.id, organization_id=2, role="user"))
    session.flush()

    MergeService(session).merge(survivor.id, victim.id, merge_type="manual_admin")
    session.flush()

    live = (
        session.query(OrganizationRewardUser)
        .filter(OrganizationRewardUser.reward_user_id == survivor.id,
                OrganizationRewardUser.deleted_date.is_(None))
        .all()
    )
    by_org = {m.organization_id: m for m in live}
    # No duplicate membership in org 1; survivor promoted to staff (staff > user).
    assert set(by_org.keys()) == {1, 2}
    assert by_org[1].role == "staff"
    # Org-2 membership re-pointed to survivor.
    assert by_org[2].organization_id == 2
    # Victim has no live memberships left.
    assert (
        session.query(OrganizationRewardUser)
        .filter(OrganizationRewardUser.reward_user_id == victim.id,
                OrganizationRewardUser.deleted_date.is_(None))
        .count()
    ) == 0


def test_merge_backfills_missing_fields_but_keeps_survivor_name(session):
    # Survivor (LINE) already has the name the user just typed; no phone yet.
    survivor = _line_user(session, name="Som ที่กรอกเอง")
    victim = _walkin_user(session, name="สมศักดิ์ ใจดี", phone="0898887777")

    MergeService(session).merge(survivor.id, victim.id, merge_type="auto_phone")
    session.flush()
    session.refresh(survivor)

    assert survivor.display_name == "Som ที่กรอกเอง"  # decision #4: form name wins
    assert survivor.phone_number == "0898887777"       # backfilled from victim


def test_self_merge_is_rejected(session):
    u = _line_user(session)
    with pytest.raises(APIException):
        MergeService(session).merge(u.id, u.id, merge_type="manual_admin")


def test_merge_missing_user_raises(session):
    survivor = _line_user(session)
    with pytest.raises(APIException):
        MergeService(session).merge(survivor.id, 999999, merge_type="manual_admin")
