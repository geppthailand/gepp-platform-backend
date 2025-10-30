"""
Integration tokens model for tracking API integration authentication
"""

from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey
from sqlalchemy.orm import relationship
from ..base import Base, BaseModel


class IntegrationToken(Base, BaseModel):
    """
    Stores integration tokens for API access tracking
    Links transactions to the integration token that created them
    """
    __tablename__ = 'integration_tokens'

    # Foreign key to user
    user_id = Column(Integer, ForeignKey('user_locations.id', ondelete='CASCADE'), nullable=False)

    # Token information
    jwt = Column(Text, nullable=False)  # The JWT token string
    description = Column(Text)  # Optional description
    valid = Column(Boolean, nullable=False, default=True)  # Token validity status

    # Relationships
    user = relationship("UserLocation", foreign_keys=[user_id])

    def __repr__(self):
        return f"<IntegrationToken(id={self.id}, user_id={self.user_id}, valid={self.valid})>"
