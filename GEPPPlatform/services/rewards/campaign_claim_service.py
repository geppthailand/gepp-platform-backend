"""
Campaign Claim Service - Links activity materials to campaigns with point rules
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import RewardCampaignClaim, RewardActivityMaterial, RewardCampaign
from ...exceptions import APIException, NotFoundException, BadRequestException
from .campaign_service import assert_editable


class CampaignClaimService:
    def __init__(self, db: Session):
        self.db = db

    def _to_dict(self, item: RewardCampaignClaim, activity_material=None) -> dict:
        result = {
            "id": item.id,
            "organization_id": item.organization_id,
            "campaign_id": item.campaign_id,
            "activity_material_id": item.activity_material_id,
            "points": float(item.points) if item.points is not None else None,
            "max_claims_total": item.max_claims_total,
            "max_claims_per_user": item.max_claims_per_user,
            "created_date": item.created_date.isoformat() if item.created_date else None,
            "updated_date": item.updated_date.isoformat() if item.updated_date else None,
        }
        if activity_material:
            result["activity_material_name"] = activity_material.name
            result["activity_material_type"] = activity_material.type
        return result

    def list(self, campaign_id: int) -> list[dict]:
        """Return all active claims for a campaign, joined with activity material info."""
        rows = (
            self.db.query(RewardCampaignClaim, RewardActivityMaterial)
            .outerjoin(
                RewardActivityMaterial,
                RewardCampaignClaim.activity_material_id == RewardActivityMaterial.id,
            )
            .filter(
                RewardCampaignClaim.campaign_id == campaign_id,
                RewardCampaignClaim.deleted_date.is_(None),
            )
            .order_by(RewardCampaignClaim.id.desc())
            .all()
        )
        return [self._to_dict(claim, am) for claim, am in rows]

    def create(self, organization_id: int, data: dict) -> dict:
        """Create a new campaign claim rule.

        Side effect: if there is a soft-deleted RewardCampaignTarget pointing at this
        activity_material in this campaign, restore it (per Q4: "ตั้งกลับมาก็เอากลับมา").
        """
        if not data.get("campaign_id"):
            raise BadRequestException("Campaign ID is required")
        if not data.get("activity_material_id"):
            raise BadRequestException("Activity material ID is required")
        if data.get("points") is None:
            raise BadRequestException("Points value is required")

        item = RewardCampaignClaim(
            organization_id=organization_id,
            campaign_id=data["campaign_id"],
            activity_material_id=data["activity_material_id"],
            points=data["points"],
            max_claims_total=data.get("max_claims_total"),
            max_claims_per_user=data.get("max_claims_per_user"),
        )
        self.db.add(item)
        self.db.flush()

        # Restore targets that were soft-deleted when this material was last removed
        from .campaign_target_service import CampaignTargetService
        CampaignTargetService(self.db).restore_targets_for_activity_material(
            campaign_id=data["campaign_id"],
            activity_material_id=data["activity_material_id"],
        )

        # Re-query with join to get activity material info
        row = (
            self.db.query(RewardCampaignClaim, RewardActivityMaterial)
            .outerjoin(
                RewardActivityMaterial,
                RewardCampaignClaim.activity_material_id == RewardActivityMaterial.id,
            )
            .filter(RewardCampaignClaim.id == item.id)
            .first()
        )
        return self._to_dict(row[0], row[1]) if row else self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        """Update an existing campaign claim rule.

        Guard: changing `points` is a BREAKING edit — reject if campaign is active.
        Changing max_claims_* (limits) is considered safe.
        """
        item = (
            self.db.query(RewardCampaignClaim)
            .filter(
                RewardCampaignClaim.id == id,
                RewardCampaignClaim.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign claim not found")

        # Check if points rate is being changed — that's breaking
        points_changed = "points" in data and float(data["points"]) != float(item.points or 0)
        if points_changed:
            campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == item.campaign_id).first()
            if campaign:
                assert_editable(campaign, breaking=True)

        for field in ("points", "max_claims_total", "max_claims_per_user"):
            if field in data:
                setattr(item, field, data[field])

        self.db.flush()

        row = (
            self.db.query(RewardCampaignClaim, RewardActivityMaterial)
            .outerjoin(
                RewardActivityMaterial,
                RewardCampaignClaim.activity_material_id == RewardActivityMaterial.id,
            )
            .filter(RewardCampaignClaim.id == item.id)
            .first()
        )
        return self._to_dict(row[0], row[1]) if row else self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Soft delete a campaign claim rule. Breaking: reject if campaign is active.

        Side effect: soft-delete any RewardCampaignTarget pointing at this activity_material
        in this campaign (per Q4 — keeps target out of progress calc until material re-added).
        """
        item = (
            self.db.query(RewardCampaignClaim)
            .filter(
                RewardCampaignClaim.id == id,
                RewardCampaignClaim.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign claim not found")

        campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == item.campaign_id).first()
        if campaign:
            assert_editable(campaign, breaking=True)

        from .campaign_target_service import CampaignTargetService
        CampaignTargetService(self.db).soft_delete_targets_for_activity_material(
            campaign_id=item.campaign_id,
            activity_material_id=item.activity_material_id,
        )

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()

        return {"id": id, "deleted": True}
