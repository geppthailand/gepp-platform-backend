"""
Catalog Category Service — Org-managed preset categories for reward catalog items
"""

from __future__ import annotations  # required: list() method shadows built-in list

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.catalog import RewardCatalog, RewardCatalogCategory
from ...exceptions import NotFoundException, BadRequestException


class CatalogCategoryService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCatalogCategory) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "is_active": item.is_active,
        }

    def list(self, organization_id: int) -> list[dict]:
        items = (
            self.db.query(RewardCatalogCategory)
            .filter(
                RewardCatalogCategory.organization_id == organization_id,
                RewardCatalogCategory.deleted_date.is_(None),
            )
            .order_by(RewardCatalogCategory.name.asc())
            .all()
        )
        return [self._to_dict(i) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise BadRequestException("Category name is required")

        # Prevent duplicates in same org (case-insensitive)
        dup = (
            self.db.query(RewardCatalogCategory)
            .filter(
                RewardCatalogCategory.organization_id == organization_id,
                RewardCatalogCategory.deleted_date.is_(None),
                RewardCatalogCategory.name.ilike(name),
            )
            .first()
        )
        if dup:
            raise BadRequestException(f"Category '{name}' already exists")

        item = RewardCatalogCategory(
            organization_id=organization_id,
            name=name,
            description=data.get("description"),
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        item = (
            self.db.query(RewardCatalogCategory)
            .filter(
                RewardCatalogCategory.id == id,
                RewardCatalogCategory.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Category not found")

        if "name" in data:
            new_name = (data["name"] or "").strip()
            if not new_name:
                raise BadRequestException("Category name is required")
            item.name = new_name
        if "description" in data:
            item.description = data["description"]

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete — blocks if any catalog item still uses this category."""
        item = (
            self.db.query(RewardCatalogCategory)
            .filter(
                RewardCatalogCategory.id == id,
                RewardCatalogCategory.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Category not found")

        in_use = (
            self.db.query(RewardCatalog)
            .filter(
                RewardCatalog.category_id == id,
                RewardCatalog.deleted_date.is_(None),
            )
            .count()
        )
        if in_use > 0:
            raise BadRequestException(
                f"Cannot delete — {in_use} catalog item(s) still use this category"
            )

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}
