"""
Rewards "Admin tools" — admin-only actions behind reward_setup.admin_tools_enabled:
  - attach a claim to a member directly (source='admin'), same rows as a staff claim;
  - set a member's claim mode in this organization ('staff' / 'non_staff');
  - approve / reject a member's self-submitted claim (kept in step with /waste-transactions);
  - transaction detail for the audit modal (with photo view URLs).
Every entry point refuses while the switch is off.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from ...exceptions import BadRequestException, NotFoundException
from ...models.rewards.claim_requests import RewardClaimRequest
from ...models.rewards.management import RewardActivityMaterial, RewardCampaign, RewardCampaignDroppoint
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import Droppoint, OrganizationRewardUser, RewardUser
from ...models.transactions.transaction_records import TransactionRecord
from ...models.transactions.transactions import Transaction
from ...models.users.user_location import UserLocation
from .claim_request_service import ClaimRequestService, admin_tools_enabled
from .claim_service import ClaimService

CLAIM_MODES = ("staff", "non_staff")


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


class AdminToolsService:
    def __init__(self, db: Session):
        self.db = db

    def _require_enabled(self, organization_id: int) -> None:
        if not admin_tools_enabled(self.db, organization_id):
            raise BadRequestException("Admin tools is turned off for this program")

    def _member(self, organization_id: int, member_id: int) -> OrganizationRewardUser:
        member = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.id == int(member_id),
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not member:
            raise NotFoundException("Member not found")
        return member

    # ------------------------------------------------------------------
    def attach_claim(self, organization_id: int, admin_user_id: int, data: dict) -> dict:
        """Admin records a claim for a member: the same reward row + waste transaction as a
        staff claim at a droppoint, marked source='admin' with the admin as creator."""
        self._require_enabled(organization_id)
        member = self._member(organization_id, data.get("member_id"))
        if not member.is_active:
            raise BadRequestException("Member account is deactivated")
        campaign_id = int(data.get("campaign_id") or 0)
        campaign = self.db.query(RewardCampaign).filter(
            RewardCampaign.id == campaign_id, RewardCampaign.organization_id == organization_id,
            RewardCampaign.deleted_date.is_(None)).first()
        if not campaign:
            raise NotFoundException("Campaign not found")
        linked = [r.droppoint_id for r in self.db.query(RewardCampaignDroppoint.droppoint_id).filter(
            RewardCampaignDroppoint.campaign_id == campaign_id,
            RewardCampaignDroppoint.deleted_date.is_(None)).all()]
        droppoint_id = data.get("droppoint_id")
        droppoint_id = int(droppoint_id) if droppoint_id else None
        if droppoint_id is None and len(linked) == 1:
            droppoint_id = linked[0]
        if droppoint_id is None and linked:
            raise BadRequestException("Choose the drop point where the waste was brought in")
        items = [{"activity_material_id": int(i.get("activity_material_id") or 0), "value": i.get("value")}
                 for i in (data.get("items") or [])]
        if not items:
            raise BadRequestException("Add at least one item")
        image_ids = [int(i) for i in (data.get("image_ids") or []) if str(i).isdigit()] or None
        note = (data.get("note") or "").strip() or None

        result = ClaimService(self.db).claim_points(
            staff_org_user_id=None,
            reward_user_id=member.reward_user_id,
            campaign_id=campaign_id,
            items=items,
            droppoint_id=droppoint_id,
            image_ids=image_ids,
            source="admin",
            created_by_user_location_id=int(admin_user_id) if admin_user_id else None,
            note=note,
        )
        self.db.commit()
        return result

    def set_claim_mode(self, organization_id: int, member_id: int, mode: str) -> dict:
        self._require_enabled(organization_id)
        if mode not in CLAIM_MODES:
            raise BadRequestException("claim_mode must be 'staff' or 'non_staff'")
        member = self._member(organization_id, member_id)
        member.claim_mode = mode
        self.db.commit()
        return {"id": member.id, "claim_mode": member.claim_mode}

    # ------------------------------------------------------------------
    def _request(self, organization_id: int, key: str) -> RewardClaimRequest:
        try:
            kind, raw_id = str(key).split("-", 1)
            req_id = int(raw_id)
        except (ValueError, AttributeError):
            raise BadRequestException("Invalid transaction key")
        if kind == "claim":
            # an approved self-claim is shown as its ledger row; review goes to its request
            row = self.db.query(RewardPointTransaction).filter(
                RewardPointTransaction.id == req_id, RewardPointTransaction.organization_id == organization_id).first()
            if not row or row.source != "self" or not row.reference_id:
                raise BadRequestException("Only member-submitted claims can be reviewed")
            req_id = row.reference_id
        elif kind != "request":
            raise BadRequestException("Only member-submitted claims can be reviewed")
        req = self.db.query(RewardClaimRequest).filter(
            RewardClaimRequest.id == req_id, RewardClaimRequest.organization_id == organization_id,
            RewardClaimRequest.deleted_date.is_(None)).first()
        if not req:
            raise NotFoundException("Claim request not found")
        return req

    def review(self, organization_id: int, reviewer_id: int, key: str, action: str,
               note: Optional[str] = None) -> dict:
        """Approve / reject a self-submitted claim. When it created a waste record, the
        decision goes through the same manual-audit path as /waste-transactions (audit
        notes, transaction roll-up); the flush hook then applies it back to the request."""
        self._require_enabled(organization_id)
        if action not in ("approve", "reject"):
            raise BadRequestException("action must be 'approve' or 'reject'")
        req = self._request(organization_id, key)
        target = "approved" if action == "approve" else "rejected"
        svc = ClaimRequestService(self.db)
        # One record for a material item; one per material for a packaging item (shared by the
        # other packaging items of the same submission — they are decided together).
        record_ids = [req.transaction_record_id] if req.transaction_record_id else sorted({
            int(c["record_id"]) for c in (req.components or []) if c.get("record_id")
        })
        if record_ids:
            from ..cores.transaction_audit.manual_audit_service import ManualAuditService
            audit = ManualAuditService()
            for record_id in record_ids:
                if action == "approve":
                    res = audit.approve_transaction_record(self.db, record_id, int(reviewer_id), notes=note)
                else:
                    res = audit.reject_transaction_record(self.db, record_id, int(reviewer_id),
                                                          rejection_reason=note)
                if not res.get("success"):
                    raise BadRequestException(res.get("error") or "Could not update the waste transaction")
            self.db.refresh(req)
        # Covers claims with no waste record, and makes the outcome explicit either way.
        svc.apply_status(req, target, reviewer_id=int(reviewer_id), note=note)
        req.reviewed_by_id = int(reviewer_id)
        if note is not None:
            req.review_note = note
        self.db.commit()
        return {"key": f"request-{req.id}", "status": req.status,
                "reward_point_transaction_id": req.reward_point_transaction_id}

    # ------------------------------------------------------------------
    def transaction_detail(self, organization_id: int, current_user_id: int, key: str) -> dict:
        try:
            kind, raw_id = str(key).split("-", 1)
            row_id = int(raw_id)
        except (ValueError, AttributeError):
            raise BadRequestException("Invalid transaction key")

        req: Optional[RewardClaimRequest] = None
        ptx: Optional[RewardPointTransaction] = None
        if kind == "request":
            req = self.db.query(RewardClaimRequest).filter(
                RewardClaimRequest.id == row_id, RewardClaimRequest.organization_id == organization_id).first()
            if not req:
                raise NotFoundException("Transaction not found")
            if req.reward_point_transaction_id:
                ptx = self.db.query(RewardPointTransaction).filter(
                    RewardPointTransaction.id == req.reward_point_transaction_id).first()
        elif kind == "claim":
            ptx = self.db.query(RewardPointTransaction).filter(
                RewardPointTransaction.id == row_id, RewardPointTransaction.organization_id == organization_id).first()
            if not ptx:
                raise NotFoundException("Transaction not found")
            if ptx.source == "self" and ptx.reference_id:
                req = self.db.query(RewardClaimRequest).filter(RewardClaimRequest.id == ptx.reference_id).first()
        else:
            raise BadRequestException("Unsupported transaction type")
        if req is not None:
            ClaimRequestService(self.db).reconcile([req])

        base = req or ptx
        campaign = self.db.query(RewardCampaign).filter(RewardCampaign.id == base.reward_campaign_id).first()
        activity = self.db.query(RewardActivityMaterial).filter(
            RewardActivityMaterial.id == base.reward_activity_materials_id).first()
        user = self.db.query(RewardUser).filter(RewardUser.id == base.reward_user_id).first()
        member = self.db.query(OrganizationRewardUser).filter(
            OrganizationRewardUser.reward_user_id == base.reward_user_id,
            OrganizationRewardUser.organization_id == organization_id,
            OrganizationRewardUser.deleted_date.is_(None)).first()
        dp = self.db.query(Droppoint).filter(Droppoint.id == base.droppoint_id).first() if base.droppoint_id else None

        staff_name = None
        if ptx is not None and ptx.staff_id:
            staff = (self.db.query(RewardUser).join(OrganizationRewardUser,
                                                    OrganizationRewardUser.reward_user_id == RewardUser.id)
                     .filter(OrganizationRewardUser.id == ptx.staff_id).first())
            staff_name = (staff.display_name or staff.line_display_name) if staff else None
        admin_name = self._user_name(ptx.created_by_user_location_id if ptx is not None else None)
        reviewer_name = self._user_name(req.reviewed_by_id if req is not None else None)

        transaction_id = (req.transaction_id if req is not None else None) or (ptx.transaction_id if ptx else None)
        record_id = (req.transaction_record_id if req is not None else None) or (ptx.transaction_record_id if ptx else None)
        waste = None
        if transaction_id:
            tx = self.db.query(Transaction).filter(Transaction.id == transaction_id).first()
            rec = self.db.query(TransactionRecord).filter(TransactionRecord.id == record_id).first() if record_id else None
            if tx is not None:
                waste = {
                    "transaction_id": tx.id,
                    "transaction_status": tx.status.value if hasattr(tx.status, "value") else str(tx.status),
                    "record_id": rec.id if rec else None,
                    "record_status": rec.status if rec else None,
                }

        # [PACKAGING] pieces + per-material split (snapshot on the request / ledger row)
        quantity = (req.quantity if req is not None else None)
        if quantity is None and ptx is not None:
            quantity = ptx.quantity
        quantity_unit = (req.quantity_unit if req is not None else None) or (ptx.quantity_unit if ptx else None)
        components = self._components_detail(req, ptx)
        packaging = None
        if activity is not None and activity.type == "packaging" and activity.packaging_id:
            from .packaging_conversion import packaging_label
            packaging = {"id": activity.packaging_id, "label": packaging_label(self.db, activity.packaging_id)}

        image_ids = list((req.image_ids if req is not None else None) or (ptx.image_ids if ptx else None) or [])
        images = self._image_urls(image_ids, organization_id, current_user_id)
        source = "self" if req is not None else (ptx.source or "staff")
        status = req.status if req is not None else "completed"
        return {
            "key": key,
            "type": "claim",
            "source": source,
            "status": status,
            "member": {
                "id": member.id if member else None,
                "reward_user_id": base.reward_user_id,
                "name": (user.display_name or user.line_display_name) if user else None,
                "phone": user.phone_number if user else None,
                "picture_url": user.line_picture_url if user else None,
                "claim_mode": (member.claim_mode if member else None) or "staff",
            },
            "campaign": {"id": campaign.id, "name": campaign.name} if campaign else None,
            "item": {"id": activity.id, "name": activity.name, "type": activity.type} if activity else None,
            "value": float(base.value or 0),
            "unit": base.unit,
            "quantity": float(quantity) if quantity is not None else None,
            "quantity_unit": quantity_unit,
            "components": components,
            "packaging": packaging,
            "points": float(ptx.points) if ptx is not None and ptx.deleted_date is None else 0.0,
            "requested_points": float(req.requested_points) if req is not None else (float(ptx.points) if ptx else 0.0),
            "droppoint": {"id": dp.id, "name": dp.name} if dp else None,
            "datetime": _iso(req.submitted_date if req is not None else (ptx.claimed_date or ptx.created_date)),
            "staff_name": staff_name,
            "added_by_admin": admin_name,
            "reviewed_by": reviewer_name,
            "reviewed_date": _iso(req.reviewed_date) if req is not None else None,
            "review_note": req.review_note if req is not None else None,
            "note": (req.note if req is not None else None) or (ptx.note if ptx else None),
            "images": images,
            "waste": waste,
            "can_review": req is not None,
        }

    def _components_detail(self, req, ptx) -> list[dict]:
        """[PACKAGING] [{material_id, name_th, name_en, weight_kg, record_id, record_status}]."""
        from ...models.rewards.points import RewardPointTransactionComponent
        from ...models.cores.references import Material
        raw: list[dict] = []
        if ptx is not None:
            for c in self.db.query(RewardPointTransactionComponent).filter(
                RewardPointTransactionComponent.reward_point_transaction_id == ptx.id,
                RewardPointTransactionComponent.deleted_date.is_(None),
            ).all():
                raw.append({"material_id": int(c.material_id), "weight_kg": float(c.weight_kg),
                            "record_id": c.transaction_record_id})
        if not raw and req is not None and req.components:
            raw = [{"material_id": int(c["material_id"]), "weight_kg": float(c["weight_kg"]),
                    "record_id": c.get("record_id")} for c in req.components]
        if not raw:
            return []
        mats = {m.id: m for m in self.db.query(Material).filter(Material.id.in_({c["material_id"] for c in raw})).all()}
        rec_ids = {int(c["record_id"]) for c in raw if c.get("record_id")}
        recs = {r.id: r for r in self.db.query(TransactionRecord).filter(TransactionRecord.id.in_(rec_ids)).all()} if rec_ids else {}
        out = []
        for c in raw:
            m = mats.get(c["material_id"])
            r = recs.get(int(c["record_id"])) if c.get("record_id") else None
            out.append({**c, "name_th": m.name_th if m else None, "name_en": m.name_en if m else None,
                        "record_status": r.status if r is not None else None})
        return out

    def _user_name(self, user_location_id: Optional[int]) -> Optional[str]:
        if not user_location_id:
            return None
        u = self.db.query(UserLocation).filter(UserLocation.id == user_location_id).first()
        if not u:
            return None
        full = " ".join(x for x in (u.first_name, u.last_name) if x)
        return u.display_name or full or u.email

    def _image_urls(self, file_ids: list, organization_id: int, user_id: int) -> list[dict[str, Any]]:
        ids = [int(i) for i in file_ids if str(i).isdigit()]
        if not ids:
            return []
        try:
            from ..cores.transactions.presigned_url_service import TransactionPresignedUrlService
            res = TransactionPresignedUrlService().get_transaction_file_view_presigned_urls_by_ids(
                file_ids=ids, db=self.db, organization_id=organization_id, user_id=int(user_id or 0))
            urls = res.get("presigned_urls") or {}
            out = []
            for fid in ids:
                entry = urls.get(fid) or urls.get(str(fid)) or {}
                out.append({"file_id": fid, "url": entry.get("view_url")})
            return out
        except Exception:
            return [{"file_id": fid, "url": None} for fid in ids]
