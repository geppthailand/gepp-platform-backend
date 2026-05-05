"""
Device-health-history model — aggregated 5-min snapshots used for trend
charts (24h fleet online%, per-device 24h sparklines).

Schema reference: migrations/20260503_100000_050_create_device_health_history.sql
"""

from sqlalchemy import (
    Column,
    String,
    Boolean,
    BigInteger,
    Integer,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
)
from ..base import Base


class DeviceHealthHistory(Base):
    __tablename__ = 'device_health_history'

    device_id = Column(
        BigInteger,
        ForeignKey('iot_devices.id', ondelete='CASCADE'),
        nullable=False,
    )
    bucket_start = Column(DateTime(timezone=True), nullable=False)

    online = Column(Boolean, nullable=False)
    battery_level = Column(Integer)
    battery_charging = Column(Boolean)
    network_type = Column(String(16))
    network_strength = Column(Integer)
    last_seen_at = Column(DateTime(timezone=True))

    __table_args__ = (
        PrimaryKeyConstraint('device_id', 'bucket_start'),
    )
