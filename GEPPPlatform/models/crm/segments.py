"""CRM segments — versioned rule-based cohorts with materialized membership."""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime, Integer, Boolean, JSON

from ..base import Base, BaseModel


class CrmSegment(Base, BaseModel):
    __tablename__ = 'crm_segments'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    rules = Column(JSON, nullable=False)
    scope = Column(String(16), nullable=False)  # 'user' | 'organization'
    version = Column(Integer, nullable=False, default=1)
    parent_segment_id = Column(BigInteger, ForeignKey('crm_segments.id'))
    is_current = Column(Boolean, nullable=False, default=True)
    member_count = Column(Integer, nullable=False, default=0)
    last_evaluated_at = Column(DateTime(timezone=True))
    created_by = Column(BigInteger, ForeignKey('user_locations.id'))


class CrmSegmentMember(Base):
    __tablename__ = 'crm_segment_members'

    segment_id = Column(BigInteger, ForeignKey('crm_segments.id', ondelete='CASCADE'), primary_key=True)
    member_type = Column(String(16), primary_key=True)  # 'user' | 'organization'
    member_id = Column(BigInteger, primary_key=True)
    evaluated_at = Column(DateTime(timezone=True))
