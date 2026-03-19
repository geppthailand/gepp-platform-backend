"""
History Service - Point and redemption history for users and staff
"""

import math

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import RewardRedemption
from ...models.rewards.catalog import RewardCatalog
from ...models.rewards.management import RewardCampaign, RewardActivityMaterial
from ...exceptions import APIException


class HistoryService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _paginate(query, page: int, per_page: int) -> tuple:
        """Apply pagination and return (items, pagination_meta)."""
        total = query.count()
        total_pages = math.ceil(total / per_page) if per_page > 0 else 0
        items = query.offset((page - 1) * per_page).limit(per_page).all()
        return items, {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        }

    def point_history(
        self,
        reward_user_id: int,
        organization_id: int = None,
        campaign_id: int = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """Paginated point transaction history for a user."""
        query = (
            self.db.query(
                RewardPointTransaction,
                RewardCampaign.name.label("campaign_name"),
                RewardActivityMaterial.name.label("activity_name"),
            )
            .outerjoin(
                RewardCampaign,
                RewardCampaign.id == RewardPointTransaction.reward_campaign_id,
            )
            .outerjoin(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )

        if organization_id is not None:
            query = query.filter(RewardPointTransaction.organization_id == organization_id)
        if campaign_id is not None:
            query = query.filter(RewardPointTransaction.reward_campaign_id == campaign_id)

        query = query.order_by(RewardPointTransaction.claimed_date.desc().nullslast())
        rows, pagination = self._paginate(query, page, per_page)

        items = [
            {
                "id": txn.id,
                "points": float(txn.points),
                "value": float(txn.value) if txn.value else None,
                "unit": txn.unit,
                "reference_type": txn.reference_type,
                "campaign_id": txn.reward_campaign_id,
                "campaign_name": campaign_name,
                "activity_material_id": txn.reward_activity_materials_id,
                "activity_name": activity_name,
                "claimed_date": txn.claimed_date.isoformat() if txn.claimed_date else None,
                "created_date": txn.created_date.isoformat() if txn.created_date else None,
            }
            for txn, campaign_name, activity_name in rows
        ]

        return {"items": items, "pagination": pagination}

    def redemption_history(
        self,
        reward_user_id: int,
        organization_id: int = None,
        campaign_id: int = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """Paginated redemption history for a user."""
        query = (
            self.db.query(
                RewardRedemption,
                RewardCatalog.name.label("catalog_name"),
                RewardCampaign.name.label("campaign_name"),
            )
            .join(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
            .join(RewardCampaign, RewardCampaign.id == RewardRedemption.reward_campaign_id)
            .filter(
                RewardRedemption.reward_user_id == reward_user_id,
                RewardRedemption.deleted_date.is_(None),
            )
        )

        if organization_id is not None:
            query = query.filter(RewardRedemption.organization_id == organization_id)
        if campaign_id is not None:
            query = query.filter(RewardRedemption.reward_campaign_id == campaign_id)

        query = query.order_by(RewardRedemption.created_date.desc())
        rows, pagination = self._paginate(query, page, per_page)

        items = [
            {
                "id": r.id,
                "hash": r.hash,
                "catalog_id": r.catalog_id,
                "catalog_name": catalog_name,
                "campaign_id": r.reward_campaign_id,
                "campaign_name": campaign_name,
                "quantity": r.quantity,
                "points_redeemed": r.points_redeemed,
                "status": r.status,
                "created_date": r.created_date.isoformat() if r.created_date else None,
            }
            for r, catalog_name, campaign_name in rows
        ]

        return {"items": items, "pagination": pagination}

    def staff_claim_history(
        self,
        staff_org_user_id: int,
        organization_id: int,
        campaign_id: int = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """Paginated claim history for a staff member."""
        query = (
            self.db.query(
                RewardPointTransaction,
                RewardCampaign.name.label("campaign_name"),
                RewardActivityMaterial.name.label("activity_name"),
            )
            .outerjoin(
                RewardCampaign,
                RewardCampaign.id == RewardPointTransaction.reward_campaign_id,
            )
            .outerjoin(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.staff_id == staff_org_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )

        if campaign_id is not None:
            query = query.filter(RewardPointTransaction.reward_campaign_id == campaign_id)

        query = query.order_by(RewardPointTransaction.claimed_date.desc().nullslast())
        rows, pagination = self._paginate(query, page, per_page)

        items = [
            {
                "id": txn.id,
                "reward_user_id": txn.reward_user_id,
                "points": float(txn.points),
                "value": float(txn.value) if txn.value else None,
                "unit": txn.unit,
                "reference_type": txn.reference_type,
                "campaign_id": txn.reward_campaign_id,
                "campaign_name": campaign_name,
                "activity_material_id": txn.reward_activity_materials_id,
                "activity_name": activity_name,
                "droppoint_id": txn.droppoint_id,
                "claimed_date": txn.claimed_date.isoformat() if txn.claimed_date else None,
                "created_date": txn.created_date.isoformat() if txn.created_date else None,
            }
            for txn, campaign_name, activity_name in rows
        ]

        return {"items": items, "pagination": pagination}

    def staff_redemption_history(
        self,
        staff_org_user_id: int,
        organization_id: int,
        campaign_id: int = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """Paginated redemption confirmations by a staff member."""
        query = (
            self.db.query(
                RewardRedemption,
                RewardCatalog.name.label("catalog_name"),
                RewardCampaign.name.label("campaign_name"),
            )
            .join(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
            .join(RewardCampaign, RewardCampaign.id == RewardRedemption.reward_campaign_id)
            .filter(
                RewardRedemption.staff_id == staff_org_user_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
        )

        if campaign_id is not None:
            query = query.filter(RewardRedemption.reward_campaign_id == campaign_id)

        query = query.order_by(RewardRedemption.created_date.desc())
        rows, pagination = self._paginate(query, page, per_page)

        items = [
            {
                "id": r.id,
                "hash": r.hash,
                "reward_user_id": r.reward_user_id,
                "catalog_id": r.catalog_id,
                "catalog_name": catalog_name,
                "campaign_id": r.reward_campaign_id,
                "campaign_name": campaign_name,
                "quantity": r.quantity,
                "points_redeemed": r.points_redeemed,
                "status": r.status,
                "created_date": r.created_date.isoformat() if r.created_date else None,
                "updated_date": r.updated_date.isoformat() if r.updated_date else None,
            }
            for r, catalog_name, campaign_name in rows
        ]

        return {"items": items, "pagination": pagination}

    def get_staff_daily_stats(
        self,
        staff_org_user_id: int,
        organization_id: int,
    ) -> dict:
        """Get aggregated stats for a staff member for today."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        claims_row = (
            self.db.query(
                func.count(RewardPointTransaction.id).label("count"),
                func.coalesce(func.sum(RewardPointTransaction.value), 0).label("total_weight"),
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("total_points"),
            )
            .filter(
                RewardPointTransaction.staff_id == staff_org_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= today_start,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .first()
        )

        confirms_count = (
            self.db.query(func.count(RewardRedemption.id))
            .filter(
                RewardRedemption.staff_id == staff_org_user_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.status == "completed",
                RewardRedemption.updated_date >= today_start,
                RewardRedemption.deleted_date.is_(None),
            )
            .scalar()
        ) or 0

        return {
            "today_claims_count": claims_row.count if claims_row else 0,
            "today_weight_total": float(claims_row.total_weight) if claims_row else 0,
            "today_points_issued": float(claims_row.total_points) if claims_row else 0,
            "today_confirms_count": confirms_count,
        }
