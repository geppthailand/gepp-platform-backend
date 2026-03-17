"""
Campaign Droppoint Service - Links droppoints to campaigns
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardCampaignDroppoint
from ...models.rewards.redemptions import Droppoint
from ...exceptions import APIException, NotFoundException, BadRequestException


class CampaignDroppointService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCampaignDroppoint, droppoint=None) -> dict:
        result = {
            "id": item.id,
            "campaign_id": item.campaign_id,
            "droppoint_id": item.droppoint_id,
            "tag_id": item.tag_id,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }
        if droppoint:
            result["droppoint_name"] = droppoint.name
            result["droppoint_hash"] = droppoint.hash
        return result

    def list(self, campaign_id: int) -> list[dict]:
        """Return all active campaign droppoints, joined with droppoint info."""
        rows = (
            self.db.query(RewardCampaignDroppoint, Droppoint)
            .outerjoin(
                Droppoint,
                RewardCampaignDroppoint.droppoint_id == Droppoint.id,
            )
            .filter(
                RewardCampaignDroppoint.campaign_id == campaign_id,
                RewardCampaignDroppoint.deleted_date.is_(None),
            )
            .order_by(RewardCampaignDroppoint.id.desc())
            .all()
        )
        return [self._to_dict(cd, dp) for cd, dp in rows]

    def create(self, data: dict) -> dict:
        """Create a new campaign droppoint link."""
        if not data.get("campaign_id"):
            raise BadRequestException("Campaign ID is required")
        if not data.get("droppoint_id"):
            raise BadRequestException("Droppoint ID is required")

        item = RewardCampaignDroppoint(
            campaign_id=data["campaign_id"],
            droppoint_id=data["droppoint_id"],
            tag_id=data.get("tag_id"),
        )
        self.db.add(item)
        self.db.flush()

        row = (
            self.db.query(RewardCampaignDroppoint, Droppoint)
            .outerjoin(
                Droppoint,
                RewardCampaignDroppoint.droppoint_id == Droppoint.id,
            )
            .filter(RewardCampaignDroppoint.id == item.id)
            .first()
        )
        return self._to_dict(row[0], row[1]) if row else self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a campaign droppoint link."""
        item = (
            self.db.query(RewardCampaignDroppoint)
            .filter(
                RewardCampaignDroppoint.id == id,
                RewardCampaignDroppoint.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign droppoint not found")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
