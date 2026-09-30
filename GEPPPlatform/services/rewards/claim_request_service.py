"""
Claim requests — a non-staff member's own claims, reviewed by an admin (Rewards "Admin tools").

Lifecycle of one request item:
    submitted (LIFF) ── pending ──► approved ──► rejected (and back, any direction)
The waste transaction record created with the request carries the same status, and a
change on either side is applied to the other:
  - rewards → waste: AdminToolsService.review() goes through ManualAuditService, so the
    waste side keeps its own audit notes and transaction roll-up;
  - waste → rewards: the `before_flush` listener in models/rewards/claim_requests.py calls
    `sync_from_waste`, and list/detail reads call `reconcile` as a safety net for the
    few raw-SQL status updates the listener can't see.
Points: a reward_point_transactions row exists only while a request is approved (created
on approval, soft-deleted on rejection), so balances, GHG, targets and leaderboards never
count pending or rejected claims and none of their queries needed a status filter.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from ...exceptions import BadRequestException, NotFoundException
from ...models.rewards.claim_requests import RewardClaimRequest
from ...models.rewards.management import (
    RewardActivityMaterial, RewardCampaign, RewardCampaignClaim, RewardCampaignDroppoint, RewardSetup,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import Droppoint, OrganizationRewardUser
from ...models.subscriptions.organizations import Organization
from ...models.transactions.transaction_records import TransactionRecord
from ...models.transactions.transactions import Transaction, TransactionStatus
from .claim_service import ClaimService

STATUSES = ("pending", "approved", "rejected")
MAX_IMAGES = 3


def admin_tools_enabled(db: Session, organization_id: int) -> bool:
    val = (
        db.query(RewardSetup.admin_tools_enabled)
        .filter(RewardSetup.organization_id == organization_id, RewardSetup.deleted_date.is_(None))
        .scalar()
    )
    return bool(val)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


class ClaimRequestService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------
    def _self_claim_membership(self, reward_user_id: int, organization_id: int) -> OrganizationRewardUser:
        """The caller may self-submit in this org only while Admin tools is on AND the
        org has set them to 'non_staff'. Anything else is refused, not silently allowed."""
        if not admin_tools_enabled(self.db, organization_id):
            raise BadRequestException("Self-submitted claims are not enabled for this organization")
        membership = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if membership is None or not membership.is_active:
            raise BadRequestException("You are not an active member of this organization")
        if (membership.claim_mode or "staff") != "non_staff":
            raise BadRequestException("This organization records your claims through its staff")
        return membership

    def self_claim_organizations(self, reward_user_id: int) -> list[dict]:
        rows = (
            self.db.query(OrganizationRewardUser, Organization, RewardSetup)
            .join(Organization, Organization.id == OrganizationRewardUser.organization_id)
            .join(RewardSetup, (RewardSetup.organization_id == OrganizationRewardUser.organization_id)
                  & RewardSetup.deleted_date.is_(None))
            .filter(
                OrganizationRewardUser.reward_user_id == reward_user_id,
                OrganizationRewardUser.deleted_date.is_(None),
                OrganizationRewardUser.is_active.is_(True),
                OrganizationRewardUser.claim_mode == "non_staff",
                RewardSetup.admin_tools_enabled.is_(True),
            )
            .order_by(Organization.name)
            .all()
        )
        return [{
            "organization_id": org.id,
            "organization_name": org.name,
            "program_name": setup.program_name_local or setup.program_name,
        } for _m, org, setup in rows]

    def self_claim_options(self, reward_user_id: int, organization_id: int) -> dict:
        """Campaigns the member can submit to right now, each with its droppoints and items."""
        self._self_claim_membership(reward_user_id, organization_id)
        now = datetime.now(timezone.utc)
        campaigns = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.status == "active",
                RewardCampaign.deleted_date.is_(None),
                RewardCampaign.start_date <= now,
                or_(RewardCampaign.end_date.is_(None), RewardCampaign.end_date >= now),
            )
            .order_by(RewardCampaign.end_date.asc().nullslast(), RewardCampaign.name)
            .all()
        )
        ids = [c.id for c in campaigns]
        items_by_campaign: dict[int, list] = {i: [] for i in ids}
        if ids:
            rows = (
                self.db.query(RewardCampaignClaim, RewardActivityMaterial)
                .join(RewardActivityMaterial, RewardActivityMaterial.id == RewardCampaignClaim.activity_material_id)
                .filter(
                    RewardCampaignClaim.campaign_id.in_(ids),
                    RewardCampaignClaim.deleted_date.is_(None),
                    RewardActivityMaterial.deleted_date.is_(None),
                )
                .order_by(RewardActivityMaterial.type, RewardActivityMaterial.name)
                .all()
            )
            for rule, am in rows:
                items_by_campaign[rule.campaign_id].append({
                    "activity_material_id": am.id,
                    "name": am.name,
                    "description": am.description,
                    "type": am.type,
                    "unit": "kg" if am.type == "material" else "times",
                    "points": float(rule.points),
                    "image_id": am.image_id,
                })
        dps_by_campaign: dict[int, list] = {i: [] for i in ids}
        if ids:
            for link, dp in (
                self.db.query(RewardCampaignDroppoint, Droppoint)
                .join(Droppoint, Droppoint.id == RewardCampaignDroppoint.droppoint_id)
                .filter(
                    RewardCampaignDroppoint.campaign_id.in_(ids),
                    RewardCampaignDroppoint.deleted_date.is_(None),
                    Droppoint.deleted_date.is_(None),
                )
                .order_by(Droppoint.name)
                .all()
            ):
                dps_by_campaign[link.campaign_id].append({"id": dp.id, "name": dp.name})
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        return {
            "organization": {"id": organization_id, "name": org.name if org else None},
            "campaigns": [{
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "image_id": c.image_id,
                "start_date": _iso(c.start_date),
                "end_date": _iso(c.end_date),
                "droppoints": dps_by_campaign.get(c.id, []),
                "items": items_by_campaign.get(c.id, []),
            } for c in campaigns if items_by_campaign.get(c.id)],
        }

    # ------------------------------------------------------------------
    # Submit (LIFF)
    # ------------------------------------------------------------------
    def submit(self, reward_user_id: int, organization_id: int, campaign_id: int, items: list[dict],
               droppoint_id: Optional[int] = None, image_ids: Optional[list] = None,
               note: Optional[str] = None) -> dict:
        membership = self._self_claim_membership(reward_user_id, organization_id)
        if not items:
            raise BadRequestException("Choose at least one item")
        image_ids = [int(i) for i in (image_ids or []) if str(i).isdigit()][:MAX_IMAGES]

        campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == campaign_id).first()
        if campaign is None or campaign.organization_id != organization_id:
            raise NotFoundException("Campaign not found in this organization")
        linked_dps = [
            r.droppoint_id for r in self.db.query(RewardCampaignDroppoint.droppoint_id).filter(
                RewardCampaignDroppoint.campaign_id == campaign_id,
                RewardCampaignDroppoint.deleted_date.is_(None),
            ).all()
        ]
        if droppoint_id is None and len(linked_dps) == 1:
            droppoint_id = linked_dps[0]
        if droppoint_id is None and len(linked_dps) > 1:
            raise BadRequestException("Choose a drop point for this campaign")

        claim_svc = ClaimService(self.db)
        prep = claim_svc.prepare_claim(reward_user_id, campaign_id, items, droppoint_id, require_started=True)
        now = datetime.now(timezone.utc)
        creator_id = claim_svc.record_creator_id(organization_id, prep["droppoint"])
        notes = f"Reward claim (submitted by member) - Campaign: {campaign.name}"
        if note:
            notes += f"\n{note}"
        transaction_id, record_by_item = claim_svc.create_waste_transaction(
            campaign, prep["droppoint"], prep["items"], now, TransactionStatus.pending, image_ids, notes, creator_id,
        )

        uid = str(uuid.uuid4())
        out_items = []
        for i, it in enumerate(prep["items"]):
            req = RewardClaimRequest(
                organization_id=organization_id,
                reward_user_id=reward_user_id,
                organization_reward_user_id=membership.id,
                reward_campaign_id=campaign_id,
                reward_activity_materials_id=it["activity_material_id"],
                droppoint_id=droppoint_id,
                submission_uid=uid,
                value=it["value"],
                unit=it["unit"],
                requested_points=it["points"],
                status="pending",
                image_ids=image_ids or None,
                note=note,
                transaction_id=transaction_id if i in record_by_item else None,
                transaction_record_id=record_by_item.get(i),
                submitted_date=now,
            )
            self.db.add(req)
            self.db.flush()
            out_items.append(self._serialize(req, activity=it["activity_mat"]))
        self.db.commit()
        return {
            "success": True,
            "submission_uid": uid,
            "status": "pending",
            "transaction_id": transaction_id,
            "total_requested_points": float(sum((it["points"] for it in prep["items"]), Decimal("0"))),
            "items": out_items,
        }

    def history(self, reward_user_id: int, organization_id: Optional[int] = None, limit: int = 30) -> list[dict]:
        q = self.db.query(RewardClaimRequest).filter(
            RewardClaimRequest.reward_user_id == reward_user_id,
            RewardClaimRequest.deleted_date.is_(None),
        )
        if organization_id:
            q = q.filter(RewardClaimRequest.organization_id == organization_id)
        reqs = q.order_by(RewardClaimRequest.submitted_date.desc(), RewardClaimRequest.id.desc()).limit(limit).all()
        self.reconcile(reqs)
        acts = self._activities({r.reward_activity_materials_id for r in reqs})
        camps = self._campaigns({r.reward_campaign_id for r in reqs})
        return [self._serialize(r, activity=acts.get(r.reward_activity_materials_id),
                                campaign=camps.get(r.reward_campaign_id)) for r in reqs]

    # ------------------------------------------------------------------
    # Status machine
    # ------------------------------------------------------------------
    def apply_status(self, req: RewardClaimRequest, status: str, reviewer_id: Optional[int] = None,
                     note: Optional[str] = None) -> bool:
        """Move a request to `status` and keep its reward row in step. Idempotent;
        returns True when anything changed."""
        if status not in STATUSES:
            raise BadRequestException(f"Unknown status '{status}'")
        changed = req.status != status
        now = datetime.now(timezone.utc)
        reward_row = None
        if req.reward_point_transaction_id:
            reward_row = self.db.query(RewardPointTransaction).filter(
                RewardPointTransaction.id == req.reward_point_transaction_id).first()

        if status == "approved":
            if reward_row is None:
                # Id from the sequence instead of a flush: this also runs inside the
                # before_flush hook, where flushing again is not allowed.
                new_id = self.db.execute(text("SELECT nextval('reward_point_transactions_id_seq')")).scalar()
                reward_row = RewardPointTransaction(
                    id=new_id,
                    organization_id=req.organization_id,
                    reward_user_id=req.reward_user_id,
                    points=req.requested_points,
                    reward_activity_materials_id=req.reward_activity_materials_id,
                    reward_campaign_id=req.reward_campaign_id,
                    value=req.value,
                    unit=req.unit,
                    claimed_date=req.submitted_date,   # counts in the period it was brought in
                    staff_id=None,
                    droppoint_id=req.droppoint_id,
                    reference_type="claim",
                    reference_id=req.id,
                    image_ids=req.image_ids,
                    source="self",
                    transaction_id=req.transaction_id,
                    transaction_record_id=req.transaction_record_id,
                    note=req.note,
                )
                self.db.add(reward_row)
                req.reward_point_transaction_id = new_id
                changed = True
            elif reward_row.deleted_date is not None:
                reward_row.deleted_date = None
                reward_row.is_active = True
                changed = True
        elif reward_row is not None and reward_row.deleted_date is None:
            reward_row.deleted_date = now          # points leave every balance/aggregate
            changed = True

        if changed:
            req.status = status
            req.reviewed_by_id = reviewer_id if status != "pending" else None
            req.reviewed_date = now if status != "pending" else None
            if note is not None:
                req.review_note = note
        return changed

    @staticmethod
    def _map_waste_status(record: Optional[TransactionRecord], tx: Optional[Transaction],
                          siblings_pending: bool) -> Optional[str]:
        """The request status implied by its waste record (None = no opinion)."""
        if tx is None and record is None:
            return None
        if (record is not None and record.deleted_date is not None) or (tx is not None and tx.deleted_date is not None):
            return "rejected"
        rs = (record.status or "").lower() if record is not None else ""
        if rs in ("approved", "completed"):
            return "approved"
        if rs == "rejected":
            return "rejected"
        ts = tx.status.value if tx is not None and hasattr(tx.status, "value") else str(getattr(tx, "status", "") or "")
        # Record still pending: follow the transaction only when it was decided as a whole
        # (no sibling record decided on its own), else a sibling's rejection would drag
        # this item along with it.
        if siblings_pending:
            if ts in ("approved", "completed"):
                return "approved"
            if ts in ("rejected", "cancelled"):
                return "rejected"
        return "pending"

    def _waste_status_for(self, reqs: list[RewardClaimRequest]) -> dict[int, Optional[str]]:
        tx_ids = {r.transaction_id for r in reqs if r.transaction_id}
        if not tx_ids:
            return {}
        txs = {t.id: t for t in self.db.query(Transaction).filter(Transaction.id.in_(tx_ids)).all()}
        recs = self.db.query(TransactionRecord).filter(TransactionRecord.created_transaction_id.in_(tx_ids)).all()
        by_id = {r.id: r for r in recs}
        by_tx: dict[int, list] = {}
        for r in recs:
            if r.deleted_date is None:
                by_tx.setdefault(r.created_transaction_id, []).append(r)
        out = {}
        for req in reqs:
            if not req.transaction_id:
                continue
            siblings = by_tx.get(req.transaction_id, [])
            siblings_pending = all((s.status or "pending") == "pending" for s in siblings)
            out[req.id] = self._map_waste_status(by_id.get(req.transaction_record_id), txs.get(req.transaction_id),
                                                 siblings_pending)
        return out

    def sync_from_waste(self, record_ids: Iterable[int] = (), transaction_ids: Iterable[int] = ()) -> int:
        record_ids, transaction_ids = set(record_ids or ()), set(transaction_ids or ())
        if not record_ids and not transaction_ids:
            return 0
        conds = []
        if record_ids:
            conds.append(RewardClaimRequest.transaction_record_id.in_(record_ids))
        if transaction_ids:
            conds.append(RewardClaimRequest.transaction_id.in_(transaction_ids))
        reqs = self.db.query(RewardClaimRequest).filter(or_(*conds), RewardClaimRequest.deleted_date.is_(None)).all()
        return self._apply_waste(reqs)

    def reconcile(self, reqs: list[RewardClaimRequest]) -> int:
        """Read-time safety net: catch up with waste-side changes the flush hook missed."""
        linked = [r for r in reqs if r.transaction_id]
        if not linked:
            return 0
        n = self._apply_waste(linked)
        if n:
            self.db.flush()
        return n

    def _apply_waste(self, reqs: list[RewardClaimRequest]) -> int:
        n = 0
        for req_id, status in self._waste_status_for(reqs).items():
            req = next(r for r in reqs if r.id == req_id)
            if status and status != req.status:
                n += int(self.apply_status(req, status))
        return n

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def _activities(self, ids: set) -> dict:
        ids = {i for i in ids if i}
        return {a.id: a for a in self.db.query(RewardActivityMaterial).filter(RewardActivityMaterial.id.in_(ids)).all()} if ids else {}

    def _campaigns(self, ids: set) -> dict:
        ids = {i for i in ids if i}
        return {c.id: c for c in self.db.query(RewardCampaign).filter(RewardCampaign.id.in_(ids)).all()} if ids else {}

    @staticmethod
    def _serialize(req: RewardClaimRequest, activity=None, campaign=None) -> dict[str, Any]:
        return {
            "id": req.id,
            "key": f"request-{req.id}",
            "submission_uid": req.submission_uid,
            "organization_id": req.organization_id,
            "campaign_id": req.reward_campaign_id,
            "campaign_name": campaign.name if campaign else None,
            "activity_material_id": req.reward_activity_materials_id,
            "item_name": activity.name if activity else None,
            "item_type": activity.type if activity else None,
            "value": float(req.value or 0),
            "unit": req.unit,
            "requested_points": float(req.requested_points or 0),
            "status": req.status,
            "image_count": len(req.image_ids or []),
            "submitted_date": _iso(req.submitted_date),
            "reviewed_date": _iso(req.reviewed_date),
            "review_note": req.review_note,
            "transaction_id": req.transaction_id,
        }
