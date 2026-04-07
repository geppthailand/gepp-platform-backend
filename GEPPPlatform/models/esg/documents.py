"""
ESG Document Model — Generic document store for all ESG categories
"""

import enum
from sqlalchemy import Column, BigInteger, Integer, String, Text, Numeric, Boolean, DateTime, TIMESTAMP, Date, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgCategory(enum.Enum):
    ENVIRONMENT = 'environment'
    SOCIAL = 'social'
    GOVERNANCE = 'governance'


class EsgClassificationStatus(enum.Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'


class EsgDocument(Base, BaseModel):
    __tablename__ = 'esg_documents'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # Document Info
    file_name = Column(String(500), nullable=False)
    file_url = Column(Text, nullable=False)
    file_type = Column(String(50))
    file_size_bytes = Column(BigInteger)

    # ESG Classification
    esg_category = Column(String(20))
    esg_subcategory = Column(String(100))
    document_type = Column(String(100))
    document_date = Column(Date)
    reporting_year = Column(Integer)

    # Source
    source = Column(String(20), nullable=False, default='upload')
    uploaded_by_id = Column(BigInteger)
    line_message_id = Column(String(255))
    line_user_id = Column(String(255))

    # AI Classification
    ai_classification_status = Column(String(30), default='pending')
    ai_classification_result = Column(JSONB)
    ai_confidence = Column(Numeric(5, 4))
    ai_classified_at = Column(DateTime(timezone=True))

    # Metadata
    vendor_name = Column(String(255))
    summary = Column(Text)
    tags = Column(JSONB, default=[])
    notes = Column(Text)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'file_name': self.file_name,
            'file_url': self.file_url,
            'file_type': self.file_type,
            'file_size_bytes': self.file_size_bytes,
            'esg_category': self.esg_category,
            'esg_subcategory': self.esg_subcategory,
            'document_type': self.document_type,
            'document_date': str(self.document_date) if self.document_date else None,
            'reporting_year': self.reporting_year,
            'source': self.source,
            'uploaded_by_id': self.uploaded_by_id,
            'line_message_id': self.line_message_id,
            'line_user_id': self.line_user_id,
            'ai_classification_status': self.ai_classification_status,
            'ai_classification_result': self.ai_classification_result,
            'ai_confidence': float(self.ai_confidence) if self.ai_confidence else None,
            'ai_classified_at': str(self.ai_classified_at) if self.ai_classified_at else None,
            'vendor_name': self.vendor_name,
            'summary': self.summary,
            'tags': self.tags or [],
            'notes': self.notes,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
