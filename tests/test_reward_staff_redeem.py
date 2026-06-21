"""Tests for RedeemService.staff_redeem — staff redeems on behalf of a member.

Verifies the orchestration of submit_redemption + confirm_redemption: points and
stock are deducted, the redemption completes with staff_id, and failure cases leave
no partial state.
"""

from datetime import datetime, timezone

import pytest

from tests._reward_db import make_session
from GEPPPlatform.models.rewards.redemptions import RewardUser, OrganizationRewardUser, RewardRedemption
from GEPPPlatform.models.rewards.points import RewardPointTransaction
from GEPPPlatform.models.rewards.catalog import RewardStock, RewardCatalog
from GEPPPlatform.models.rewards.management import RewardCampaign, RewardCampaignCatalog
from GEPPPlatform.services.rewards.redeem_service import RedeemService
from GEPPPlatform.libs.exceptions import APIException
from sqlalchemy import func

ORG = 1
STAFF = 77  # staff org_reward_user.id


@pytest.fixture
def session():
    s = make_session()
    try:
        yield s
    finally:
        s.close()


def _balance(session, reward_user_id, campaign_id):
    return float(
        session.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
        .filter(
            RewardPointTransaction.reward_user_id == reward_user_id,
            RewardPointTransaction.reward_campaign_id == campaign_id,
            RewardPointTransaction.deleted_date.is_(None),
        )
        .scalar()
    )


def _campaign_stock(session, catalog_id, campaign_id):
    return int(
        session.query(func.coalesce(func.sum(RewardStock.values), 0))
        .filter(
            RewardStock.reward_catalog_id == catalog_id,
            RewardStock.reward_campaign_id == campaign_id,
            RewardStock.deleted_date.is_(None),
        )
        .scalar()
    )


def _setup(session, *, member_points=500, stock=10, points_cost=100,
           membership_active=True, limit_per_user=None):
    """Build a redeemable world: member + active membership + campaign + catalog + stock + points."""
    now = datetime.now(timezone.utc)
    member = RewardUser(display_name="สมชาย", phone_number="0812345678", created_via="staff_walkin")
    session.add(member)
    session.flush()
    session.add(OrganizationRewardUser(
        reward_user_id=member.id, organization_id=ORG, role="user", is_active=membership_active,
    ))
    campaign = RewardCampaign(organization_id=ORG, name="ลดโลกร้อน", start_date=now, end_date=None, status="active")
    session.add(campaign)
    session.flush()
    catalog = RewardCatalog(organization_id=ORG, name="ถุงผ้า GEPP", status="active",
                            limit_per_user_per_campaign=limit_per_user)
    session.add(catalog)
    session.flush()
    session.add(RewardCampaignCatalog(
        campaign_id=campaign.id, catalog_id=catalog.id, points_cost=points_cost, status="active",
    ))
    # Campaign-allocated stock (deposit)
    session.add(RewardStock(
        reward_catalog_id=catalog.id, reward_campaign_id=campaign.id, values=stock, ledger_type="deposit",
    ))
    # Give the member points in this campaign
    if member_points:
        session.add(RewardPointTransaction(
            organization_id=ORG, reward_user_id=member.id, reward_campaign_id=campaign.id,
            points=member_points, reference_type="claim", claimed_date=now,
        ))
    session.flush()
    return member, campaign, catalog


def test_staff_redeem_happy_path_deducts_points_and_stock(session):
    member, campaign, catalog = _setup(session, member_points=500, stock=10, points_cost=100)

    result = RedeemService(session).staff_redeem(
        staff_org_user_id=STAFF, reward_user_id=member.id, organization_id=ORG,
        campaign_id=campaign.id, items=[{"catalog_id": catalog.id, "quantity": 2}],
    )
    session.flush()

    assert result["success"] is True
    # Points: 500 - (100 * 2) = 300
    assert _balance(session, member.id, campaign.id) == 300
    # Stock: 10 - 2 = 8 (a -2 withdrawal row added)
    assert _campaign_stock(session, catalog.id, campaign.id) == 8
    # Redemption completed + staff attributed
    redemption = session.query(RewardRedemption).filter_by(reward_user_id=member.id).one()
    assert redemption.status == "completed"
    assert redemption.staff_id == STAFF
    # A redeem-type stock withdrawal row exists
    withdrawal = (
        session.query(RewardStock)
        .filter(RewardStock.reward_user_id == member.id, RewardStock.ledger_type == "redeem")
        .one()
    )
    assert withdrawal.values == -2


def test_staff_redeem_insufficient_points_rejected_no_deduction(session):
    member, campaign, catalog = _setup(session, member_points=50, stock=10, points_cost=100)
    with pytest.raises(APIException):
        RedeemService(session).staff_redeem(
            staff_org_user_id=STAFF, reward_user_id=member.id, organization_id=ORG,
            campaign_id=campaign.id, items=[{"catalog_id": catalog.id, "quantity": 1}],
        )
    # Balance untouched, no completed redemption, stock untouched
    assert _balance(session, member.id, campaign.id) == 50
    assert _campaign_stock(session, catalog.id, campaign.id) == 10


def test_staff_redeem_insufficient_stock_rejected(session):
    member, campaign, catalog = _setup(session, member_points=500, stock=1, points_cost=100)
    with pytest.raises(APIException):
        RedeemService(session).staff_redeem(
            staff_org_user_id=STAFF, reward_user_id=member.id, organization_id=ORG,
            campaign_id=campaign.id, items=[{"catalog_id": catalog.id, "quantity": 5}],
        )
    assert _balance(session, member.id, campaign.id) == 500
    assert _campaign_stock(session, catalog.id, campaign.id) == 1


def test_staff_redeem_deactivated_member_blocked(session):
    member, campaign, catalog = _setup(session, membership_active=False)
    with pytest.raises(APIException):
        RedeemService(session).staff_redeem(
            staff_org_user_id=STAFF, reward_user_id=member.id, organization_id=ORG,
            campaign_id=campaign.id, items=[{"catalog_id": catalog.id, "quantity": 1}],
        )


def test_staff_redeem_respects_per_user_limit(session):
    member, campaign, catalog = _setup(session, member_points=500, stock=10, points_cost=100, limit_per_user=1)
    svc = RedeemService(session)
    # First redemption ok
    svc.staff_redeem(staff_org_user_id=STAFF, reward_user_id=member.id, organization_id=ORG,
                     campaign_id=campaign.id, items=[{"catalog_id": catalog.id, "quantity": 1}])
    session.flush()
    # Second exceeds limit_per_user_per_campaign=1
    with pytest.raises(APIException):
        svc.staff_redeem(staff_org_user_id=STAFF, reward_user_id=member.id, organization_id=ORG,
                         campaign_id=campaign.id, items=[{"catalog_id": catalog.id, "quantity": 1}])
