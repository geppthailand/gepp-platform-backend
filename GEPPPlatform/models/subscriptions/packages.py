"""
Subscription packages and permissions models
"""

from sqlalchemy import Column, String, Text, ForeignKey, Integer, BigInteger
from sqlalchemy.types import DECIMAL
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel

class SubscriptionPackage(Base, BaseModel):
    __tablename__ = 'subscription_packages'
    
    # Organization linkage (nullable for global packages)
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    
    name = Column(String(255))
    description = Column(Text)
    price = Column(DECIMAL(10, 2))
    duration_days = Column(Integer)
    
    # Global or organization-specific
    is_global = Column(Integer, default=1)  # 1 for global, 0 for org-specific
    
    # Relationships
    organization = relationship("Organization")

class SubscriptionPermission(Base, BaseModel):
    __tablename__ = 'subscription_package_permissions'
    
    subscription_package_id = Column(ForeignKey('subscription_packages.id'))
    permission_id = Column(ForeignKey('permissions.id'))
    
    subscription_package = relationship("SubscriptionPackage")
    permission = relationship("Permission")