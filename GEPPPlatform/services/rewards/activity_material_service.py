"""
Activity Material Service - Materials or activities that can earn points
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardActivityMaterial
from ...exceptions import APIException, NotFoundException, BadRequestException


class ActivityMaterialService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardActivityMaterial) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "type": item.type,
            "material_id": item.material_id,
            "image_id": item.image_id,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }

    def list(self, organization_id: int) -> list[dict]:
        """Return all active reward activity materials for an organization."""
        items = (
            self.db.query(RewardActivityMaterial)
            .filter(
                RewardActivityMaterial.organization_id == organization_id,
                RewardActivityMaterial.deleted_date.is_(None),
            )
            .order_by(RewardActivityMaterial.id.desc())
            .all()
        )
        return [self._to_dict(i) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        """Create a new activity material."""
        if not data.get("name"):
            raise BadRequestException("Name is required")
        if data.get("type") not in ("material", "activity"):
            raise BadRequestException("Type must be 'material' or 'activity'")

        item = RewardActivityMaterial(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            type=data["type"],
            material_id=data.get("material_id"),
            image_id=data.get("image_id"),
        )
        self.db.add(item)
        self.db.flush()

        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        """Update an existing activity material."""
        item = (
            self.db.query(RewardActivityMaterial)
            .filter(
                RewardActivityMaterial.id == id,
                RewardActivityMaterial.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Activity material not found")

        for field in ("name", "description", "image_id"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete an activity material."""
        item = (
            self.db.query(RewardActivityMaterial)
            .filter(
                RewardActivityMaterial.id == id,
                RewardActivityMaterial.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Activity material not found")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
