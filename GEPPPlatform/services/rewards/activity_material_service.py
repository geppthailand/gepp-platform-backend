"""
Activity Material Service - Materials or activities that can earn points
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardActivityMaterial
from ...models.cores.packagings import Packaging
from ...exceptions import APIException, NotFoundException, BadRequestException
from .packaging_conversion import compositions, packaging_label

TYPES = ("material", "activity", "packaging")


class ActivityMaterialService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardActivityMaterial, comp: dict | None = None) -> dict:
        out = {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "type": item.type,
            "material_id": item.material_id,
            "packaging_id": item.packaging_id,
            "image_id": item.image_id,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }
        if item.type == "packaging" and item.packaging_id:
            parts = (comp if comp is not None else compositions(self.db, [item.packaging_id])).get(int(item.packaging_id), [])
            out["packaging"] = {
                "id": item.packaging_id,
                "label": packaging_label(self.db, item.packaging_id),
                "kg_per_piece": float(sum((c["weight_kg"] for c in parts), 0)),
                "components": [{"material_id": c["material_id"], "name_th": c["name_th"], "name_en": c["name_en"],
                                "weight_kg": float(c["weight_kg"])} for c in parts],
            }
        return out

    def _check_packaging(self, packaging_id) -> int:
        """A packaging item must point at an active catalogue entry that has a composition."""
        try:
            pid = int(packaging_id)
        except (TypeError, ValueError):
            raise BadRequestException("packaging_id is required for a packaging item")
        p = self.db.query(Packaging).filter(Packaging.id == pid, Packaging.deleted_date.is_(None),
                                            Packaging.is_active.is_(True)).first()
        if not p:
            raise BadRequestException("Packaging not found")
        if not compositions(self.db, [pid]).get(pid):
            raise BadRequestException("This packaging has no material composition yet")
        return pid

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
        comp = compositions(self.db, [i.packaging_id for i in items if i.type == "packaging"])
        return [self._to_dict(i, comp) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        """Create a new activity material."""
        if not data.get("name"):
            raise BadRequestException("Name is required")
        if data.get("type") not in TYPES:
            raise BadRequestException("Type must be 'material', 'activity' or 'packaging'")
        packaging_id = self._check_packaging(data.get("packaging_id")) if data["type"] == "packaging" else None

        item = RewardActivityMaterial(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            type=data["type"],
            material_id=data.get("material_id") if data["type"] == "material" else None,
            packaging_id=packaging_id,
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

        if "type" in data and data["type"] not in TYPES:
            raise BadRequestException("Type must be 'material', 'activity' or 'packaging'")
        for field in ("name", "description", "type", "material_id", "image_id"):
            if field in data:
                setattr(item, field, data[field])
        if item.type == "packaging":
            if "packaging_id" in data or not item.packaging_id:
                item.packaging_id = self._check_packaging(data.get("packaging_id", item.packaging_id))
            item.material_id = None
        else:
            item.packaging_id = None

        # Clear material_id if type changed to activity
        if data.get("type") == "activity":
            item.material_id = None

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
