"""
ESG Supplier Chaser Model - Automated reminders for supplier data collection
"""

from sqlalchemy import Column, BigInteger, String, Integer, Boolean, Date, DateTime, ForeignKey
from GEPPPlatform.models.base import Base, BaseModel


class EsgSupplierChaser(Base, BaseModel):
    """Scheduled chasers/reminders sent to suppliers"""
    __tablename__ = 'esg_supplier_chasers'

    supplier_id = Column(BigInteger, ForeignKey('esg_suppliers.id'), nullable=False, index=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    chaser_type = Column(String(20), nullable=False, default='email')
    scheduled_date = Column(Date, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default='scheduled')
    reminder_count = Column(Integer, nullable=False, default=0)
    linked_submission_id = Column(BigInteger, ForeignKey('esg_supplier_submissions.id'), nullable=True)
    message_template = Column(String(50), nullable=True)
    response_received = Column(Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'supplier_id': self.supplier_id,
            'organization_id': self.organization_id,
            'chaser_type': self.chaser_type,
            'scheduled_date': str(self.scheduled_date) if self.scheduled_date else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'status': self.status,
            'reminder_count': self.reminder_count,
            'linked_submission_id': self.linked_submission_id,
            'message_template': self.message_template,
            'response_received': self.response_received,
            'is_active': self.is_active,
            'created_date': str(self.created_date) if self.created_date else None,
            'updated_date': str(self.updated_date) if self.updated_date else None,
        }
