"""
ESG LINE Message Model — LINE message tracking for document submissions
"""

from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func

from ..base import Base, BaseModel


class EsgLineMessage(Base, BaseModel):
    __tablename__ = 'esg_line_messages'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)

    # LINE Message Info
    line_message_id = Column(String(255), nullable=False)
    line_user_id = Column(String(255), nullable=False)
    line_reply_token = Column(String(255))
    message_type = Column(String(50), nullable=False)  # image, text, file

    # Processing
    processing_status = Column(String(30), nullable=False, default='received')
    document_id = Column(BigInteger, ForeignKey('esg_documents.id', ondelete='SET NULL'))
    error_message = Column(Text)

    # Reply
    reply_sent = Column(Boolean, default=False)
    reply_message = Column(Text)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'line_message_id': self.line_message_id,
            'line_user_id': self.line_user_id,
            'message_type': self.message_type,
            'processing_status': self.processing_status,
            'document_id': self.document_id,
            'error_message': self.error_message,
            'reply_sent': self.reply_sent,
            'reply_message': self.reply_message,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
        }
