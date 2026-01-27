"""
Custom API models for organization-specific API access control
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, Integer, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class CustomApi(Base, BaseModel):
    """
    Stores available custom API endpoints that can be enabled per organization.
    Each API has a service_path (URL segment) and root_fn_name (Python function to execute).
    """
    __tablename__ = 'custom_apis'

    name = Column(String(255), nullable=False)
    description = Column(Text)
    service_path = Column(String(255), nullable=False, unique=True)
    root_fn_name = Column(String(255), nullable=False)

    # Relationships
    organization_apis = relationship("OrganizationCustomApi", back_populates="custom_api")


class OrganizationCustomApi(Base, BaseModel):
    """
    Junction table controlling which custom APIs are enabled for each organization.
    Includes quota management and expiration controls.
    """
    __tablename__ = 'organization_custom_apis'

    organization_id = Column(BigInteger, ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    custom_api_id = Column(BigInteger, ForeignKey('custom_apis.id', ondelete='CASCADE'), nullable=False)
    
    # Quota tracking
    api_call_quota = Column(Integer, default=1000)
    api_call_used = Column(Integer, default=0)
    process_quota = Column(Integer, default=10000)
    process_used = Column(Integer, default=0)
    
    # Access control
    enable = Column(Boolean, default=True)
    expired_date = Column(DateTime(timezone=True))

    # Relationships
    organization = relationship("Organization", back_populates="custom_apis")
    custom_api = relationship("CustomApi", back_populates="organization_apis")

    def is_valid(self) -> bool:
        """Check if this API access is currently valid"""
        from datetime import datetime, timezone
        
        if not self.enable:
            return False
        if self.deleted_date:
            return False
        if self.expired_date and self.expired_date < datetime.now(timezone.utc):
            return False
        return True

    def has_api_quota(self) -> bool:
        """Check if API call quota is available"""
        if self.api_call_quota is None:
            return True  # Unlimited
        return self.api_call_used < self.api_call_quota

    def has_process_quota(self, units: int = 1) -> bool:
        """Check if process quota is available for given units"""
        if self.process_quota is None:
            return True  # Unlimited
        return (self.process_used + units) <= self.process_quota

    def increment_api_call(self) -> None:
        """Increment API call counter"""
        self.api_call_used = (self.api_call_used or 0) + 1

    def increment_process_usage(self, units: int = 1) -> None:
        """Increment process usage counter"""
        self.process_used = (self.process_used or 0) + units
