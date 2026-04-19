"""
Campaign Catalog Service - Links catalog items to campaigns with redeem rules
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardCampaignCatalog, RewardCampaign
from ...models.rewards.catalog import RewardCatalog
from ...exceptions import APIException, NotFoundException, BadRequestException
from .campaign_service import assert_editable


class CampaignCatalogService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _safe_iso(val):
        if val is None:
            return None
        return val.isoformat() if hasattr(val, 'isoformat') else str(val)

    def _to_dict(self, item: RewardCampaignCatalog, catalog=None) -> dict:
        result = {
            "id": item.id,
            "campaign_id": item.campaign_id,
            "catalog_id": item.catalog_id,
            "points_cost": item.points_cost,
            "start_date": self._safe_iso(item.start_date),
            "end_date": self._safe_iso(item.end_date),
            "status": item.status,
            "created_date": self._safe_iso(item.created_date),
            "updated_date": self._safe_iso(item.updated_date),
        }
        if catalog:
            result["catalog_name"] = catalog.name
            result["catalog_thumbnail_id"] = catalog.thumbnail_id
        return result

    def list(self, campaign_id: int) -> list[dict]:
        """Return all active campaign catalog entries, joined with catalog info."""
        rows = (
            self.db.query(RewardCampaignCatalog, RewardCatalog)
            .outerjoin(
                RewardCatalog,
                RewardCampaignCatalog.catalog_id == RewardCatalog.id,
            )
            .filter(
                RewardCampaignCatalog.campaign_id == campaign_id,
                RewardCampaignCatalog.deleted_date.is_(None),
            )
            .order_by(RewardCampaignCatalog.id.desc())
            .all()
        )
        return [self._to_dict(cc, cat) for cc, cat in rows]

    def create(self, data: dict) -> dict:
        """Create a new campaign catalog entry."""
        if not data.get("campaign_id"):
            raise BadRequestException("Campaign ID is required")
        if not data.get("catalog_id"):
            raise BadRequestException("Catalog ID is required")
        if data.get("points_cost") is None:
            raise BadRequestException("Points cost is required")

        item = RewardCampaignCatalog(
            campaign_id=data["campaign_id"],
            catalog_id=data["catalog_id"],
            points_cost=data["points_cost"],
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            status=data.get("status", "active"),
        )
        self.db.add(item)
        self.db.flush()

        row = (
            self.db.query(RewardCampaignCatalog, RewardCatalog)
            .outerjoin(
                RewardCatalog,
                RewardCampaignCatalog.catalog_id == RewardCatalog.id,
            )
            .filter(RewardCampaignCatalog.id == item.id)
            .first()
        )
        return self._to_dict(row[0], row[1]) if row else self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        """Update an existing campaign catalog entry."""
        item = (
            self.db.query(RewardCampaignCatalog)
            .filter(
                RewardCampaignCatalog.id == id,
                RewardCampaignCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign catalog entry not found")

        # points_cost change is a BREAKING edit — reject if campaign is active
        points_changed = "points_cost" in data and int(data["points_cost"]) != int(item.points_cost or 0)
        if points_changed:
            campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == item.campaign_id).first()
            if campaign:
                assert_editable(campaign, breaking=True)

        for field in ("points_cost", "start_date", "end_date", "status"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()

        row = (
            self.db.query(RewardCampaignCatalog, RewardCatalog)
            .outerjoin(
                RewardCatalog,
                RewardCampaignCatalog.catalog_id == RewardCatalog.id,
            )
            .filter(RewardCampaignCatalog.id == item.id)
            .first()
        )
        return self._to_dict(row[0], row[1]) if row else self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a campaign catalog entry. Breaking: reject if campaign is active."""
        item = (
            self.db.query(RewardCampaignCatalog)
            .filter(
                RewardCampaignCatalog.id == id,
                RewardCampaignCatalog.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign catalog entry not found")

        campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == item.campaign_id).first()
        if campaign:
            assert_editable(campaign, breaking=True)

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
