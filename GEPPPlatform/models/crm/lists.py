"""CRM email lists (CC/BCC) + unsubscribe registry."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, JSON

from ..base import Base, BaseModel


class CrmEmailList(Base, BaseModel):
    __tablename__ = 'crm_email_lists'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    emails = Column(JSON, nullable=False, default=list)
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))


class CrmUnsubscribe(Base):
    __tablename__ = 'crm_unsubscribes'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    reason = Column(String(255))
    unsubscribed_at = Column(DateTime(timezone=True))
    source = Column(String(32), nullable=False, default='manual')
