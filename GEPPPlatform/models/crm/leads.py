"""CRM Leads + Lead Activities — Sprint 9 Phase 2 Lead Management System."""

from sqlalchemy import (
    Column, String, Text, ForeignKey, BigInteger, DateTime, Integer, JSON,
)

from ..base import Base, BaseModel


class CrmLead(Base, BaseModel):
    """
    One row per (organization_id, lower(email)) prospect.

    Lifecycle:  new → contacted → qualified → negotiating → customer | lost
    Sources:    web_form, csv_import, api, manual, event, referral
    """
    __tablename__ = 'crm_leads'

    organization_id   = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    email             = Column(String(255), nullable=False)   # always lowercased
    first_name        = Column(String(128))
    last_name         = Column(String(128))
    company           = Column(String(255))
    job_title         = Column(String(255))
    phone             = Column(String(64))
    country           = Column(String(64))
    language          = Column(String(8))
    source            = Column(String(64))    # web_form | csv_import | api | manual | event | referral
    source_metadata   = Column(JSON)
    status            = Column(String(16), nullable=False, default='new')
    status_changed_at = Column(DateTime(timezone=True))
    lead_score        = Column(Integer, nullable=False, default=0)
    owner_user_id     = Column(BigInteger, ForeignKey('user_locations.id'))
    tags              = Column(JSON)          # array of tag strings
    notes             = Column(Text)
    converted_user_id = Column(BigInteger, ForeignKey('user_locations.id'))
    converted_at      = Column(DateTime(timezone=True))
    last_activity_at  = Column(DateTime(timezone=True))


class CrmLeadActivity(Base):
    """
    Append-only activity log for crm_leads.  Never updated — only inserted.
    """
    __tablename__ = 'crm_lead_activities'

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    lead_id       = Column(BigInteger, ForeignKey('crm_leads.id', ondelete='CASCADE'), nullable=False)
    activity_type = Column(String(64), nullable=False)
    properties    = Column(JSON)
    performed_by  = Column(BigInteger, ForeignKey('user_locations.id'))
    occurred_at   = Column(DateTime(timezone=True), nullable=False)
