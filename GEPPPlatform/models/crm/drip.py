"""CRM Drip Sequences — Sprint 10."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Integer, JSON

from ..base import Base, BaseModel


class CrmDripSequence(Base, BaseModel):
    """
    A drip sequence defines a series of timed emails sent automatically
    when a trigger event (e.g. lead_created, lead_status_changed) fires.

    Lifecycle: draft → active → paused → archived
    """
    __tablename__ = 'crm_drip_sequences'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    name            = Column(String(255), nullable=False)
    description     = Column(Text)
    trigger_event   = Column(String(64))     # 'lead_created'|'lead_status_changed'|'user_first_login'|...
    trigger_config  = Column(JSON)           # e.g. {"targetStatus": "qualified"}
    status          = Column(String(16), nullable=False, default='draft')
    created_by      = Column(BigInteger, ForeignKey('user_locations.id'))


class CrmDripStep(Base):
    """One step in a drip sequence — a template sent after a delay."""
    __tablename__ = 'crm_drip_steps'

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    sequence_id  = Column(BigInteger, ForeignKey('crm_drip_sequences.id', ondelete='CASCADE'), nullable=False)
    step_index   = Column(Integer, nullable=False)
    template_id  = Column(BigInteger, ForeignKey('crm_email_templates.id'), nullable=False)
    delay_days   = Column(Integer, nullable=False, default=0)
    delay_hours  = Column(Integer, nullable=False, default=0)
    skip_filter  = Column(JSON)              # property_filter spec


class CrmDripEnrollment(Base):
    """Tracks one lead/user's progress through a drip sequence."""
    __tablename__ = 'crm_drip_enrollments'

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    sequence_id      = Column(BigInteger, ForeignKey('crm_drip_sequences.id'), nullable=False)
    lead_id          = Column(BigInteger, ForeignKey('crm_leads.id'))
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    current_step     = Column(Integer, nullable=False, default=0)
    next_step_at     = Column(DateTime(timezone=True), nullable=False)
    status           = Column(String(16), nullable=False, default='active')
    enrolled_at      = Column(DateTime(timezone=True))
    completed_at     = Column(DateTime(timezone=True))
