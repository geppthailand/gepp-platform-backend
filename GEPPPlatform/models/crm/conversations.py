"""CRM conversation inbox — outbound threads + inbound replies via Mailchimp inbound webhook."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Integer, DateTime
from sqlalchemy.sql import func

from ..base import Base


class CrmConversation(Base):
    __tablename__ = 'crm_conversations'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'))
    lead_id = Column(BigInteger, ForeignKey('crm_leads.id', ondelete='SET NULL'))
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id', ondelete='SET NULL'))
    subject = Column(String(500))
    thread_token = Column(String(64), nullable=False, unique=True)
    status = Column(String(16), nullable=False, default='open')
    last_message_at = Column(DateTime(timezone=True))
    unread_count = Column(Integer, nullable=False, default=0)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CrmConversationMessage(Base):
    __tablename__ = 'crm_conversation_messages'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        BigInteger,
        ForeignKey('crm_conversations.id', ondelete='CASCADE'),
        nullable=False,
    )
    direction = Column(String(8), nullable=False)  # 'outbound' | 'inbound'
    delivery_id = Column(BigInteger, ForeignKey('crm_campaign_deliveries.id', ondelete='SET NULL'))
    from_email = Column(String(255))
    to_email = Column(String(255))
    subject = Column(String(500))
    body_html = Column(Text)
    body_plain = Column(Text)
    mandrill_message_id = Column(String(255))
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
