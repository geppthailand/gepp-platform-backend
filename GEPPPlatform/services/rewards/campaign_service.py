"""
Campaign Service - Time-bound campaigns for earning and redeeming rewards
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardCampaign
from ...exceptions import APIException, NotFoundException, BadRequestException


def _parse_dt(value):
    """Convert ISO-format string to datetime, pass through datetime objects."""
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _safe_iso(val):
        if val is None:
            return None
        return val.isoformat() if hasattr(val, 'isoformat') else str(val)

    def _to_dict(self, item: RewardCampaign) -> dict:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "image_id": item.image_id,
            "start_date": self._safe_iso(item.start_date),
            "end_date": self._safe_iso(item.end_date),
            "status": item.status,
            "points_per_transaction_limit": item.points_per_transaction_limit,
            "points_per_day_limit": item.points_per_day_limit,
            "created_date": self._safe_iso(item.created_date),
            "updated_date": self._safe_iso(item.updated_date),
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
            start_date=_parse_dt(data["start_date"]),
            end_date=_parse_dt(data.get("end_date")),
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

        date_fields = ("start_date", "end_date")
        for field in ("name", "description", "image_id", "start_date", "end_date", "status", "points_per_transaction_limit", "points_per_day_limit"):
            if field in data:
                value = _parse_dt(data[field]) if field in date_fields else data[field]
                setattr(item, field, value)

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
