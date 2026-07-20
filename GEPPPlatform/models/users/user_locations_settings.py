"""
Per-user data-entry settings (user_locations_settings).

Holds the two "ตั้งค่าทั่วไป" General-Settings toggles PER USER (a user_locations row with
is_user=true), instead of per organization:
  - input_destination         ("กรอกปลายทาง")
  - show_all_location_options  ("แสดงตัวเลือกสถานที่ทั้งหมด")

At most one live row per user (see the partial unique index in migration 076). When a user
has no row, the app uses the system defaults (input_destination=False, show_all=True).

See migration 20260720_120000_076_create_user_locations_settings.sql.
"""

from sqlalchemy import Column, Boolean, BigInteger, DateTime, ForeignKey
from sqlalchemy.sql import func

from ..base import Base


class UserLocationSettings(Base):
    __tablename__ = 'user_locations_settings'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # The user (a user_locations row, is_user=true) these settings belong to.
    user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)
    # Scoping/reporting convenience; the user already implies one org.
    organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=True)

    input_destination = Column(Boolean, nullable=False, default=False)
    show_all_location_options = Column(Boolean, nullable=False, default=True)

    created_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_date = Column(DateTime(timezone=True))
