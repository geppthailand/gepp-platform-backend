"""Tests for PublicRewardService walk-in member methods."""

import pytest

from tests._reward_db import make_session
from GEPPPlatform.models.rewards.redemptions import RewardUser, OrganizationRewardUser
from GEPPPlatform.models.rewards.points import RewardPointTransaction
from GEPPPlatform.services.rewards.public_service import PublicRewardService
from GEPPPlatform.libs.exceptions import APIException

ORG = 1
STAFF = 50


@pytest.fixture
def session():
    s = make_session()
    try:
        yield s
    finally:
        s.close()


def _svc(session):
    return PublicRewardService(session)


def _line_user(session, line_id="Uline_abc", name="Som"):
    u = RewardUser(display_name=name, line_user_id=line_id, created_via="line")
    session.add(u)
    session.flush()
    return u


# ── register_walkin ──────────────────────────────────────────────────────────

def test_register_walkin_creates_member_and_membership(session):
    out = _svc(session).register_walkin(
        staff_org_user_id=STAFF, organization_id=ORG,
        display_name="สมศักดิ์", phone="081-234-5678", pdpa_consent=True,
    )
    assert out["existing"] is False
    assert out["phone_number"] == "0812345678"  # normalized
    assert out["has_line"] is False

    user = session.query(RewardUser).filter_by(id=out["id"]).one()
    assert user.created_via == "staff_walkin"
    assert user.created_by_staff_id == STAFF
    assert user.pdpa_consent_at is not None

    membership = session.query(OrganizationRewardUser).filter_by(
        reward_user_id=out["id"], organization_id=ORG
    ).one()
    assert membership.role == "user"


def test_register_walkin_duplicate_phone_returns_existing_no_dup(session):
    svc = _svc(session)
    first = svc.register_walkin(STAFF, ORG, "สมศักดิ์", "0812345678", pdpa_consent=True)
    second = svc.register_walkin(STAFF, ORG, "อีกชื่อ", "081-234-5678", pdpa_consent=True)

    assert second["existing"] is True
    assert second["id"] == first["id"]
    # Only one reward_user with this phone.
    assert session.query(RewardUser).filter_by(phone_number="0812345678").count() == 1


def test_register_walkin_requires_pdpa(session):
    with pytest.raises(APIException):
        _svc(session).register_walkin(STAFF, ORG, "สมศักดิ์", "0812345678", pdpa_consent=False)


def test_register_walkin_rejects_invalid_phone(session):
    with pytest.raises(APIException):
        _svc(session).register_walkin(STAFF, ORG, "สมศักดิ์", "07123", pdpa_consent=True)


# ── resolve_user_by_phone ────────────────────────────────────────────────────

def test_resolve_by_phone_matches_normalized_variants(session):
    svc = _svc(session)
    created = svc.register_walkin(STAFF, ORG, "สมศักดิ์", "0812345678", pdpa_consent=True)
    for variant in ["0812345678", "081-234-5678", "+66812345678"]:
        found = svc.resolve_user_by_phone(variant, organization_id=ORG)
        assert found is not None and found["id"] == created["id"]


def test_resolve_by_phone_returns_none_when_absent(session):
    assert _svc(session).resolve_user_by_phone("0899999999") is None


# ── complete_profile ─────────────────────────────────────────────────────────

def test_complete_profile_no_match_updates_user(session):
    user = _line_user(session)
    out = _svc(session).complete_profile(
        reward_user_id=user.id, display_name="ชื่อจริง", phone="0898887777",
        date_of_birth="1990-05-01", pdpa_consent=True,
    )
    assert out["merged"] is False
    session.refresh(user)
    assert user.phone_number == "0898887777"
    assert user.display_name == "ชื่อจริง"
    assert user.pdpa_consent_at is not None
    assert str(user.date_of_birth) == "1990-05-01"


def test_complete_profile_match_without_confirm_returns_needs_merge(session):
    svc = _svc(session)
    walkin = svc.register_walkin(STAFF, ORG, "สมศักดิ์", "0812345678", pdpa_consent=True)
    line_user = _line_user(session)
    out = svc.complete_profile(line_user.id, "Som", "0812345678", pdpa_consent=True)
    assert out["needs_merge"] is True
    assert out["walkin_preview"]["id"] == walkin["id"]


def test_complete_profile_confirm_merges_walkin_into_line(session):
    svc = _svc(session)
    walkin = svc.register_walkin(STAFF, ORG, "สมศักดิ์", "0812345678", pdpa_consent=True)
    # Walk-in earned some points.
    session.add(RewardPointTransaction(organization_id=ORG, reward_user_id=walkin["id"], points=25))
    session.flush()

    line_user = _line_user(session)
    out = svc.complete_profile(line_user.id, "Som ใหม่", "0812345678", pdpa_consent=True, confirm_merge=True)
    session.flush()

    assert out["merged"] is True
    # Points moved to the LINE survivor.
    assert session.query(RewardPointTransaction).filter_by(reward_user_id=line_user.id).count() == 1
    # Survivor keeps the name from the form (decision #4).
    session.refresh(line_user)
    assert line_user.display_name == "Som ใหม่"
    # Walk-in victim soft-deleted.
    victim = session.query(RewardUser).filter_by(id=walkin["id"]).one()
    assert victim.deleted_date is not None


def test_register_user_sets_needs_profile_until_phone_and_consent(session):
    svc = _svc(session)
    out = svc.register_user({"line_user_id": "Unew", "display_name": "Som"})
    assert out["needs_profile"] is True  # no phone / no consent yet

    svc.complete_profile(out["id"], "Som", "0812345678", pdpa_consent=True)
    again = svc.register_user({"line_user_id": "Unew"})  # idempotent re-register on next open
    assert again["needs_profile"] is False


def test_complete_profile_phone_bound_to_other_line_is_refused(session):
    svc = _svc(session)
    # Another LINE account already owns this phone.
    other = _line_user(session, line_id="Uline_other", name="Other")
    other.phone_number = "0812345678"
    session.flush()

    me = _line_user(session, line_id="Uline_me")
    with pytest.raises(APIException):
        svc.complete_profile(me.id, "Me", "0812345678", pdpa_consent=True, confirm_merge=True)
