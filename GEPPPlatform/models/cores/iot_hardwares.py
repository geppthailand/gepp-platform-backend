"""IoT hardware registry — see migration 051 header for the rationale."""

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
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

    # Physical-unit lifecycle, independent of pairing. See migration 087.
    lifecycle_status = Column(String(24), nullable=False, default='active')
    status_note = Column(Text)
    status_changed_at = Column(DateTime(timezone=True))
    status_changed_by = Column(BigInteger)

    # Latest telemetry straight off /api/iot-hardwares/checkin — present
    # even for tablets that have never been paired (iot_device_health is
    # keyed on device_id and so can't cover them).
    last_battery_level = Column(Integer)
    last_battery_charging = Column(Boolean)
    last_network_type = Column(String(16))
    last_network_strength = Column(Integer)
    last_storage_free_mb = Column(Integer)
    last_telemetry_at = Column(DateTime(timezone=True))
    checkin_count = Column(BigInteger, nullable=False, default=0)
    first_checkin_at = Column(DateTime(timezone=True))

    is_active = Column(Boolean, nullable=False, default=True)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_date = Column(DateTime(timezone=True))


class IoTHardwareHistory(Base):
    """Append-only timeline per physical tablet — see migration 087.

    Carries both system events (pair / unpair / status_change / delete /
    restore) and ops-entered notes + issues, so the admin drawer can render
    "what happened to this unit?" from a single query. Only ``issue`` rows
    are resolvable; everything else is a fact, not a ticket.
    """

    __tablename__ = 'iot_hardware_history'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    hardware_id = Column(
        BigInteger, ForeignKey('iot_hardwares.id', ondelete='CASCADE'), nullable=False
    )
    event_type = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False, default='info')
    title = Column(String(200), nullable=False)
    detail = Column(Text)
    payload = Column(JSONB)
    resolved_date = Column(DateTime(timezone=True))
    resolved_by = Column(BigInteger)
    created_by = Column(BigInteger)
    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IoTHardwareBatteryHistory(Base):
    """15-min battery / network buckets per physical tablet.

    Upserted directly by the public checkin handler rather than by a
    snapshot worker: checkin already fires every ~5 s and is the only path
    that sees an unpaired tablet.
    """

    __tablename__ = 'iot_hardware_battery_history'

    hardware_id = Column(
        BigInteger,
        ForeignKey('iot_hardwares.id', ondelete='CASCADE'),
        primary_key=True,
    )
    bucket_start = Column(DateTime(timezone=True), primary_key=True)
    battery_level = Column(Integer)
    battery_min = Column(Integer)
    battery_max = Column(Integer)
    battery_charging = Column(Boolean)
    network_type = Column(String(16))
    network_strength = Column(Integer)
    samples = Column(Integer, nullable=False, default=1)
    last_checkin_at = Column(DateTime(timezone=True))
