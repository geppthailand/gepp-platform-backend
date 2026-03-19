"""
Confirm Service - Staff confirming redemptions and deducting stock
Supports both single-item hash (backward compat) and group hash (cart)
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import RewardRedemption, OrganizationRewardUser
from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...exceptions import NotFoundException, BadRequestException


class ConfirmService:
    """Handles staff confirming redemptions — deducts stock at confirm time."""

    def __init__(self, db: Session):
        self.db = db

    def confirm_redemption(
        self,
        hash: str = None,
        group_hash: str = None,
        staff_org_user_id: int = None,
    ) -> dict:
        """Confirm redemption(s) by hash or group_hash.
        Stock is deducted here (not at redeem time)."""

        if group_hash:
            return self._confirm_group(group_hash, staff_org_user_id)
        elif hash:
            return self._confirm_single(hash, staff_org_user_id)
        else:
            raise BadRequestException("Either hash or group_hash is required")

    def _confirm_single(self, hash: str, staff_org_user_id: int) -> dict:
        """Confirm a single redemption by its per-item hash."""
        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.hash == hash,
                RewardRedemption.deleted_date.is_(None),
            )
            .first()
        )
        if not redemption:
            raise NotFoundException("Redemption not found")

        if redemption.status == "completed":
            return self._already_completed_response(redemption)
        if redemption.status == "canceled":
            raise BadRequestException("Redemption was canceled")
        if redemption.status != "inprogress":
            raise BadRequestException(f"Unexpected status: {redemption.status}")

        # Deduct stock and confirm
        self._deduct_stock_and_confirm(redemption, staff_org_user_id)

        return {
            "success": True,
            "confirmed_items": [self._item_dict(redemption)],
        }

    def _confirm_group(self, group_hash: str, staff_org_user_id: int) -> dict:
        """Confirm all redemptions in a cart group."""
        redemptions = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.redemption_group_hash == group_hash,
                RewardRedemption.deleted_date.is_(None),
            )
            .all()
        )
        if not redemptions:
            raise NotFoundException("Redemption group not found")

        # Check if all already completed
        if all(r.status == "completed" for r in redemptions):
            return {
                "already_completed": True,
                "completed_at": max(
                    (r.updated_date for r in redemptions if r.updated_date),
                    default=None,
                ),
                "confirmed_items": [self._item_dict(r) for r in redemptions],
            }

        # Check for canceled items
        canceled = [r for r in redemptions if r.status == "canceled"]
        if canceled:
            raise BadRequestException(
                f"{len(canceled)} item(s) in this group have been canceled"
            )

        # Filter to inprogress items only
        pending = [r for r in redemptions if r.status == "inprogress"]
        if not pending:
            raise BadRequestException("No items to confirm in this group")

        # Deduct stock and confirm each item
        confirmed_items = []
        for redemption in pending:
            self._deduct_stock_and_confirm(redemption, staff_org_user_id)
            confirmed_items.append(self._item_dict(redemption))

        return {
            "success": True,
            "group_hash": group_hash,
            "confirmed_items": confirmed_items,
        }

    def _deduct_stock_and_confirm(self, redemption: RewardRedemption, staff_org_user_id: int):
        """Deduct stock for a single redemption item and mark as completed."""
        now = datetime.now(timezone.utc)

        # Check stock availability
        current_stock = (
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .filter(
                RewardStock.reward_catalog_id == redemption.catalog_id,
                RewardStock.reward_campaign_id == redemption.reward_campaign_id,
                RewardStock.deleted_date.is_(None),
            )
            .scalar()
        )

        if int(current_stock) < redemption.quantity:
            catalog = (
                self.db.query(RewardCatalog)
                .filter(RewardCatalog.id == redemption.catalog_id)
                .first()
            )
            name = catalog.name if catalog else f"ID {redemption.catalog_id}"
            raise BadRequestException(
                f"Insufficient stock for '{name}' (available: {int(current_stock)}, needed: {redemption.quantity})"
            )

        # Create stock withdrawal
        stock_record = RewardStock(
            reward_catalog_id=redemption.catalog_id,
            values=-redemption.quantity,
            reward_campaign_id=redemption.reward_campaign_id,
            note="redemption_confirmed",
            reward_user_id=redemption.reward_user_id,
        )
        self.db.add(stock_record)
        self.db.flush()

        # Update redemption
        redemption.status = "completed"
        redemption.staff_id = staff_org_user_id
        redemption.stock_action_id = stock_record.id
        redemption.updated_date = now
        self.db.flush()

    def _item_dict(self, r: RewardRedemption) -> dict:
        catalog = (
            self.db.query(RewardCatalog)
            .filter(RewardCatalog.id == r.catalog_id)
            .first()
        )
        return {
            "id": r.id,
            "hash": r.hash,
            "catalog_id": r.catalog_id,
            "catalog_name": catalog.name if catalog else None,
            "quantity": r.quantity,
            "points_redeemed": r.points_redeemed,
            "status": r.status,
        }

    def _already_completed_response(self, redemption: RewardRedemption) -> dict:
        return {
            "already_completed": True,
            "completed_at": redemption.updated_date.isoformat() if redemption.updated_date else None,
            "confirmed_items": [self._item_dict(redemption)],
        }
