"""
Custom API Callings - Records each custom API call with affected transactions
"""

from sqlalchemy import Column, String, Text, ForeignKey, BigInteger, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class CustomApiCalling(Base, BaseModel):
    """
    Records each custom API call, including which transactions were
    created, updated or deleted as a result.
    """
    __tablename__ = 'custom_api_callings'

    status = Column(String(50), nullable=False, default='pending')  # pending, failed, success
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    api_path = Column(String(255), nullable=True)  # The organization api_path segment
    custom_api_id = Column(BigInteger, ForeignKey('custom_apis.id'), nullable=True)
    full_path = Column(Text, nullable=True)  # Full API path e.g. /api/userapi/.../call
    api_method = Column(String(10), nullable=True)  # GET, POST, PUT, DELETE, ...
    caller_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=True)  # JWT user_location id

    # Affected transactions (JSONB arrays of transaction IDs)
    created_transactions = Column(JSONB, nullable=False, default=[])
    updated_transactions = Column(JSONB, nullable=False, default=[])
    deleted_transactions = Column(JSONB, nullable=False, default=[])

    # Relationships
    organization = relationship("Organization", foreign_keys=[organization_id])
    custom_api = relationship("CustomApi", foreign_keys=[custom_api_id])
    caller = relationship("UserLocation", foreign_keys=[caller_id])
