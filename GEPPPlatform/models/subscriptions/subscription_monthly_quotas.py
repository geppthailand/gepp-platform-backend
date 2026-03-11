"""
Subscription Monthly Quotas model
Tracks AI audit and transaction creation usage per time period (monthly/yearly)
"""

from sqlalchemy import Column, String, BigInteger, Integer, ForeignKey
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel


class SubscriptionMonthlyQuota(Base, BaseModel):
    """Usage quotas per organization per time period"""
    __tablename__ = 'subscription_monthly_quotas'

    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    duration_type = Column(String(20), nullable=False, default='monthly')
    duration_scope = Column(String(10), nullable=False)
    ai_audit_limit = Column(Integer, nullable=False, default=10)
    ai_audit_usage = Column(Integer, nullable=False, default=0)
    create_transaction_limit = Column(Integer, nullable=False, default=100)
    create_transaction_usage = Column(Integer, nullable=False, default=0)

    organization = relationship("Organization", foreign_keys=[organization_id])

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'duration_type': self.duration_type,
            'duration_scope': self.duration_scope,
            'ai_audit_limit': self.ai_audit_limit,
            'ai_audit_usage': self.ai_audit_usage,
            'create_transaction_limit': self.create_transaction_limit,
            'create_transaction_usage': self.create_transaction_usage,
            'is_active': self.is_active,
            'created_date': self.created_date.isoformat() if self.created_date else None,
        }
