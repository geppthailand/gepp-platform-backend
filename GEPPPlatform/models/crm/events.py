"""CRM event log — lean, indexed for org/time aggregation."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, JSON
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class CrmEvent(Base, BaseModel):
    __tablename__ = 'crm_events'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    event_type = Column(String(64), nullable=False)
    event_category = Column(String(32), nullable=False)
    event_source = Column(String(32), nullable=False, default='server')
    properties = Column(JSON)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    session_id = Column(String(128))
    ip_address = Column(INET)
    user_agent = Column(Text)
