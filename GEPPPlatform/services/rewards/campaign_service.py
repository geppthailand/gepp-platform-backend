"""
Campaign Service - Time-bound campaigns for earning and redeeming rewards
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardCampaign
from ...exceptions import APIException, NotFoundException, BadRequestException


class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCampaign) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "image_id": item.image_id,
            "start_date": item.start_date.isoformat() if item.start_date else None,
            "end_date": item.end_date.isoformat() if item.end_date else None,
            "status": item.status,
            "points_per_transaction_limit": item.points_per_transaction_limit,
            "points_per_day_limit": item.points_per_day_limit,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }

    def list(self, organization_id: int) -> list[dict]:
        """Return all active campaigns for an organization."""
        items = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .order_by(RewardCampaign.id.desc())
            .all()
        )
        return [self._to_dict(i) for i in items]

    def create(self, organization_id: int, data: dict) -> dict:
        """Create a new campaign."""
        if not data.get("name"):
            raise BadRequestException("Name is required")
        if not data.get("start_date"):
            raise BadRequestException("Start date is required")

        item = RewardCampaign(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            image_id=data.get("image_id"),
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            status=data.get("status", "active"),
            points_per_transaction_limit=data.get("points_per_transaction_limit"),
            points_per_day_limit=data.get("points_per_day_limit"),
        )
        self.db.add(item)
        self.db.flush()

        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        """Update an existing campaign."""
        item = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign not found")

        for field in ("name", "description", "image_id", "start_date", "end_date", "status", "points_per_transaction_limit", "points_per_day_limit"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a campaign."""
        item = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign not found")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
