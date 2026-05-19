"""CRM event log — lean, indexed for org/time aggregation.

NOTE: this model intentionally does NOT inherit `BaseModel`. The
`crm_events` table (migration 20260420_*_029_create_crm_events.sql) is an
APPEND-ONLY log — it has only `id` + `created_date`, no `is_active`,
`deleted_date`, or `updated_date`. Inheriting `BaseModel` would inject
those four columns into every INSERT and crash with
    (psycopg2.errors.UndefinedColumn) column "deleted_date" of relation
    "crm_events" does not exist
breaking every code path that emits a CRM event (user login, IoT
heartbeat, transaction, traceability, …). The model below mirrors exactly
the schema declared in the migration.
"""

from sqlalchemy import (
    Column,
    String,
    Text,
    ForeignKey,
    BigInteger,
    DateTime,
    JSON,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.sql import func

from ..base import Base


class CrmEvent(Base):
    __tablename__ = 'crm_events'

    # Append-only log — only id + created_date for housekeeping.
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_date = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Domain columns (match migration 029).
    organization_id = Column(BigInteger, ForeignKey('organizations.id'))
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'))
    event_type = Column(String(64), nullable=False)
    event_category = Column(String(32), nullable=False)
    event_source = Column(String(32), nullable=False, default='server')
    properties = Column(JSON)
    occurred_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    session_id = Column(String(128))
    ip_address = Column(INET)
    user_agent = Column(Text)
