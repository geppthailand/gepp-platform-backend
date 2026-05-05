"""
Activity Type Service — Activity types for activity-based campaigns
(e.g. BYO Bag, Refuse Plastic, Clean Beach).

Phase 2 (rewards v3 redesign).
"""

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...models.rewards.management import RewardActivityType
from ...exceptions import APIException, NotFoundException, BadRequestException


class ActivityTypeService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardActivityType) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,  # null for system defaults
            "name": item.name,
            "name_local": item.name_local,
            "emoji": item.emoji,
            "color": item.color,
            "description": item.description,
            "is_default": item.is_default,
            "is_active": item.is_active,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }

    def list(self, organization_id: int) -> list[dict]:
        """List all activity types visible to this org:
           system defaults (org_id NULL) + this org's custom types.
           Excludes soft-deleted rows."""
        items = (
            self.db.query(RewardActivityType)
            .filter(
                or_(
                    RewardActivityType.organization_id == organization_id,
                    RewardActivityType.organization_id.is_(None),
                ),
                RewardActivityType.deleted_date.is_(None),
                RewardActivityType.is_active.is_(True),
            )
            .order_by(
                RewardActivityType.is_default.desc(),
                RewardActivityType.id.asc(),
            )
            .all()
        )
        return [self._to_dict(i) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        if not data.get("name"):
            raise BadRequestException("Name is required")

        item = RewardActivityType(
            organization_id=organization_id,  # always belongs to the calling org
            name=data["name"],
            name_local=data.get("name_local"),
            emoji=data.get("emoji"),
            color=data.get("color"),
            description=data.get("description"),
            is_default=False,  # admin-created custom types are never defaults
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item)

    def update(self, id: int, organization_id: int, data: dict) -> dict:
        item = (
            self.db.query(RewardActivityType)
            .filter(
                RewardActivityType.id == id,
                RewardActivityType.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Activity type not found")
        # System defaults (org_id NULL) are read-only across orgs
        if item.organization_id is None:
            raise BadRequestException("System default activity types cannot be modified")
        if item.organization_id != organization_id:
            raise BadRequestException("Cannot modify activity type from another organization")

        for field in ("name", "name_local", "emoji", "color", "description", "is_active"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int, organization_id: int) -> dict:
        item = (
            self.db.query(RewardActivityType)
            .filter(
                RewardActivityType.id == id,
                RewardActivityType.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Activity type not found")
        if item.organization_id is None:
            raise BadRequestException("System default activity types cannot be deleted")
        if item.organization_id != organization_id:
            raise BadRequestException("Cannot delete activity type from another organization")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}
