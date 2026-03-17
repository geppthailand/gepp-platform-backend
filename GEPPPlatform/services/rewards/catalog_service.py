"""
Catalog Service - Master reward items available for redemption
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.catalog import RewardCatalog
from ...exceptions import APIException, NotFoundException, BadRequestException


class CatalogService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCatalog) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "thumbnail_id": item.thumbnail_id,
            "images": item.images,
            "price": float(item.price) if item.price is not None else None,
            "unit": item.unit,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }

    def list(self, organization_id: int) -> list[dict]:
        """Return all active catalog items for an organization."""
        items = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.organization_id == organization_id,
                RewardCatalog.deleted_date.is_(None),
            )
            .order_by(RewardCatalog.id.desc())
            .all()
        )
        return [self._to_dict(i) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        """Create a new catalog item."""
        if not data.get("name"):
            raise BadRequestException("Name is required")

        item = RewardCatalog(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            thumbnail_id=data.get("thumbnail_id"),
            images=data.get("images"),
            price=data.get("price"),
            unit=data.get("unit"),
        )
        self.db.add(item)
        self.db.flush()

        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        """Update an existing catalog item."""
        item = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.id == id,
                RewardCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Catalog item not found")

        for field in ("name", "description", "thumbnail_id", "images", "price", "unit"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a catalog item."""
        item = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.id == id,
                RewardCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Catalog item not found")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
