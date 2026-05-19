"""
Device event model — append-only audit trail for IoT devices.

Schema reference: migrations/20260430_100000_047_create_device_events.sql
Phase 1 of scale-concept.md (IoT remote-management layer).
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..base import Base


class DeviceEvent(Base):
    __tablename__ = 'iot_device_events'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(
        BigInteger,
        ForeignKey('iot_devices.id', ondelete='CASCADE'),
        nullable=False,
    )
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    event_type = Column(String(48), nullable=False)
    # nav | click | input | error | login | logout | command_executed
    route = Column(String(128))
    payload = Column(JSONB)                    # {target: 'input1', value: 'xyz'} etc.
    user_id = Column(BigInteger)
    session_id = Column(String(64))            # groups events between login/logout
