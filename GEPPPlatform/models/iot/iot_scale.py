"""
IoT Scale model for digital scale devices
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class IoTScale(Base, BaseModel):
    """
    IoT Scale model for digital scale devices
    Represents a physical digital scale that can authenticate and send weight data
    """
    __tablename__ = 'iot_scales'
    
    # Basic identification
    scale_name = Column(String(255), nullable=False, unique=True, index=True)
    password = Column(String(255), nullable=False)  # hashed password for authentication
    
    # Ownership & Location
    owner_user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False, index=True)
    location_point_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False, index=True)
    
    # Dates
    added_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=True)  # Scale expiration date
    
    # Technical details
    mac_tablet = Column(String(17), nullable=True)  # MAC address of controlling tablet
    mac_scale = Column(String(17), nullable=True)   # MAC address of the scale device
    
    # Status & Configuration
    status = Column(String(50), nullable=False, default='active', index=True)  # active, maintenance, offline
    scale_type = Column(String(100), nullable=False, default='digital')
    
    # Additional configuration
    calibration_data = Column(Text, nullable=True)  # JSON string for calibration settings
    notes = Column(Text, nullable=True)             # Additional notes about the scale
    
    # Relationships
    owner = relationship(
        "UserLocation", 
        foreign_keys=[owner_user_location_id],
        back_populates="owned_iot_scales"
    )
    location = relationship(
        "UserLocation", 
        foreign_keys=[location_point_id],
        back_populates="iot_scales_at_location"
    )
    
    def __repr__(self):
        return f"<IoTScale(id={self.id}, scale_name='{self.scale_name}', status='{self.status}')>"
    
    def is_active(self) -> bool:
        """Check if the scale is currently active"""
        from datetime import datetime, timezone
        if self.status != 'active':
            return False
        if self.end_date and datetime.now(timezone.utc) > self.end_date:
            return False
        return True
    
    def can_authenticate(self) -> bool:
        """Check if the scale can authenticate (login)"""
        return self.is_active() and bool(self.password)
    
    def get_owner_info(self) -> dict:
        """Get basic owner information"""
        if not self.owner:
            return {}
        return {
            'id': self.owner.id,
            'display_name': self.owner.display_name,
            'email': self.owner.email,
            'organization_id': self.owner.organization_id
        }
    
    def get_location_info(self) -> dict:
        """Get basic location information"""
        if not self.location:
            return {}
        return {
            'id': self.location.id,
            'display_name': self.location.display_name,
            'name_th': self.location.name_th,
            'name_en': self.location.name_en,
            'coordinate': self.location.coordinate,
            'address': self.location.address,
            'postal_code': self.location.postal_code
        }
