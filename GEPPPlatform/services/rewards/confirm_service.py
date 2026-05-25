"""
Confirm Service - Staff confirming redemptions and deducting stock
Supports both single-item hash (backward compat) and group hash (cart)
"""

from datetime import datetime, timezone

from sqlalchemy import func, update, or_
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import RewardRedemption, RewardUser, OrganizationRewardUser
from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...models.rewards.management import RewardCampaign
from ...models.rewards.points import RewardPointTransaction
from ...exceptions import NotFoundException, BadRequestException


class ConfirmService:
    """Handles staff confirming redemptions — deducts stock at confirm time."""

    def __init__(self, db: Session):
        self.db = db

    def lookup_redemption(self, hash: str, organization_id: int) -> dict:
        """Look up redemption(s) by hash or group_hash — preview only, no confirm.

        Scoped to organization_id so staff cannot lookup another org's coupons.
        """
        # Try group_hash first
        redemptions = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.redemption_group_hash == hash,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .all()
        )
        if not redemptions:
            # Fallback to per-item hash
            single = (
                self.db.query(RewardRedemption)
                .filter(
                    RewardRedemption.hash == hash,
                    RewardRedemption.organization_id == organization_id,
                    RewardRedemption.deleted_date.is_(None),
                )
                .first()
            )
            if not single:
                raise NotFoundException("Redemption not found")
            redemptions = [single]

        # Get user info
        user_id = redemptions[0].reward_user_id
        user = self.db.query(RewardUser).filter(RewardUser.id == user_id).first()

        # Get campaign info
        campaign_id = redemptions[0].reward_campaign_id
        campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == campaign_id).first()

        # Build items list with catalog names
        items = []
        total_points = 0
        for r in redemptions:
            catalog = self.db.query(RewardCatalog).filter(RewardCatalog.id == r.catalog_id).first()
            items.append({
                "id": r.id,
                "hash": r.hash,
                "catalog_id": r.catalog_id,
                "catalog_name": catalog.name if catalog else None,
                "quantity": r.quantity,
                "points_redeemed": r.points_redeemed,
                "status": r.status,
            })
            total_points += r.points_redeemed

        return {
            "group_hash": redemptions[0].redemption_group_hash,
            "status": redemptions[0].status,
            "user": {
                "id": user.id if user else user_id,
                "display_name": (user.display_name or user.line_display_name) if user else None,
                "line_picture_url": user.line_picture_url if user else None,
            },
            "campaign": {
                "id": campaign_id,
                "name": campaign.name if campaign else None,
            },
            "items": items,
            "total_points": total_points,
            "created_date": redemptions[0].created_date.isoformat() if redemptions[0].created_date else None,
        }

    def confirm_redemption(
        self,
        hash: str = None,
        group_hash: str = None,
        staff_org_user_id: int = None,
        organization_id: int = None,
    ) -> dict:
        """Confirm redemption(s) by hash or group_hash.
        Stock is deducted here (not at redeem time).

        organization_id must match the redemption's org — prevents cross-org confirms.
        """
        if organization_id is None:
            raise BadRequestException("organization_id is required")

        # Try group_hash first, then fall back to per-item hash
        if group_hash:
            # Check if group exists in this org
            group_exists = (
                self.db.query(RewardRedemption)
                .filter(
                    RewardRedemption.redemption_group_hash == group_hash,
                    RewardRedemption.organization_id == organization_id,
                    RewardRedemption.deleted_date.is_(None),
                )
                .first()
            )
            if group_exists:
                return self._confirm_group(group_hash, staff_org_user_id, organization_id)

        if hash:
            return self._confirm_single(hash, staff_org_user_id, organization_id)

        raise BadRequestException("Either hash or group_hash is required")

    def _confirm_single(self, hash: str, staff_org_user_id: int, organization_id: int) -> dict:
        """Confirm a single redemption by its per-item hash."""
        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.hash == hash,
                RewardRedemption.organization_id == organization_id,
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

        # Atomic status transition: only succeeds if status is still 'inprogress'
        if not self._atomic_claim_status(redemption.id, staff_org_user_id):
            # Another request confirmed it between our read and update
            self.db.refresh(redemption)
            if redemption.status == "completed":
                return self._already_completed_response(redemption)
            raise BadRequestException(f"Unexpected status: {redemption.status}")

        # Deduct stock (status already set to 'completed' atomically).
        # If stock turns out to be insufficient (TOCTOU between submit and confirm),
        # _deduct_stock auto-cancels the redemption + refunds points and returns the
        # cancellation info; we surface that to staff instead of raising 500.
        self.db.refresh(redemption)
        cancel_info = self._deduct_stock(redemption)
        if cancel_info is not None:
            return {
                "success": False,
                "auto_canceled": [cancel_info],
                "confirmed_items": [],
            }

        return {
            "success": True,
            "confirmed_items": [self._item_dict(redemption)],
        }

    def _confirm_group(self, group_hash: str, staff_org_user_id: int, organization_id: int) -> dict:
        """Confirm all redemptions in a cart group."""
        redemptions = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.redemption_group_hash == group_hash,
                RewardRedemption.organization_id == organization_id,
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

        # Atomic status transition + stock deduction for each item.
        # Auto-canceled items (insufficient stock at confirm time) are reported
        # alongside successfully-confirmed ones so staff can communicate to the member.
        confirmed_items = []
        auto_canceled = []
        for redemption in pending:
            if self._atomic_claim_status(redemption.id, staff_org_user_id):
                self.db.refresh(redemption)
                cancel_info = self._deduct_stock(redemption)
                if cancel_info is not None:
                    auto_canceled.append(cancel_info)
                else:
                    confirmed_items.append(self._item_dict(redemption))

        if not confirmed_items and not auto_canceled:
            raise BadRequestException("All items were already confirmed by another request")

        return {
            "success": len(confirmed_items) > 0,
            "group_hash": group_hash,
            "confirmed_items": confirmed_items,
            "auto_canceled": auto_canceled,
        }

    def _atomic_claim_status(self, redemption_id: int, staff_org_user_id: int) -> bool:
        """Atomically set status='completed' only if currently 'inprogress'.
        Returns True if the row was updated (we won the race), False otherwise."""
        now = datetime.now(timezone.utc)
        result = self.db.execute(
            update(RewardRedemption)
            .where(
                RewardRedemption.id == redemption_id,
                RewardRedemption.status == "inprogress",
            )
            .values(
                status="completed",
                staff_id=staff_org_user_id,
                updated_date=now,
            )
        )
        self.db.flush()
        return result.rowcount > 0

    def _deduct_stock(self, redemption: RewardRedemption) -> dict | None:
        """Deduct stock for a single redemption item (status already set to completed).

        Concurrency: locks the catalog row with SELECT ... FOR UPDATE before reading
        the stock sum + inserting the -quantity ledger entry. This serialises
        concurrent redemptions on the same item and prevents the stock total from
        going negative through a TOCTOU race.

        Returns None on success. If stock is insufficient (e.g. another submission
        depleted it between submit and confirm), this method auto-cancels the
        redemption and refunds points to the user, then returns a dict describing
        the auto-cancel so the caller can report it to staff.
        """
        # Lock the catalog row to serialise stock operations for this item.
        # Released at transaction commit / rollback.
        self.db.query(RewardCatalog).filter(
            RewardCatalog.id == redemption.catalog_id
        ).with_for_update().first()

        current_stock = (
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .filter(
                RewardStock.reward_catalog_id == redemption.catalog_id,
                or_(
                    RewardStock.reward_campaign_id == redemption.reward_campaign_id,
                    RewardStock.reward_campaign_id.is_(None),
                ),
                RewardStock.deleted_date.is_(None),
            )
            .scalar()
        )

        if int(current_stock) < redemption.quantity:
            # Auto-cancel + refund instead of raising (which would leave the user
            # with deducted points and a 'completed' status that has no stock row).
            catalog = (
                self.db.query(RewardCatalog)
                .filter(RewardCatalog.id == redemption.catalog_id)
                .first()
            )
            name = catalog.name if catalog else f"ID {redemption.catalog_id}"

            redemption.status = "canceled"
            redemption.updated_date = datetime.now(timezone.utc)
            refund_txn = RewardPointTransaction(
                organization_id=redemption.organization_id,
                reward_user_id=redemption.reward_user_id,
                points=abs(int(redemption.points_redeemed or 0)),
                reward_campaign_id=redemption.reward_campaign_id,
                claimed_date=datetime.now(timezone.utc),
                reference_type="refund",
            )
            self.db.add(refund_txn)
            self.db.flush()
            return {
                "auto_canceled": True,
                "reason": "insufficient_stock",
                "catalog_name": name,
                "available": int(current_stock),
                "needed": redemption.quantity,
                "refunded_points": int(redemption.points_redeemed or 0),
                "redemption_id": redemption.id,
            }

        stock_record = RewardStock(
            reward_catalog_id=redemption.catalog_id,
            values=-redemption.quantity,
            reward_campaign_id=redemption.reward_campaign_id,
            note="redemption_confirmed",
            reward_user_id=redemption.reward_user_id,
            ledger_type="redeem",
        )
        self.db.add(stock_record)
        self.db.flush()

        redemption.stock_action_id = stock_record.id
        self.db.flush()
        return None

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
