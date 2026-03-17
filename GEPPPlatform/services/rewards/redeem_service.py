"""
Redeem Service - User redeeming rewards from catalog
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, distinct
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

        # 1. Calculate available points for user in this campaign
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

            # 2c. Check stock
            current_stock = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == catalog_id,
                    RewardStock.reward_campaign_id == campaign_id,
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

        # 4. Create stock withdrawals and redemption records
        redemptions = []
        for ri in redemption_items:
            # 4a. Withdraw stock
            stock_record = RewardStock(
                reward_catalog_id=ri["catalog_id"],
                values=-ri["quantity"],
                reward_campaign_id=campaign_id,
                note="redemption",
                reward_user_id=reward_user_id,
            )
            self.db.add(stock_record)
            self.db.flush()

            # 4b. Create redemption record
            redemption_hash = uuid.uuid4().hex
            redemption = RewardRedemption(
                organization_id=organization_id,
                reward_user_id=reward_user_id,
                reward_campaign_id=campaign_id,
                catalog_id=ri["catalog_id"],
                points_redeemed=int(ri["item_cost"]),
                quantity=ri["quantity"],
                status="inprogress",
                stock_action_id=stock_record.id,
                hash=redemption_hash,
            )
            self.db.add(redemption)
            self.db.flush()

            catalog = (
                self.db.query(RewardCatalog)
                .filter(RewardCatalog.id == ri["catalog_id"])
                .first()
            )

            redemptions.append({
                "hash": redemption_hash,
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
            "redemptions": redemptions,
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

            stock_remaining = (
                self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
                .filter(
                    RewardStock.reward_catalog_id == link.catalog_id,
                    RewardStock.reward_campaign_id == campaign_id,
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
