"""
IoT devices model
"""

from sqlalchemy import Column, String, Boolean
from ..base import Base, BaseModel


class IoTDevice(Base, BaseModel):
    __tablename__ = 'iot_devices'

    device_type = Column(String(64), nullable=False, default='scale')
    device_name = Column(String(255), nullable=False)
    mac_address_bluetooth = Column(String(64))
    mac_address_tablet = Column(String(64))
    password = Column(String(255))


