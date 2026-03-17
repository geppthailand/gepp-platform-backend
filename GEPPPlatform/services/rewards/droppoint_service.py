"""
Droppoint Service - Manage physical collection/redemption points
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.redemptions import Droppoint
from ...exceptions import NotFoundException, BadRequestException


class DroppointService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: Droppoint) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "hash": item.hash,
            "tag_id": item.tag_id,
            "tenant_id": item.tenant_id,
            "user_location_id": item.user_location_id,
            "type": item.type,
            "is_active": item.is_active,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }

    def list(self, organization_id: int, type_filter: str = None) -> list[dict]:
        """Return all active droppoints for an organization."""
        query = (
            self.db.query(Droppoint)
            .filter(
                Droppoint.organization_id == organization_id,
                Droppoint.deleted_date.is_(None),
            )
        )

        if type_filter:
            query = query.filter(Droppoint.type == type_filter)

        items = query.order_by(Droppoint.id.desc()).all()
        return [self._to_dict(i) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        """Create a new droppoint."""
        if not data.get("name"):
            raise BadRequestException("Name is required")

        item = Droppoint(
            organization_id=organization_id,
            name=data["name"],
            hash=uuid.uuid4().hex,
            tag_id=data.get("tag_id"),
            tenant_id=data.get("tenant_id"),
            user_location_id=data.get("user_location_id"),
            type=data.get("type", "reward_droppoint"),
        )
        self.db.add(item)
        self.db.flush()

        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        """Update an existing droppoint."""
        item = (
            self.db.query(Droppoint)
            .filter(Droppoint.id == id, Droppoint.deleted_date.is_(None))
            .first()
        )
        if not item:
            raise NotFoundException("Droppoint not found")

        for field in ("name", "tag_id", "tenant_id", "user_location_id"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a droppoint."""
        item = (
            self.db.query(Droppoint)
            .filter(Droppoint.id == id, Droppoint.deleted_date.is_(None))
            .first()
        )
        if not item:
            raise NotFoundException("Droppoint not found")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
