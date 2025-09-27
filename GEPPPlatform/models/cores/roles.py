"""
System role models for organizational permissions
"""

from sqlalchemy import Column, String, Text, BigInteger, Table, ForeignKey
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel

# Association table for subscription permissions
subscription_permissions = Table(
    'subscription_permissions',
    Base.metadata,
    Column('subscription_id', ForeignKey('subscriptions.id'), primary_key=True),
    Column('permission_id', ForeignKey('system_permissions.id'), primary_key=True)
)


class SystemRole(Base, BaseModel):
    """
    System roles that define what system-level permissions an organization can have.
    These roles determine what parts of the GEPP platform the organization can access.
    """
    __tablename__ = 'system_roles'

    name = Column(String(100), nullable=False)
    description = Column(Text)
    permissions = Column(Text)  # JSON column storing system permissions

    def __repr__(self):
        return f"<SystemRole(id={self.id}, name='{self.name}')>"


class SystemPermission(Base, BaseModel):
    """System-level permissions that control feature access based on subscription"""
    __tablename__ = 'system_permissions'

    code = Column(String(100), unique=True, nullable=False)  # e.g., 'waste_transaction.create'
    name = Column(String(255))
    description = Column(Text)
    category = Column(String(100))  # e.g., 'waste_transaction', 'reporting', 'analytics'

    # Which plans have this permission
    subscriptions = relationship("Subscription", secondary=subscription_permissions, back_populates="permissions")

    def __repr__(self):
        return f"<SystemPermission(id={self.id}, code='{self.code}')>"