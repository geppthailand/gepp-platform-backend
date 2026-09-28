"""Registration-QR handling in PublicRewardService.register_user.

The backoffice "ลิงก์สมัครสมาชิก" QR encodes `reward_setup.hash`. Before this was
wired up the hash reached the LIFF and stopped there: membership only appeared on
the member's first claim, so a member recruited by a QR who never claimed anything
was invisible to the org that recruited them.

The rules worth locking down are the failure modes, not the happy path:
  * an unknown / regenerated hash must NOT fail the call — this endpoint is also
    the plain login path for every returning member;
  * re-scanning must not create a second membership;
  * it must not reactivate a membership an admin switched off.
"""

import pytest

from tests._reward_db import make_session
from GEPPPlatform.models.rewards.redemptions import RewardUser, OrganizationRewardUser
from GEPPPlatform.models.rewards.management import RewardSetup
from GEPPPlatform.services.rewards.public_service import PublicRewardService

ORG = 77
PROGRAM_HASH = "a1b2c3d4e5f6"
LINE_ID = "Uregister_test_001"


@pytest.fixture
def session():
    s = make_session()
    try:
        yield s
    finally:
        s.close()


def _svc(session):
    return PublicRewardService(session)


def _program(session, org_id=ORG, hash_=PROGRAM_HASH, name="Zero Waste Tower"):
    setup = RewardSetup(
        organization_id=org_id, hash=hash_,
        program_name=name, program_name_local="โครงการลดขยะ",
    )
    session.add(setup)
    session.flush()
    return setup


def _memberships(session, reward_user_id, org_id=ORG):
    return (
        session.query(OrganizationRewardUser)
        .filter(
            OrganizationRewardUser.reward_user_id == reward_user_id,
            OrganizationRewardUser.organization_id == org_id,
            OrganizationRewardUser.deleted_date.is_(None),
        )
        .all()
    )


# ── happy path ───────────────────────────────────────────────────────────────

def test_program_hash_creates_membership_for_new_member(session):
    _program(session)

    out = _svc(session).register_user({
        "line_user_id": LINE_ID, "display_name": "Som", "program_hash": PROGRAM_HASH,
    })

    assert out["joined_program"] == {
        "organization_id": ORG, "program_name": "โครงการลดขยะ",
    }
    rows = _memberships(session, out["id"])
    assert len(rows) == 1
    assert rows[0].role == "user"


def test_program_name_falls_back_to_english_when_no_local_name(session):
    setup = _program(session)
    setup.program_name_local = None
    session.flush()

    out = _svc(session).register_user({
        "line_user_id": LINE_ID, "program_hash": PROGRAM_HASH,
    })

    assert out["joined_program"]["program_name"] == "Zero Waste Tower"


# ── the hash must never be able to break login ───────────────────────────────

def test_unknown_hash_still_registers_the_member(session):
    out = _svc(session).register_user({
        "line_user_id": LINE_ID, "display_name": "Som", "program_hash": "no-such-hash",
    })

    assert out["id"]
    assert out["joined_program"] is None
    assert _memberships(session, out["id"]) == []


def test_soft_deleted_program_is_treated_as_unknown(session):
    setup = _program(session)
    from datetime import datetime, timezone
    setup.deleted_date = datetime.now(timezone.utc)
    session.flush()

    out = _svc(session).register_user({
        "line_user_id": LINE_ID, "program_hash": PROGRAM_HASH,
    })

    assert out["joined_program"] is None
    assert _memberships(session, out["id"]) == []


def test_no_hash_leaves_registration_unchanged(session):
    _program(session)

    out = _svc(session).register_user({"line_user_id": LINE_ID, "display_name": "Som"})

    assert out["joined_program"] is None
    assert _memberships(session, out["id"]) == []


# ── idempotency / admin intent ───────────────────────────────────────────────

def test_rescanning_the_qr_does_not_duplicate_membership(session):
    _program(session)
    svc = _svc(session)
    payload = {"line_user_id": LINE_ID, "program_hash": PROGRAM_HASH}

    first = svc.register_user(payload)
    second = svc.register_user(payload)

    assert first["id"] == second["id"]
    assert len(_memberships(session, first["id"])) == 1


def test_does_not_reactivate_a_membership_an_admin_switched_off(session):
    _program(session)
    user = RewardUser(display_name="Som", line_user_id=LINE_ID)
    session.add(user)
    session.flush()
    membership = OrganizationRewardUser(
        reward_user_id=user.id, organization_id=ORG, role="user", is_active=False,
    )
    session.add(membership)
    session.flush()

    out = _svc(session).register_user({
        "line_user_id": LINE_ID, "program_hash": PROGRAM_HASH,
    })

    # The join reports success (the program resolved) but the deactivated
    # membership stays deactivated — re-scanning a QR must not undo an admin's
    # decision. Same stance as PublicRewardService._ensure_membership.
    assert out["joined_program"]["organization_id"] == ORG
    rows = _memberships(session, user.id)
    assert len(rows) == 1
    assert rows[0].is_active is False
