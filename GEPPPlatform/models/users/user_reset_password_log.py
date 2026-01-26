"""
User Reset Password Log Model
Stores password reset request logs with JWT tokens and device information
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class UserResetPasswordLog(Base, BaseModel):
    """
    Tracks password reset requests with JWT tokens and device information
    """
    __tablename__ = 'user_reset_password_log'

    # Foreign key to user
    user_id = Column(Integer, ForeignKey('user_locations.id', ondelete='CASCADE'), nullable=False)

    # Request information
    user_agent = Column(Text)  # User browser or client user agent string
    jwt = Column(Text, nullable=False)  # JWT token used for password reset
    device_type = Column(Text)  # Device information of the user
    ip_address = Column(Text)  # IP address of the user making the request
    user_identification = Column(Text, nullable=False)  # User email address
    expires = Column(DateTime(timezone=True), nullable=False)  # Token expiration timestamp

    # Relationships
    user = relationship("UserLocation", foreign_keys=[user_id])

    def __repr__(self):
        return f"<UserResetPasswordLog(id={self.id}, user_id={self.user_id}, expires={self.expires})>"
