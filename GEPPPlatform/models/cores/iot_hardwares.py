"""IoT hardware registry — see migration 051 header for the rationale."""

from sqlalchemy import (
    Column,
    String,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.sql import func
from ..base import Base


class IoTHardware(Base):
    __tablename__ = 'iot_hardwares'

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    mac_address = Column(String(64), unique=True)
    serial_number = Column(String(128))
    device_code = Column(String(128))
    device_model = Column(String(128))
    os_version = Column(String(64))
    app_version = Column(String(32))

    last_checkin_at = Column(DateTime(timezone=True))
    last_ip_address = Column(String(64))

    paired_iot_device_id = Column(
        BigInteger, ForeignKey('iot_devices.id', ondelete='SET NULL')
    )
    paired_at = Column(DateTime(timezone=True))
    paired_by = Column(BigInteger)  # admin user_locations.id

    is_active = Column(Boolean, nullable=False, default=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_date = Column(DateTime(timezone=True))
