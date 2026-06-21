"""Tests for the admin members listing: credential filter + walk-in fields."""

from datetime import datetime, timezone

import pytest

from tests._reward_db import make_session
from GEPPPlatform.models.rewards.redemptions import RewardUser, OrganizationRewardUser
from GEPPPlatform.services.rewards.member_service import MemberService

ORG = 1


@pytest.fixture
def session():
    s = make_session()
    try:
        yield s
    finally:
        s.close()


def _member(session, *, name, line=None, phone=None, created_via="line", dob=None, consent=False):
    u = RewardUser(
        display_name=name, line_user_id=line, phone_number=phone, created_via=created_via,
        date_of_birth=dob,
        pdpa_consent_at=datetime.now(timezone.utc) if consent else None,
    )
    session.add(u)
    session.flush()
    session.add(OrganizationRewardUser(reward_user_id=u.id, organization_id=ORG, role="user"))
    session.flush()
    return u


def _seed(session):
    _member(session, name="LineOnly", line="Uline1", phone=None, created_via="line")
    _member(session, name="WalkinOnly", line=None, phone="0812345678", created_via="staff_walkin", consent=True)
    _member(session, name="Both", line="Uline2", phone="0898887777", created_via="line")


def test_credential_filter_walkin_only(session):
    _seed(session)
    res = MemberService(session).list_members(ORG, {"credential": "walkin_only"})
    names = {i["display_name"] for i in res["items"]}
    assert names == {"WalkinOnly"}


def test_credential_filter_line_only(session):
    _seed(session)
    res = MemberService(session).list_members(ORG, {"credential": "line_only"})
    names = {i["display_name"] for i in res["items"]}
    assert names == {"LineOnly"}


def test_credential_filter_both(session):
    _seed(session)
    res = MemberService(session).list_members(ORG, {"credential": "both"})
    names = {i["display_name"] for i in res["items"]}
    assert names == {"Both"}


def test_no_credential_filter_returns_all(session):
    _seed(session)
    res = MemberService(session).list_members(ORG, {})
    assert res["total"] == 3


def test_list_items_expose_walkin_fields(session):
    _member(session, name="WalkinOnly", line=None, phone="0812345678",
            created_via="staff_walkin", consent=True)
    res = MemberService(session).list_members(ORG, {"credential": "walkin_only"})
    item = res["items"][0]
    assert item["created_via"] == "staff_walkin"
    assert item["phone_number"] == "0812345678"
    assert item["pdpa_consent_at"] is not None
    assert "date_of_birth" in item
