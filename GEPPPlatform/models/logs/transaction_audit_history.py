"""
Transaction Audit History Model
Stores batch audit information for tracking AI audit history
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ARRAY, JSON, Boolean
from sqlalchemy.sql import func
from datetime import datetime, timezone

from ..base import Base


class TransactionAuditHistory(Base):
    """
    Model for tracking transaction audit history batches
    Each record represents one AI audit batch execution
    """
    __tablename__ = 'transaction_audit_history'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Organization that triggered this audit batch
    organization_id = Column(Integer, nullable=False, index=True)

    # User who triggered this audit batch
    triggered_by_user_id = Column(Integer, nullable=True)

    # List of transaction IDs included in this audit batch
    transactions = Column(ARRAY(Integer), nullable=False, default=[])

    # Full audit response/info from LLM for this batch
    audit_info = Column(JSON, nullable=True)

    # Summary statistics for this batch
    total_transactions = Column(Integer, default=0)
    processed_transactions = Column(Integer, default=0)
    approved_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)

    # Batch status
    status = Column(String(50), default='completed')  # completed, failed, partial

    # Error message if batch failed
    error_message = Column(Text, nullable=True)

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Soft delete
    deleted_date = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<TransactionAuditHistory(id={self.id}, organization_id={self.organization_id}, total_transactions={self.total_transactions}, status={self.status})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'triggered_by_user_id': self.triggered_by_user_id,
            'transactions': self.transactions or [],
            'audit_info': self.audit_info,
            'total_transactions': self.total_transactions,
            'processed_transactions': self.processed_transactions,
            'approved_count': self.approved_count,
            'rejected_count': self.rejected_count,
            'status': self.status,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_date': self.created_date.isoformat() if self.created_date else None
        }
