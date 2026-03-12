"""
AI Audit Document Types Model
Defines document type classifications for AI audit evidence analysis
"""

from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class AiAuditDocumentType(Base, BaseModel):
    """
    Document type definitions for AI audit evidence classification.
    Each type defines what data fields can be extracted from that document type.
    """
    __tablename__ = 'ai_audit_document_types'

    name_en = Column(String(255), nullable=False)
    name_th = Column(String(255), nullable=False)
    description_en = Column(Text, nullable=True)
    description_th = Column(Text, nullable=True)
    extract_list = Column(JSONB, nullable=False, default=[])

    def __repr__(self):
        return f"<AiAuditDocumentType(id={self.id}, name_en='{self.name_en}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'name_en': self.name_en,
            'name_th': self.name_th,
            'description_en': self.description_en,
            'description_th': self.description_th,
            'extract_list': self.extract_list,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
        }
