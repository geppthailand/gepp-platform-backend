"""
Shared User Location model — cross-organization location data sharing.

Company A shares one of its locations (source_user_location_id) to Company B
(target_organization_id, resolved from target_email's owned org). Company B
surfaces that location's data as READ-ONLY via a virtual node in its
organization_setup.root_nodes, bounded by [start_date, end_date].

See migration 20260701_120000_070_create_shared_user_locations.sql.
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from .base import Base, BaseModel


class SharedUserLocation(Base, BaseModel):
    __tablename__ = 'shared_user_locations'

    # BaseModel provides: id, is_active (the on/off switch), created_date, updated_date, deleted_date.

    # Sharer (Org A) and the specific location being shared.
    source_organization_id = Column(BigInteger, ForeignKey('organizations.id'), nullable=False)
    source_user_location_id = Column(BigInteger, ForeignKey('user_locations.id'), nullable=False)

    # Recipient org (Org B), resolved from target_email's owned org; NULL until resolved.
    target_organization_id = Column(BigInteger, ForeignKey('organizations.id'))

    name = Column(String(255))
    description = Column(Text)
    target_email = Column(String(255), nullable=False)

    # Internal identifier (secrets.token_urlsafe(16)); NOT a click-to-accept token.
    share_code = Column(String(64), nullable=False, unique=True)

    # Share-level expiry (distinct from the data window below).
    expired_date = Column(DateTime(timezone=True))

    # SILENT compute/query flag — single source of truth for "may this share's data be
    # computed/surfaced". True only if target_email resolves to an org owner AND not rejected.
    is_valid = Column(Boolean, nullable=False, default=False)

    # Recipient rejected the share (removed the node). Also forces is_valid=false.
    is_rejected = Column(Boolean, nullable=False, default=False)

    # Placement in the TARGET org's chart: real user_location id this shared node hangs under
    # (set when the recipient drags it in). NULL = not yet placed. Shared nodes are never stored
    # in organization_setup.root_nodes — placement lives here, decoupled from the tree-save path.
    placed_parent_node_id = Column(BigInteger, ForeignKey('user_locations.id'))

    # Data window: only source transactions within [start_date, end_date] are shared.
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))

    # Relationships
    source_organization = relationship("Organization", foreign_keys=[source_organization_id])
    target_organization = relationship("Organization", foreign_keys=[target_organization_id])
    source_user_location = relationship("UserLocation", foreign_keys=[source_user_location_id])

    def effective(self) -> bool:
        """Whether this share may actually surface data right now."""
        from datetime import datetime, timezone
        if not (self.is_active and self.is_valid and not self.is_rejected and self.deleted_date is None):
            return False
        if self.expired_date is not None:
            now = datetime.now(timezone.utc)
            exp = self.expired_date
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now >= exp:
                return False
        return True
