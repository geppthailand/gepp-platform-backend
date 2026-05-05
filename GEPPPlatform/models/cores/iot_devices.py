"""
IoT devices model
"""

from sqlalchemy import Column, String, Boolean, BigInteger, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base, BaseModel


class IoTDevice(Base, BaseModel):
    __tablename__ = 'iot_devices'

    device_type = Column(String(64), nullable=False, default='scale')
    device_name = Column(String(255), nullable=False)
    mac_address_bluetooth = Column(String(64))
    mac_address_tablet = Column(String(64))
    password = Column(String(255))
    organization_id = Column(BigInteger)

    # Operational labels (string array) — e.g. ["pilot-group-a","firmware-v2"].
    # Independent of organization; filtered with @> operator in admin list.
    tags = Column(JSONB, nullable=False, default=list)

    # When TRUE, device is suppressed from alerts panel + proactive notifications.
    maintenance_mode = Column(Boolean, nullable=False, default=False)
    maintenance_reason = Column(Text)
    # Optional auto-clear; future cron will flip maintenance_mode=FALSE when
    # NOW() > maintenance_until.
    maintenance_until = Column(DateTime(timezone=True))

    # Currently-paired physical hardware (FK iot_hardwares.id). NULL when no
    # tablet is bound. See migration 051 + admin pair/unpair endpoints.
    hardware_id = Column(BigInteger)
