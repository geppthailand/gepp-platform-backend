"""
IoT scales model
"""

from sqlalchemy import Column, String, BigInteger, DateTime, Text
from sqlalchemy.sql import func
from ..base import Base, BaseModel


class IoTScale(Base, BaseModel):
    __tablename__ = 'iot_scales'

    scale_name = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    owner_user_location_id = Column(BigInteger, nullable=False)
    location_point_id = Column(BigInteger, nullable=False)
    added_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_date = Column(DateTime(timezone=True))
    mac_tablet = Column(String(17))
    mac_scale = Column(String(17))
    status = Column(String(50), nullable=False, default='active')
    scale_type = Column(String(100), nullable=False, default='digital')
    calibration_data = Column(Text)
    notes = Column(Text)
