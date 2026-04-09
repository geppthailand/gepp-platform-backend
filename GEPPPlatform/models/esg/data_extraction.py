"""
ESG Organization Data Extraction Model
"""

from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgOrganizationDataExtraction(Base, BaseModel):
    __tablename__ = 'esg_organization_data_extraction'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # Source
    channel = Column(String(20), nullable=False)
    type = Column(String(10), nullable=False)
    file_id = Column(BigInteger, ForeignKey('files.id', ondelete='SET NULL'))

    # Raw content
    raw_content = Column(Text)

    # Source tracking
    source_group_id = Column(String(255))
    source_group_name = Column(String(255))
    source_user_id = Column(String(255))
    source_message_id = Column(String(255))

    # LLM Extraction Results
    extractions = Column(JSONB, default=dict)

    # Datapoint Matches (legacy — kept for backward compat)
    datapoint_matches = Column(JSONB, default=list)

    # Reference tracking (legacy — kept for backward compat)
    refs = Column(JSONB, default=dict)

    # New compact structured extraction (ver=2)
    # Schema: {rows:[{lbl,cat,sub,attrs:[{dp,v,u,c,t,cur,tags}],atm}],tots,dm,add,ver}
    structured_data = Column(JSONB, default=dict)

    # Processing
    processing_status = Column(String(30), default='pending')
    error_message = Column(Text)
    processed_at = Column(DateTime(timezone=True))

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'channel': self.channel,
            'type': self.type,
            'file_id': self.file_id,
            'raw_content': self.raw_content[:200] if self.raw_content else None,
            'source_group_id': self.source_group_id,
            'source_group_name': self.source_group_name,
            'source_user_id': self.source_user_id,
            'source_message_id': self.source_message_id,
            'extractions': self.extractions or {},
            'datapoint_matches': self.datapoint_matches or [],
            'refs': self.refs or {},
            'structured_data': self.structured_data or {},
            'processing_status': self.processing_status,
            'error_message': self.error_message,
            'processed_at': str(self.processed_at) if self.processed_at else None,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
