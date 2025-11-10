"""
Association model linking user_locations and materials
"""

from sqlalchemy import Column, ForeignKey, BigInteger
from sqlalchemy.orm import relationship

from ..base import Base, BaseModel


class UserLocationMaterial(Base, BaseModel):
    __tablename__ = 'user_location_materials'

    location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    materials_id = Column(BigInteger, ForeignKey('materials.id'), nullable=False)

    # Relationships
    location = relationship("UserLocation")
    material = relationship("Material")


