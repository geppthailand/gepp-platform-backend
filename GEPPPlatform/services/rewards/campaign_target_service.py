"""
Campaign Target Service - Per-material/activity goals for a campaign.

Two target shapes:
  1. main_material target — aggregates kg across all material-type ActivityMaterials
     in this campaign whose linked Material has the targeted main_material_id.
  2. activity_material target — points at a single RewardActivityMaterial:
       - if type='material' → unit='kg', progress = SUM(claim.value)
       - if type='activity' → unit='times', progress = COUNT(claim rows)

Selection scope (per user requirement):
  - For activity_material target: dropdown shows ONLY ActivityMaterials currently
    linked to this campaign via reward_campaign_claims (active, not deleted).
  - For main_material target: dropdown shows ONLY MainMaterials that have ≥1
    material-type ActivityMaterial linked to this campaign.

NOTE: `from __future__ import annotations` is required because we define a method
named `list()` inside the class — without lazy annotations, subsequent uses of
`list[dict]` in the same class body would resolve `list` to the method, not
the builtin type, causing `TypeError: 'function' object is not subscriptable`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardCampaign,
    RewardCampaignTarget,
    RewardCampaignClaim,
    RewardActivityMaterial,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.cores.references import Material, MainMaterial
from ...exceptions import NotFoundException, BadRequestException


class CampaignTargetService:
    def __init__(self, db: Session):
        self.db = db

    # ── Progress computation ──────────────────────────────────────────
    def _compute_current(self, campaign_id: int, target: RewardCampaignTarget) -> float:
        """Return current progress in the target's unit (kg or count)."""
        base_filters = [
            RewardPointTransaction.reward_campaign_id == campaign_id,
            RewardPointTransaction.reference_type == "claim",
            RewardPointTransaction.deleted_date.is_(None),
        ]

        if target.target_level == "main":
            # Sum claim weight across all material-type ActivityMaterials whose
            # Material has this main_material_id.
            return float(
                self.db.query(func.coalesce(func.sum(RewardPointTransaction.value), 0))
                .select_from(RewardPointTransaction)
                .join(
                    RewardActivityMaterial,
                    RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
                )
                .join(Material, Material.id == RewardActivityMaterial.material_id)
                .filter(
                    *base_filters,
                    RewardActivityMaterial.type == "material",
                    Material.main_material_id == target.main_material_id,
                )
                .scalar() or 0
            )

        # activity_material level
        am = (
            self.db.query(RewardActivityMaterial)
            .filter(RewardActivityMaterial.id == target.activity_material_id)
            .first()
        )
        if not am:
            return 0.0

        if am.type == "activity":
            # Count claim rows
            return float(
                self.db.query(func.count(RewardPointTransaction.id))
                .filter(
                    *base_filters,
                    RewardPointTransaction.reward_activity_materials_id == target.activity_material_id,
                )
                .scalar() or 0
            )

        # material type — sum kg
        return float(
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.value), 0))
            .filter(
                *base_filters,
                RewardPointTransaction.reward_activity_materials_id == target.activity_material_id,
            )
            .scalar() or 0
        )

    # ── Display name resolution ───────────────────────────────────────
    def _resolve_name(self, target: RewardCampaignTarget) -> str:
        if target.target_level == "main" and target.main_material_id:
            mm = self.db.query(MainMaterial).filter(MainMaterial.id == target.main_material_id).first()
            if mm:
                return mm.name_th or mm.name_en or f"MainMaterial #{target.main_material_id}"
            return f"MainMaterial #{target.main_material_id}"
        if target.target_level == "activity_material" and target.activity_material_id:
            am = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == target.activity_material_id)
                .first()
            )
            if am:
                return am.name or f"ActivityMaterial #{target.activity_material_id}"
            return f"ActivityMaterial #{target.activity_material_id}"
        return "—"

    def _resolve_kind(self, target: RewardCampaignTarget) -> str:
        """Return 'main' / 'material' / 'activity' for UI display."""
        if target.target_level == "main":
            return "main"
        if target.activity_material_id:
            am = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == target.activity_material_id)
                .first()
            )
            if am and am.type == "activity":
                return "activity"
        return "material"

    def _to_dict(self, item: RewardCampaignTarget, include_progress: bool = True) -> dict:
        d = {
            "id": item.id,
            "reward_campaign_id": item.reward_campaign_id,
            "target_level": item.target_level,
            "main_material_id": item.main_material_id,
            "activity_material_id": item.activity_material_id,
            "target_amount": float(item.target_amount or 0),
            "target_unit": item.target_unit,
            "name": self._resolve_name(item),
            "kind": self._resolve_kind(item),
        }
        if include_progress:
            d["current_amount"] = self._compute_current(item.reward_campaign_id, item)
        return d

    # ── CRUD ──────────────────────────────────────────────────────────
    def list(self, campaign_id: int) -> list[dict]:
        items = (
            self.db.query(RewardCampaignTarget)
            .filter(
                RewardCampaignTarget.reward_campaign_id == campaign_id,
                RewardCampaignTarget.deleted_date.is_(None),
            )
            .order_by(RewardCampaignTarget.id.asc())
            .all()
        )
        return [self._to_dict(i) for i in items]

    def create(self, data: dict) -> dict:
        campaign_id = data.get("reward_campaign_id")
        level = data.get("target_level")
        main_material_id = data.get("main_material_id")
        activity_material_id = data.get("activity_material_id")
        target_amount = data.get("target_amount")

        if not campaign_id or not level or target_amount is None:
            raise BadRequestException(
                "reward_campaign_id, target_level, and target_amount are required"
            )
        if level not in ("main", "activity_material"):
            raise BadRequestException("target_level must be 'main' or 'activity_material'")

        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == campaign_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise NotFoundException("Campaign not found")

        # Auto-derive unit + validate FK shape
        if level == "main":
            if not main_material_id or activity_material_id:
                raise BadRequestException(
                    "target_level='main' requires main_material_id and no activity_material_id"
                )
            target_unit = "kg"
            # Validate: at least one material-type ActivityMaterial in this campaign maps to this main
            count = (
                self.db.query(func.count(RewardActivityMaterial.id))
                .select_from(RewardActivityMaterial)
                .join(Material, Material.id == RewardActivityMaterial.material_id)
                .join(
                    RewardCampaignClaim,
                    RewardCampaignClaim.activity_material_id == RewardActivityMaterial.id,
                )
                .filter(
                    RewardCampaignClaim.campaign_id == campaign_id,
                    RewardCampaignClaim.deleted_date.is_(None),
                    RewardActivityMaterial.type == "material",
                    Material.main_material_id == main_material_id,
                )
                .scalar() or 0
            )
            if count == 0:
                raise BadRequestException(
                    "No material-type ActivityMaterial in this campaign maps to that main_material"
                )
        else:
            if not activity_material_id or main_material_id:
                raise BadRequestException(
                    "target_level='activity_material' requires activity_material_id and no main_material_id"
                )
            am = (
                self.db.query(RewardActivityMaterial)
                .filter(RewardActivityMaterial.id == activity_material_id)
                .first()
            )
            if not am:
                raise NotFoundException("ActivityMaterial not found")
            # Validate: this activity_material is linked to this campaign
            link = (
                self.db.query(RewardCampaignClaim)
                .filter(
                    RewardCampaignClaim.campaign_id == campaign_id,
                    RewardCampaignClaim.activity_material_id == activity_material_id,
                    RewardCampaignClaim.deleted_date.is_(None),
                )
                .first()
            )
            if not link:
                raise BadRequestException(
                    "ActivityMaterial is not linked to this campaign — add it via campaign claims first"
                )
            target_unit = "times" if am.type == "activity" else "kg"

        # If a soft-deleted target with same scope exists — restore it instead of creating duplicate
        existing_q = self.db.query(RewardCampaignTarget).filter(
            RewardCampaignTarget.reward_campaign_id == campaign_id,
            RewardCampaignTarget.target_level == level,
        )
        if level == "main":
            existing_q = existing_q.filter(RewardCampaignTarget.main_material_id == main_material_id)
        else:
            existing_q = existing_q.filter(RewardCampaignTarget.activity_material_id == activity_material_id)
        existing = existing_q.order_by(RewardCampaignTarget.id.desc()).first()

        if existing and existing.deleted_date is not None:
            existing.deleted_date = None
            existing.target_amount = target_amount
            existing.target_unit = target_unit
            self.db.flush()
            return self._to_dict(existing)
        if existing and existing.deleted_date is None:
            raise BadRequestException("Target already exists for this scope — edit instead of recreating")

        item = RewardCampaignTarget(
            reward_campaign_id=campaign_id,
            target_level=level,
            main_material_id=main_material_id,
            activity_material_id=activity_material_id,
            target_amount=target_amount,
            target_unit=target_unit,
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        item = (
            self.db.query(RewardCampaignTarget)
            .filter(
                RewardCampaignTarget.id == id,
                RewardCampaignTarget.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign target not found")

        # Only target_amount is freely editable; changing scope = delete + recreate
        if "target_amount" in data:
            item.target_amount = data["target_amount"]

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        item = (
            self.db.query(RewardCampaignTarget)
            .filter(
                RewardCampaignTarget.id == id,
                RewardCampaignTarget.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign target not found")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}

    # ── Selectors for UI dropdowns ─────────────────────────────────────
    def list_eligible_activity_materials(self, campaign_id: int) -> list[dict]:
        """Return ActivityMaterials currently linked to this campaign (via active claims)."""
        rows = (
            self.db.query(RewardActivityMaterial, RewardCampaignClaim)
            .join(
                RewardCampaignClaim,
                RewardCampaignClaim.activity_material_id == RewardActivityMaterial.id,
            )
            .filter(
                RewardCampaignClaim.campaign_id == campaign_id,
                RewardCampaignClaim.deleted_date.is_(None),
                RewardActivityMaterial.deleted_date.is_(None),
            )
            .all()
        )
        seen = set()
        result = []
        for am, _claim in rows:
            if am.id in seen:
                continue
            seen.add(am.id)
            result.append({
                "id": am.id,
                "name": am.name,
                "type": am.type,  # 'material' | 'activity'
                "unit": "times" if am.type == "activity" else "kg",
            })
        return result

    def list_eligible_main_materials(self, campaign_id: int) -> list[dict]:
        """Return MainMaterials that have ≥1 material-type ActivityMaterial linked to this campaign."""
        rows = (
            self.db.query(MainMaterial)
            .join(Material, Material.main_material_id == MainMaterial.id)
            .join(RewardActivityMaterial, RewardActivityMaterial.material_id == Material.id)
            .join(
                RewardCampaignClaim,
                RewardCampaignClaim.activity_material_id == RewardActivityMaterial.id,
            )
            .filter(
                RewardCampaignClaim.campaign_id == campaign_id,
                RewardCampaignClaim.deleted_date.is_(None),
                RewardActivityMaterial.deleted_date.is_(None),
                RewardActivityMaterial.type == "material",
            )
            .distinct()
            .all()
        )
        return [
            {"id": mm.id, "name": mm.name_th or mm.name_en or f"#{mm.id}"}
            for mm in rows
        ]

    # ── Hooks called from claim service ───────────────────────────────
    def soft_delete_targets_for_activity_material(
        self, campaign_id: int, activity_material_id: int
    ) -> int:
        """Soft-delete all active targets pointing at this ActivityMaterial in this campaign.
        Called when a claim (campaign-material link) is removed."""
        items = (
            self.db.query(RewardCampaignTarget)
            .filter(
                RewardCampaignTarget.reward_campaign_id == campaign_id,
                RewardCampaignTarget.activity_material_id == activity_material_id,
                RewardCampaignTarget.deleted_date.is_(None),
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for t in items:
            t.deleted_date = now
        self.db.flush()
        return len(items)

    def restore_targets_for_activity_material(
        self, campaign_id: int, activity_material_id: int
    ) -> int:
        """Restore (un-soft-delete) all targets that were tied to this ActivityMaterial.
        Called when a claim (campaign-material link) is re-added."""
        items = (
            self.db.query(RewardCampaignTarget)
            .filter(
                RewardCampaignTarget.reward_campaign_id == campaign_id,
                RewardCampaignTarget.activity_material_id == activity_material_id,
                RewardCampaignTarget.deleted_date.isnot(None),
            )
            .all()
        )
        for t in items:
            t.deleted_date = None
        self.db.flush()
        return len(items)
