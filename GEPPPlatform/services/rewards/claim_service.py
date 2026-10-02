"""
Claim Service - claiming points for a user.

Creates both reward point transactions AND real transactions in the main system.
Callers:
  - staff at a droppoint (source='staff', the original flow, via the LIFF)
  - an admin attaching a claim from the web Members tab (source='admin', Admin tools)
  - an approved self-submitted request (source='self', see ClaimRequestService), which
    reuses `prepare_claim` for validation + points and writes its own rows.
"""

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardSetup,
    RewardCampaign,
    RewardCampaignClaim,
    RewardCampaignDroppoint,
    RewardActivityMaterial,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import OrganizationRewardUser, Droppoint
from ...models.subscriptions.organizations import Organization
from ...models.transactions.transactions import Transaction, TransactionStatus
from ...models.transactions.transaction_records import TransactionRecord
from ...models.cores.references import Material
from ...exceptions import NotFoundException, BadRequestException


class ClaimService:
    """Validates claims, computes points, and writes the reward + waste rows."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Validation + points (shared with self-submitted requests)
    # ------------------------------------------------------------------
    def prepare_claim(
        self,
        reward_user_id: int,
        campaign_id: int,
        items: list[dict],
        droppoint_id: Optional[int],
        require_started: bool = False,
    ) -> dict:
        """Validate a claim and compute points per item without writing anything.

        Returns {campaign, setup, droppoint, is_new_member, items: [{activity_material_id,
        value, points, unit, activity_mat, material_id, main_material_id, category_id}]}.
        """
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
            raise NotFoundException("Campaign not found, not active, or has ended")
        if require_started and campaign.start_date is not None and campaign.start_date > now:
            raise BadRequestException("Campaign has not started yet")

        # [V3] Block claims for members whose org membership is deactivated.
        # First-time claimers have no membership row yet — those are allowed and
        # auto-registered after the claim. Only block when an existing membership is
        # explicitly deactivated by an admin.
        membership = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == campaign.organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if membership is not None and not membership.is_active:
            raise BadRequestException("Member account is deactivated — contact admin to reactivate")

        droppoint = None
        if droppoint_id is not None:
            dp_link = (
                self.db.query(RewardCampaignDroppoint)
                .filter(
                    RewardCampaignDroppoint.campaign_id == campaign_id,
                    RewardCampaignDroppoint.droppoint_id == droppoint_id,
                    RewardCampaignDroppoint.deleted_date.is_(None),
                )
                .first()
            )
            if not dp_link:
                raise BadRequestException("Droppoint is not linked to this campaign")
            droppoint = self.db.query(Droppoint).filter(Droppoint.id == droppoint_id).first()

        setup = (
            self.db.query(RewardSetup)
            .filter(
                RewardSetup.organization_id == campaign.organization_id,
                RewardSetup.deleted_date.is_(None),
            )
            .first()
        )
        rounding_method = setup.points_rounding_method if setup else "floor"
        setup_tz = setup.timezone if setup else "UTC"

        # Today's total for the per-day limit
        local_now = now.astimezone(ZoneInfo(setup_tz))
        local_today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_today_start = local_today_start.astimezone(timezone.utc)
        today_total = Decimal("0")
        if campaign.points_per_day_limit is not None:
            today_total = Decimal(str(
                self.db.query(func.coalesce(func.sum(RewardPointTransaction.points), 0))
                .filter(
                    RewardPointTransaction.reward_user_id == reward_user_id,
                    RewardPointTransaction.reward_campaign_id == campaign_id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.claimed_date >= utc_today_start,
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar()
            ))

        prepared = []
        # Cumulative points within THIS submission, so the per-transaction limit caps the
        # whole submission rather than each item individually.
        submission_total = Decimal("0")
        for item in items:
            activity_material_id = item.get("activity_material_id")
            value = Decimal(str(item.get("value", 0)))
            if not activity_material_id or value <= 0:
                raise BadRequestException("Each item requires activity_material_id and a positive value")

            claim_rule = (
                self.db.query(RewardCampaignClaim)
                .filter(
                    RewardCampaignClaim.campaign_id == campaign_id,
                    RewardCampaignClaim.activity_material_id == activity_material_id,
                    RewardCampaignClaim.deleted_date.is_(None),
                )
                .first()
            )
            if not claim_rule:
                raise NotFoundException(
                    f"No claim rule for activity_material_id={activity_material_id} in this campaign"
                )

            if claim_rule.max_claims_total is not None:
                total_claims = (
                    self.db.query(func.count(RewardPointTransaction.id))
                    .filter(
                        RewardPointTransaction.reward_campaign_id == campaign_id,
                        RewardPointTransaction.reward_activity_materials_id == activity_material_id,
                        RewardPointTransaction.reference_type == "claim",
                        RewardPointTransaction.deleted_date.is_(None),
                    )
                    .scalar()
                ) or 0
                if total_claims >= claim_rule.max_claims_total:
                    raise BadRequestException(
                        f"Total claim limit reached for activity_material_id={activity_material_id}"
                    )

            if claim_rule.max_claims_per_user is not None:
                user_claims = (
                    self.db.query(func.count(RewardPointTransaction.id))
                    .filter(
                        RewardPointTransaction.reward_user_id == reward_user_id,
                        RewardPointTransaction.reward_campaign_id == campaign_id,
                        RewardPointTransaction.reward_activity_materials_id == activity_material_id,
                        RewardPointTransaction.reference_type == "claim",
                        RewardPointTransaction.deleted_date.is_(None),
                    )
                    .scalar()
                ) or 0
                if user_claims >= claim_rule.max_claims_per_user:
                    raise BadRequestException(
                        f"Per-user claim limit reached for activity_material_id={activity_material_id}"
                    )

            points = claim_rule.points * value
            if rounding_method == "ceil":
                points = Decimal(str(math.ceil(points)))
            elif rounding_method == "round":
                points = Decimal(str(round(points)))
            else:  # floor (default)
                points = Decimal(str(math.floor(points)))

            if campaign.points_per_transaction_limit is not None:
                remaining_tx = Decimal(str(campaign.points_per_transaction_limit)) - submission_total
                points = min(points, max(Decimal("0"), remaining_tx))
                if points <= 0:
                    raise BadRequestException("Per-transaction point limit reached for this campaign")

            if campaign.points_per_day_limit is not None:
                remaining_daily = Decimal(str(campaign.points_per_day_limit)) - today_total
                points = min(points, max(Decimal("0"), remaining_daily))
                if points <= 0:
                    raise BadRequestException("Daily point limit reached for this campaign")
                today_total += points

            submission_total += points

            activity_mat = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == activity_material_id)
                .first()
            )
            linked_material_id = activity_mat.material_id if activity_mat else None
            main_material_id = category_id = None
            if linked_material_id:
                mat = self.db.query(Material).filter(Material.id == linked_material_id).first()
                if mat:
                    main_material_id = mat.main_material_id
                    category_id = mat.category_id
            # `unit` is the measurement unit ('kg' / 'times'), NOT the material name —
            # rank + gamification logic key off this string via _is_weight_unit().
            unit = ("kg" if activity_mat.type == "material" else "times") if activity_mat else None
            prepared.append({
                "activity_material_id": activity_material_id,
                "value": value,
                "points": points,
                "unit": unit,
                "activity_mat": activity_mat,
                "material_id": linked_material_id,
                "main_material_id": main_material_id,
                "category_id": category_id,
            })

        return {
            "campaign": campaign,
            "setup": setup,
            "droppoint": droppoint,
            "is_new_member": membership is None,
            "items": prepared,
        }

    def record_creator_id(self, organization_id: int, droppoint, preferred: Optional[int] = None) -> Optional[int]:
        """transaction_records.created_by_id is a NOT NULL FK to user_locations: the admin
        who added the claim, else the droppoint's location, else the organisation owner."""
        if preferred:
            return preferred
        if droppoint is not None and droppoint.user_location_id:
            return droppoint.user_location_id
        owner = self.db.query(Organization.owner_id).filter(Organization.id == organization_id).scalar()
        return owner

    def create_waste_transaction(
        self,
        campaign,
        droppoint,
        prepared_items: list[dict],
        claimed_at: datetime,
        status: TransactionStatus,
        image_ids: list[int] | None,
        notes: str,
        created_by_id: Optional[int],
        transaction_created_by_id: Optional[int] = None,
    ) -> tuple[Optional[int], dict]:
        """Transaction + one record per material-linked item. Returns (transaction_id,
        {item_index: record_id}); (None, {}) when no item resolves to a material."""
        linked = [(i, it) for i, it in enumerate(prepared_items) if it["main_material_id"] and it["category_id"]]
        if not linked:
            return None, {}
        origin_id = droppoint.user_location_id if droppoint and droppoint.user_location_id else None
        record_status = "completed" if status == TransactionStatus.completed else status.value
        total_weight = sum((it["value"] for _i, it in linked), Decimal("0"))
        transaction = Transaction(
            transaction_method="reward",
            status=status,
            organization_id=campaign.organization_id,
            origin_id=origin_id,
            transaction_date=claimed_at,
            weight_kg=total_weight,
            images=image_ids or [],
            notes=notes,
            created_by_id=transaction_created_by_id,   # None for reward claims → "ระบบรางวัล"
        )
        self.db.add(transaction)
        self.db.flush()

        record_by_item = {}
        record_ids = []
        for i, it in linked:
            tx_record = TransactionRecord(
                status=record_status,
                created_transaction_id=transaction.id,
                transaction_type="rewards",
                material_id=it["material_id"],
                main_material_id=it["main_material_id"],
                category_id=it["category_id"],
                origin_quantity=it["value"],
                origin_weight_kg=it["value"],
                unit=it["activity_mat"].name if it["activity_mat"] else "kg",
                created_by_id=created_by_id,
                transaction_date=claimed_at,
                completed_date=claimed_at if status == TransactionStatus.completed else None,
                images=image_ids or [],
            )
            self.db.add(tx_record)
            self.db.flush()
            record_ids.append(tx_record.id)
            record_by_item[i] = tx_record.id
        transaction.transaction_records = record_ids
        self.db.flush()
        return transaction.id, record_by_item

    # ------------------------------------------------------------------
    # Claim (staff / admin)
    # ------------------------------------------------------------------
    def claim_points(
        self,
        staff_org_user_id: Optional[int],
        reward_user_id: int,
        campaign_id: int,
        items: list[dict],
        droppoint_id: Optional[int],
        image_ids: list[int] | None = None,
        source: str = "staff",
        created_by_user_location_id: Optional[int] = None,
        note: Optional[str] = None,
    ) -> dict:
        """
        Claim points for a user.
        items = [{"activity_material_id": int, "value": float}, ...]
        Also creates a real Transaction + TransactionRecords when material is linked.
        """
        prep = self.prepare_claim(reward_user_id, campaign_id, items, droppoint_id)
        campaign, droppoint = prep["campaign"], prep["droppoint"]
        now = datetime.now(timezone.utc)

        origin_id = droppoint.user_location_id if droppoint and droppoint.user_location_id else None
        # On /waste-transactions every reward claim reads as "ระบบรางวัล", whoever recorded it;
        # an admin-added claim keeps the admin on the reward row (created_by_user_location_id).
        creator_id = self.record_creator_id(campaign.organization_id, droppoint)
        notes = (f"Reward claim (added by admin) - Campaign: {campaign.name}" if source == "admin"
                 else f"Reward claim - Campaign: {campaign.name}")
        if note:
            notes += f"\n{note}"
        transaction_id, record_by_item = self.create_waste_transaction(
            campaign, droppoint, prep["items"], now, TransactionStatus.completed, image_ids, notes, creator_id,
        )

        total_points = Decimal("0")
        total_weight = Decimal("0")
        items_claimed = []
        for i, it in enumerate(prep["items"]):
            txn = RewardPointTransaction(
                organization_id=campaign.organization_id,
                reward_user_id=reward_user_id,
                points=it["points"],
                reward_activity_materials_id=it["activity_material_id"],
                reward_campaign_id=campaign_id,
                value=it["value"],
                unit=it["unit"],
                claimed_date=now,
                staff_id=staff_org_user_id,
                droppoint_id=droppoint_id,
                reference_type="claim",
                image_ids=image_ids,
                source=source,
                created_by_user_location_id=created_by_user_location_id,
                transaction_id=transaction_id if i in record_by_item else None,
                transaction_record_id=record_by_item.get(i),
                note=note,
            )
            self.db.add(txn)
            self.db.flush()
            total_points += it["points"]
            total_weight += it["value"]
            items_claimed.append({
                "activity_material_id": it["activity_material_id"],
                "value": float(it["value"]),
                "points": float(it["points"]),
                "point_transaction_id": txn.id,
            })

        self.ensure_membership(reward_user_id, campaign.organization_id)

        # ── CRM: emit reward_claimed + points_earned (+ campaign_joined on first claim) ──
        # crm_events.user_location_id is FK → user_locations.id, so we must pass the
        # droppoint's location (origin_id), NOT staff_org_user_id which belongs to a
        # different table (organization_reward_users) — using the wrong id silently
        # passes emit_event() but blows up on COMMIT with a FK violation.
        try:
            from GEPPPlatform.services.admin.crm.crm_service import emit_event
            _props = {
                'campaign_id': campaign_id,
                'transaction_id': transaction_id,
                'total_points': float(total_points),
                'total_weight_kg': float(total_weight),
                'source': source,
            }
            emit_event(
                self.db, event_type='reward_claimed', event_category='reward',
                organization_id=campaign.organization_id,
                user_location_id=origin_id,
                properties=_props, event_source='server', commit=False,
            )
            emit_event(
                self.db, event_type='points_earned', event_category='reward',
                organization_id=campaign.organization_id,
                user_location_id=origin_id,
                properties=_props, event_source='server', commit=False,
            )
            if prep["is_new_member"]:
                emit_event(
                    self.db, event_type='campaign_joined', event_category='reward',
                    organization_id=campaign.organization_id,
                    user_location_id=origin_id,
                    properties={'campaign_id': campaign_id}, event_source='server', commit=False,
                )
        except Exception as _exc:
            import logging as _log
            _log.getLogger(__name__).warning("CRM emit_event non-fatal (claim): %s", _exc)

        return {
            "success": True,
            "total_points": float(total_points),
            "total_weight_kg": float(total_weight),
            "transaction_id": transaction_id,
            "items_claimed": items_claimed,
        }

    def ensure_membership(self, reward_user_id: int, organization_id: int) -> None:
        """Auto-register the user in the organization on their first claim.
        SAVEPOINT: a concurrent first-time claim may create the row first."""
        existing = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if existing:
            return
        nested = self.db.begin_nested()
        try:
            self.db.add(OrganizationRewardUser(
                reward_user_id=reward_user_id,
                organization_id=organization_id,
                role="user",
            ))
            self.db.flush()
            nested.commit()
        except Exception:
            nested.rollback()  # unique violation: another request created it first
