"""
Device command model — admin → device command queue.

Schema reference: migrations/20260430_100000_048_create_device_commands.sql
Phase 1 of scale-concept.md (IoT remote-management layer).
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..base import Base


class DeviceCommand(Base):
    __tablename__ = 'device_commands'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(
        BigInteger,
        ForeignKey('iot_devices.id', ondelete='CASCADE'),
        nullable=False,
    )
    command_type = Column(String(48), nullable=False)
    # force_login | force_logout | navigate | reset_to_home | reset_input
    # overwrite_cache | clear_storage | restart_app | ota_update | ping

    payload = Column(JSONB)                    # {user_id, route, key, value, ...}
    status = Column(String(16), nullable=False, default='pending')
    # pending | delivered | acked | succeeded | failed | expired

    issued_by = Column(BigInteger, nullable=False)   # admin user_locations.id
    issued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    delivered_at = Column(DateTime(timezone=True))
    acked_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    result = Column(JSONB)                     # error message or output

    # 5-minute TTL applied by Postgres default; surface the same default to ORM-side inserts.
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW() + INTERVAL '5 minutes'"),
    )
