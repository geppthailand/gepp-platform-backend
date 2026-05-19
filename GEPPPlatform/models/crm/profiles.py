"""CRM per-user + per-org denormalized profiles (refreshed nightly from crm_events)."""

from sqlalchemy import Column, String, ForeignKey, BigInteger, DateTime, Integer, Boolean, Numeric

from ..base import Base


class CrmUserProfile(Base):
    __tablename__ = 'crm_user_profiles'

    user_location_id = Column(BigInteger, ForeignKey('user_locations.id', ondelete='CASCADE'), primary_key=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    last_login_at = Column(DateTime(timezone=True))
    days_since_last_login = Column(Integer)
    login_count_30d = Column(Integer, nullable=False, default=0)
    transaction_count_30d = Column(Integer, nullable=False, default=0)
    transaction_count_lifetime = Column(Integer, nullable=False, default=0)
    qr_count_30d = Column(Integer, nullable=False, default=0)
    reward_claim_count_30d = Column(Integer, nullable=False, default=0)
    iot_readings_count_30d = Column(Integer, nullable=False, default=0)
    gri_submission_count_30d = Column(Integer, nullable=False, default=0)
    traceability_count_30d = Column(Integer, nullable=False, default=0)
    first_login_at = Column(DateTime(timezone=True))
    onboarded = Column(Boolean, nullable=False, default=False)
    engagement_score = Column(Numeric(5, 2), nullable=False, default=0)
    activity_tier = Column(String(16), nullable=False, default='dormant')
    last_profile_refresh_at = Column(DateTime(timezone=True))
    created_date = Column(DateTime(timezone=True))
    updated_date = Column(DateTime(timezone=True))


class CrmOrgProfile(Base):
    __tablename__ = 'crm_org_profiles'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    active_user_count_30d = Column(Integer, nullable=False, default=0)
    total_user_count = Column(Integer, nullable=False, default=0)
    active_user_ratio = Column(Numeric(5, 2), nullable=False, default=0)
    transaction_count_30d = Column(Integer, nullable=False, default=0)
    traceability_count_30d = Column(Integer, nullable=False, default=0)
    gri_submission_count_30d = Column(Integer, nullable=False, default=0)
    subscription_plan_id = Column(BigInteger)
    subscription_active = Column(Boolean, nullable=False, default=False)
    quota_used_pct = Column(Numeric(5, 2))
    activity_tier = Column(String(16), nullable=False, default='dormant')
    last_activity_at = Column(DateTime(timezone=True))
    last_profile_refresh_at = Column(DateTime(timezone=True))
    created_date = Column(DateTime(timezone=True))
    updated_date = Column(DateTime(timezone=True))
