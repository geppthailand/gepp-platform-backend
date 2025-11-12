"""
Transaction Audits Model
Stores audit history for transactions (both AI and manual audits)
"""

from sqlalchemy import Column, String, BigInteger, Boolean, ForeignKey, Integer, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class TransactionAudit(Base, BaseModel):
    """
    Transaction audit history
    Stores results from AI and manual audits
    """
    __tablename__ = 'transaction_audits'

    # Core fields
    transaction_id = Column(BigInteger, ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False, index=True)
    audit_notes = Column(JSONB, nullable=False, default={})
    by_human = Column(Boolean, nullable=False, default=False)

    # Audit metadata
    auditor_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False, index=True)
    audit_type = Column(String(50), nullable=True)  # 'ai_sync', 'ai_async', 'manual', etc.
    created_by_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)  # User who created this audit

    # AI processing details
    processing_time_ms = Column(Integer, nullable=True)
    token_usage = Column(JSONB, nullable=True)
    model_version = Column(String(100), nullable=True)

    # Override BaseModel's DateTime columns with BIGINT (milliseconds since epoch)
    # This matches the database schema in migration 054
    created_date = Column(BigInteger, nullable=True)
    updated_date = Column(BigInteger, nullable=True)
    deleted_date = Column(BigInteger, nullable=True)

    # Relationships
    transaction = relationship("Transaction", foreign_keys=[transaction_id], back_populates="audits")
    organization = relationship("Organization", foreign_keys=[organization_id])
    auditor = relationship("UserLocation", foreign_keys=[auditor_id])

    # Indexes
    __table_args__ = (
        Index('idx_transaction_audits_transaction_id', 'transaction_id'),
        Index('idx_transaction_audits_by_human', 'by_human'),
        Index('idx_transaction_audits_organization_id', 'organization_id'),
        Index('idx_transaction_audits_created_date', 'created_date'),
        Index('idx_transaction_audits_audit_type', 'audit_type'),
        Index('idx_transaction_audits_audit_notes', 'audit_notes', postgresql_using='gin'),
    )

    def __repr__(self):
        audit_source = "Manual" if self.by_human else "AI"
        return f"<TransactionAudit(id={self.id}, transaction_id={self.transaction_id}, by_human={self.by_human}, type={audit_source})>"

    def to_dict(self):
        """Convert audit to dictionary for API responses"""
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'audit_notes': self.audit_notes,
            'by_human': self.by_human,
            'auditor_id': self.auditor_id,
            'organization_id': self.organization_id,
            'audit_type': self.audit_type,
            'processing_time_ms': self.processing_time_ms,
            'token_usage': self.token_usage,
            'model_version': self.model_version,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'updated_date': self.updated_date.isoformat() if self.updated_date else None,
            'created_by_id': self.created_by_id
        }

    def get_status(self):
        """Get audit status from audit_notes"""
        return self.audit_notes.get('s', 'unknown')

    def get_violations(self):
        """Get violations array from audit_notes"""
        return self.audit_notes.get('v', [])

    def get_violation_count(self):
        """Count total violations"""
        return len(self.get_violations())

    def has_violations(self):
        """Check if audit has any violations"""
        return self.get_violation_count() > 0
