"""
Device health model — single row per IoT device, upserted on each /sync heartbeat.

Schema reference: migrations/20260430_100000_046_create_device_health.sql
Phase 1 of scale-concept.md (IoT remote-management layer).
"""

from sqlalchemy import (
    Column, String, Boolean, BigInteger, Integer, Numeric, DateTime, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base


class DeviceHealth(Base):
    __tablename__ = 'iot_device_health'

    # Primary key is device_id (no surrogate id) — one row per device.
    device_id = Column(
        BigInteger,
        ForeignKey('iot_devices.id', ondelete='CASCADE'),
        primary_key=True,
    )

    last_seen_at = Column(DateTime(timezone=True), nullable=False)

    # NOTE: there is no `online` column on this table. Compute it at SELECT time:
    #     SELECT (last_seen_at > NOW() - INTERVAL '30 seconds') AS online ...
    # See migration 20260430_100000_046 header comment for rationale.

    # Hardware
    battery_level = Column(Integer)            # 0–100
    battery_charging = Column(Boolean)
    cpu_temp_c = Column(Numeric(5, 2))
    network_type = Column(String(16))          # wifi | cellular | ethernet | none
    network_strength = Column(Integer)         # 0–100 (RSSI normalized)
    ip_address = Column(String(64))
    storage_free_mb = Column(Integer)
    ram_free_mb = Column(Integer)
    os_version = Column(String(64))
    app_version = Column(String(32))

    # App
    current_route = Column(String(128))        # /data-entry, /login, etc.
    current_user_id = Column(BigInteger)       # FK user_locations.id (logged-in admin)
    current_org_id = Column(BigInteger)        # FK organizations.id
    current_location_id = Column(BigInteger)   # FK user_locations.id
    scale_connected = Column(Boolean)
    scale_mac_bt = Column(String(64))
    cache_summary = Column(JSONB)              # {materials_count, pending_records, ...}
    raw = Column(JSONB)                        # full last heartbeat for debugging
