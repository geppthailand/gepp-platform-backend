"""
Redeem Service - User redeeming rewards from catalog
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, distinct, or_
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardCampaign,
    RewardCampaignCatalog,
)
from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import RewardRedemption, OrganizationRewardUser
from ...exceptions import NotFoundException, BadRequestException


class RedeemService:
    """Handles user redeeming rewards."""

    def __init__(self, db: Session):
        self.db = db

    def submit_redemption(
        self,
        reward_user_id: int,
        organization_id: int,
        campaign_id: int,
        items: list[dict],
    ) -> dict:
        """
        Submit a redemption request.
        items = [{"catalog_id": int, "quantity": int}, ...]
        """
        if not items:
            raise BadRequestException("At least one item is required")

        # 0. Verify campaign is active AND not past end_date (ended = computed)
        now = datetime.now(timezone.utc)
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == campaign_id,
                RewardCampaign.status == "active",
                or_(RewardCampaign.end_date.is_(None), RewardCampaign.end_date >= now),
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise BadRequestException("Campaign not active, ended, or not found")

        # 1. Lock the user's point rows for this campaign to prevent concurrent overdraw,
        #    then calculate balance. FOR UPDATE cannot be used with aggregate functions,
        #    so we lock first, then SUM separately.
        self.db.query(RewardPointTransaction.id).filter(
            RewardPointTransaction.reward_user_id == reward_user_id,
            RewardPointTransaction.organization_id == organization_id,
            RewardPointTransaction.reward_campaign_id == campaign_id,
            RewardPointTransaction.deleted_date.is_(None),
        ).with_for_update().all()

        available_points = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reward_campaign_id == campaign_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        )
        available_points = Decimal(str(available_points))

        total_cost = Decimal("0")
        redemption_items = []

        for item in items:
            catalog_id = item.get("catalog_id")
            quantity = item.get("quantity", 1)

            if not catalog_id or quantity <= 0:
                raise BadRequestException("Each item requires catalog_id and positive quantity")

            # 2a. Get campaign catalog link
            campaign_catalog = (
                self.db.query(RewardCampaignCatalog)
                .filter(
                    RewardCampaignCatalog.campaign_id == campaign_id,
                    RewardCampaignCatalog.catalog_id == catalog_id,
                    RewardCampaignCatalog.status == "active",
                    RewardCampaignCatalog.deleted_date.is_(None),
                )
                .first()
            )
            if not campaign_catalog:
                raise NotFoundException(f"Catalog item {catalog_id} not available in this campaign")

            # 2b. Calculate cost
            points_cost = campaign_catalog.points_cost
            item_cost = Decimal(str(points_cost)) * quantity
            total_cost += item_cost

            # 2c. Check stock (campaign-specific + global)
            from sqlalchemy import or_
            current_stock = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == catalog_id,
                    or_(
                        RewardStock.reward_campaign_id == campaign_id,
                        RewardStock.reward_campaign_id.is_(None),
                    ),
                    RewardStock.deleted_date.is_(None),
                )
                .scalar()
            )
            if int(current_stock) < quantity:
                catalog = (
                    self.db.query(RewardCatalog)
                    .filter(RewardCatalog.id == catalog_id)
                    .first()
                )
                name = catalog.name if catalog else f"ID {catalog_id}"
                raise BadRequestException(f"Insufficient stock for '{name}'")

            redemption_items.append({
                "catalog_id": catalog_id,
                "quantity": quantity,
                "points_cost": points_cost,
                "item_cost": item_cost,
                "campaign_catalog": campaign_catalog,
            })

        # 3. Check total cost against available points
        if total_cost > available_points:
            raise BadRequestException(
                f"Insufficient points. Available: {float(available_points)}, required: {float(total_cost)}"
            )

        # 4. Create redemption records with shared group hash (NO stock withdrawal yet)
        group_hash = uuid.uuid4().hex
        redemptions = []
        for ri in redemption_items:
            redemption = RewardRedemption(
                organization_id=organization_id,
                reward_user_id=reward_user_id,
                reward_campaign_id=campaign_id,
                catalog_id=ri["catalog_id"],
                points_redeemed=int(ri["item_cost"]),
                quantity=ri["quantity"],
                status="inprogress",
                stock_action_id=None,  # stock deducted at confirm time
                hash=uuid.uuid4().hex,  # per-item hash (backward compat)
                redemption_group_hash=group_hash,  # shared cart hash
            )
            self.db.add(redemption)
            self.db.flush()

            catalog = (
                self.db.query(RewardCatalog)
                .filter(RewardCatalog.id == ri["catalog_id"])
                .first()
            )

            redemptions.append({
                "hash": redemption.hash,
                "catalog_name": catalog.name if catalog else None,
                "quantity": ri["quantity"],
                "points_cost": ri["points_cost"],
            })

        # 5. Deduct points
        point_txn = RewardPointTransaction(
            organization_id=organization_id,
            reward_user_id=reward_user_id,
            points=-total_cost,
            reward_campaign_id=campaign_id,
            claimed_date=datetime.now(timezone.utc),
            reference_type="redeem",
        )
        self.db.add(point_txn)
        self.db.flush()

        return {
            "success": True,
            "group_hash": group_hash,
            "redemptions": redemptions,
        }

    def cancel_redemption(self, reward_user_id: int, redemption_id: int) -> dict:
        """Cancel an inprogress redemption and refund points."""
        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.id == redemption_id,
                RewardRedemption.reward_user_id == reward_user_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .first()
        )
        if not redemption:
            raise NotFoundException("Redemption not found")
        if redemption.status != "inprogress":
            raise BadRequestException(f"Cannot cancel redemption with status '{redemption.status}'")

        # 1. Set status to canceled
        redemption.status = "canceled"
        redemption.updated_date = datetime.now(timezone.utc)
        self.db.flush()

        # 2. Refund points (positive transaction)
        refund_txn = RewardPointTransaction(
            organization_id=redemption.organization_id,
            reward_user_id=reward_user_id,
            points=redemption.points_redeemed,
            reward_campaign_id=redemption.reward_campaign_id,
            claimed_date=datetime.now(timezone.utc),
            reference_type="refund",
        )
        self.db.add(refund_txn)
        self.db.flush()

        return {
            "success": True,
            "refunded_points": redemption.points_redeemed,
            "redemption_id": redemption.id,
        }

    def reject_redemption_by_hash(self, hash: str, note: str = None) -> dict:
        """Staff rejects redemption(s) by hash or group_hash — cancel + refund points."""
        # Try group_hash first
        redemptions = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.redemption_group_hash == hash,
                RewardRedemption.status == "inprogress",
                RewardRedemption.deleted_date.is_(None),
            )
            .all()
        )
        if not redemptions:
            # Fallback to single hash
            single = (
                self.db.query(RewardRedemption)
                .filter(
                    RewardRedemption.hash == hash,
                    RewardRedemption.status == "inprogress",
                    RewardRedemption.deleted_date.is_(None),
                )
                .first()
            )
            if not single:
                raise NotFoundException("No inprogress redemption found for this QR")
            redemptions = [single]

        now = datetime.now(timezone.utc)
        total_refunded = 0

        for r in redemptions:
            r.status = "canceled"
            r.note = note or "Rejected by staff"
            r.updated_date = now
            self.db.flush()

            refund_txn = RewardPointTransaction(
                organization_id=r.organization_id,
                reward_user_id=r.reward_user_id,
                points=r.points_redeemed,
                reward_campaign_id=r.reward_campaign_id,
                claimed_date=now,
                reference_type="refund",
            )
            self.db.add(refund_txn)
            self.db.flush()
            total_refunded += r.points_redeemed

        return {
            "success": True,
            "canceled_count": len(redemptions),
            "total_refunded_points": total_refunded,
        }

    def get_user_organizations(self, reward_user_id: int) -> list[dict]:
        """Get organizations the user has earned points in, ordered by most recent claim."""
        from ...models.subscriptions.organizations import Organization

        rows = (
            self.db.query(
                RewardPointTransaction.organization_id,
                func.max(RewardPointTransaction.claimed_date).label("last_claim"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.organization_id)
            .order_by(func.max(RewardPointTransaction.claimed_date).desc())
            .all()
        )

        result = []
        for row in rows:
            org = (
                self.db.query(Organization)
                .filter(Organization.id == row.organization_id)
                .first()
            )
            result.append({
                "organization_id": row.organization_id,
                "organization_name": org.name if org else None,
            })

        return result

    def get_user_campaigns_for_redeem(
        self, reward_user_id: int, organization_id: int
    ) -> list[dict]:
        """Get campaigns the user has points in, with available balances."""
        rows = (
            self.db.query(
                RewardPointTransaction.reward_campaign_id,
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("available_points"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reward_campaign_id.isnot(None),
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_campaign_id)
            .all()
        )

        result = []
        for row in rows:
            available = float(row.available_points)
            if available <= 0:
                continue

            campaign = (
                self.db.query(RewardCampaign)
                .filter(RewardCampaign.id == row.reward_campaign_id)
                .first()
            )
            result.append({
                "campaign_id": row.reward_campaign_id,
                "name": campaign.name if campaign else None,
                "available_points": available,
            })

        return result

    def get_campaign_catalog_for_redeem(
        self, campaign_id: int, reward_user_id: int
    ) -> dict:
        """Get redeemable catalog items for a campaign with stock and user balance."""
        # User available points for this campaign
        available_points = (
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
            .filter(
                RewardPointTransaction.reward_user_id == reward_user_id,
                RewardPointTransaction.reward_campaign_id == campaign_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar()
        )

        # Campaign catalog items
        links = (
            self.db.query(RewardCampaignCatalog)
            .filter(
                RewardCampaignCatalog.campaign_id == campaign_id,
                RewardCampaignCatalog.status == "active",
                RewardCampaignCatalog.deleted_date.is_(None),
            )
            .all()
        )

        catalog_items = []
        for link in links:
            catalog = (
                self.db.query(RewardCatalog)
                .filter(
                    RewardCatalog.id == link.catalog_id,
                    RewardCatalog.deleted_date.is_(None),
                )
                .first()
            )
            if not catalog:
                continue

            # Stock = campaign-specific + global (campaign_id=NULL)
            from sqlalchemy import or_
            stock_remaining = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == link.catalog_id,
                    or_(
                        RewardStock.reward_campaign_id == campaign_id,
                        RewardStock.reward_campaign_id.is_(None),
                    ),
                    RewardStock.deleted_date.is_(None),
                )
                .scalar()
            )

            catalog_items.append({
                "id": link.id,
                "catalog_id": catalog.id,
                "name": catalog.name,
                "description": catalog.description,
                "thumbnail_id": catalog.thumbnail_id,
                "points_cost": link.points_cost,
                "stock_remaining": int(stock_remaining),
                "unit": catalog.unit,
            })

        return {
            "available_points": float(available_points),
            "catalog": catalog_items,
        }
