"""CRM campaigns + per-recipient deliveries with Mailchimp Transactional correlation."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Integer, JSON

from ..base import Base, BaseModel


class CrmCampaign(Base, BaseModel):
    __tablename__ = 'crm_campaigns'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    campaign_type = Column(String(16), nullable=False)  # 'trigger' | 'blast'
    trigger_event = Column(String(64))
    trigger_config = Column(JSON)
    segment_id = Column(BigInteger, ForeignKey('crm_segments.id'))
    template_id = Column(BigInteger, ForeignKey('crm_email_templates.id'), nullable=False)
    status = Column(String(16), nullable=False, default='draft')
    scheduled_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    send_from_name = Column(String(255))
    send_from_email = Column(String(255))
    reply_to = Column(String(255))
    cc_list_id = Column(BigInteger)  # FK to crm_email_lists added in migration 035
    recipient_list_id = Column(BigInteger, ForeignKey('crm_email_lists.id', ondelete='SET NULL'))
    metrics_cache = Column(JSON)
    last_trigger_eval_at = Column(DateTime(timezone=True))
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))


class CrmCampaignDelivery(Base):
    __tablename__ = 'crm_campaign_deliveries'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id = Column(BigInteger, ForeignKey('crm_campaigns.id', ondelete='CASCADE'), nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    recipient_email = Column(String(255), nullable=False)
    status = Column(String(16), nullable=False, default='pending')
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    first_clicked_at = Column(DateTime(timezone=True))
    open_count = Column(Integer, nullable=False, default=0)
    click_count = Column(Integer, nullable=False, default=0)
    mandrill_message_id = Column(String(255), unique=True)
    mandrill_response = Column(JSON)
    error_message = Column(Text)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True))
    rendered_subject = Column(String(500))
    rendered_body_hash = Column(String(64))
    created_date = Column(DateTime(timezone=True))
    updated_date = Column(DateTime(timezone=True))
