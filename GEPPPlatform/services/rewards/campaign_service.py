"""
Campaign Service - Time-bound campaigns for earning and redeeming rewards.

Lifecycle: draft → active ↔ paused → (archived)
  - 'ended' is a COMPUTED state (when status='active' and end_date < now())
  - 'archived' is set manually, only from ended

NOTE: `from __future__ import annotations` is required — we define a method
named `list()` inside the class, so later `list[dict]` annotations must be
lazy-evaluated to avoid shadowing the builtin type.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...models.rewards.management import (
    RewardCampaign,
    RewardCampaignClaim,
    RewardCampaignCatalog,
    RewardCampaignDroppoint,
    RewardCampaignTarget,
    RewardActivityType,
    RewardCampaignActivityType,
)
from ...exceptions import NotFoundException, BadRequestException


VALID_STATUSES = {"draft", "active", "paused", "archived"}
VALID_METRIC_TYPES = {"material", "activity"}


def _parse_dt(value):
    """Convert ISO-format string to datetime, pass through datetime objects."""
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def compute_effective_status(item: RewardCampaign) -> str:
    """Return the effective status — 'ended' if end_date has passed, else raw status."""
    if item.status == "active" and item.end_date is not None:
        now = datetime.now(timezone.utc)
        end = item.end_date
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end < now:
            return "ended"
    return item.status


def assert_editable(item: RewardCampaign, breaking: bool = True):
    """Raise if a breaking mutation is attempted on an active (non-ended) campaign.

    Safe (additive) ops should pass breaking=False.
    """
    if not breaking:
        return
    effective = compute_effective_status(item)
    if effective == "active":
        raise BadRequestException(
            "Cannot perform this edit while the campaign is active. Pause the campaign first."
        )


class CampaignService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _safe_iso(val):
        if val is None:
            return None
        return val.isoformat() if hasattr(val, 'isoformat') else str(val)

    def _to_dict(self, item: RewardCampaign) -> dict:
        # Phase 2: load activity_type ids if metric_type='activity'
        activity_type_ids: list[int] = []
        if getattr(item, "metric_type", "material") == "activity":
            joins = (
                self.db.query(RewardCampaignActivityType.activity_type_id)
                .filter(
                    RewardCampaignActivityType.campaign_id == item.id,
                    RewardCampaignActivityType.deleted_date.is_(None),
                )
                .all()
            )
            activity_type_ids = [row.activity_type_id for row in joins]

        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "name": item.name,
            "description": item.description,
            "image_id": item.image_id,
            "start_date": self._safe_iso(item.start_date),
            "end_date": self._safe_iso(item.end_date),
            "status": item.status,
            "effective_status": compute_effective_status(item),
            "points_per_transaction_limit": item.points_per_transaction_limit,
            "points_per_day_limit": item.points_per_day_limit,
            "target_participants": item.target_participants,
            "budget_baht": float(item.budget_baht) if item.budget_baht is not None else None,
            "metric_type": getattr(item, "metric_type", "material"),
            "activity_type_ids": activity_type_ids,
            "created_date": self._safe_iso(item.created_date),
            "updated_date": self._safe_iso(item.updated_date),
        }

    def _get_or_404(self, id: int) -> RewardCampaign:
        item = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign not found")
        return item

    def list(self, organization_id: int) -> list[dict]:
        """List campaigns with lightweight progress metrics for the list page.

        Each row includes:
          - participants_count (distinct users who claimed in this campaign)
          - overall_progress_percent (kg-only weighted; returns None if no kg targets)
        """
        from sqlalchemy import func, distinct
        from ...models.rewards.points import RewardPointTransaction

        items = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .order_by(RewardCampaign.id.desc())
            .all()
        )

        result = []
        for c in items:
            d = self._to_dict(c)
            # Participants count
            d["participants_count"] = int(
                self.db.query(func.count(distinct(RewardPointTransaction.reward_user_id)))
                .filter(
                    RewardPointTransaction.reward_campaign_id == c.id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
                .scalar() or 0
            )
            # Aggregate kg targets + current (skip times targets for list view simplicity)
            targets = (
                self.db.query(RewardCampaignTarget)
                .filter(
                    RewardCampaignTarget.reward_campaign_id == c.id,
                    RewardCampaignTarget.target_unit == "kg",
                    RewardCampaignTarget.deleted_date.is_(None),
                )
                .all()
            )
            if targets:
                from .campaign_target_service import CampaignTargetService
                tsvc = CampaignTargetService(self.db)
                total_target = sum(float(t.target_amount or 0) for t in targets)
                total_current = sum(tsvc._compute_current(c.id, t) for t in targets)
                d["overall_progress_percent"] = round(
                    min(999, (total_current / total_target * 100)) if total_target > 0 else 0
                )
            else:
                d["overall_progress_percent"] = None
            result.append(d)
        return result

    def create(self, organization_id: int, data: dict) -> dict:
        if not data.get("name"):
            raise BadRequestException("Name is required")
        if not data.get("start_date"):
            raise BadRequestException("Start date is required")

        status = data.get("status", "draft")
        if status not in VALID_STATUSES:
            raise BadRequestException(f"Invalid status '{status}'")

        # Phase 2: validate metric_type + activity_types
        metric_type = data.get("metric_type", "material")
        if metric_type not in VALID_METRIC_TYPES:
            raise BadRequestException(f"Invalid metric_type '{metric_type}'")
        activity_type_ids = data.get("activity_type_ids") or []
        if metric_type == "material" and activity_type_ids:
            # Activity types only meaningful for activity campaigns; silently drop
            activity_type_ids = []

        item = RewardCampaign(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            image_id=data.get("image_id"),
            start_date=_parse_dt(data["start_date"]),
            end_date=_parse_dt(data.get("end_date")),
            status=status,
            points_per_transaction_limit=data.get("points_per_transaction_limit"),
            points_per_day_limit=data.get("points_per_day_limit"),
            target_participants=data.get("target_participants"),
            budget_baht=data.get("budget_baht"),
            metric_type=metric_type,
        )
        self.db.add(item)
        self.db.flush()

        # Persist activity-type joins (Phase 2)
        if activity_type_ids:
            for at_id in activity_type_ids:
                self.db.add(RewardCampaignActivityType(
                    campaign_id=item.id,
                    activity_type_id=at_id,
                ))
            self.db.flush()

        return self._to_dict(item)

    def update(self, id: int, data: dict) -> dict:
        item = self._get_or_404(id)

        # Breaking edit check: changing dates while active
        date_fields = ("start_date", "end_date")
        incoming_dates = {f: _parse_dt(data[f]) for f in date_fields if f in data}
        date_changed = any(
            incoming_dates.get(f) != getattr(item, f) for f in incoming_dates
        )
        if date_changed:
            assert_editable(item, breaking=True)

        # Status change validation — if status is in payload, enforce valid value
        if "status" in data and data["status"] not in VALID_STATUSES:
            raise BadRequestException(f"Invalid status '{data['status']}'")

        editable_fields = (
            "name", "description", "image_id", "start_date", "end_date", "status",
            "points_per_transaction_limit", "points_per_day_limit",
            "target_participants", "budget_baht",
        )
        for field in editable_fields:
            if field in data:
                value = _parse_dt(data[field]) if field in date_fields else data[field]
                setattr(item, field, value)

        # Phase 2: metric_type + activity_type_ids editable on draft only (breaking on active)
        if "metric_type" in data:
            new_metric = data["metric_type"]
            if new_metric not in VALID_METRIC_TYPES:
                raise BadRequestException(f"Invalid metric_type '{new_metric}'")
            if new_metric != item.metric_type:
                assert_editable(item, breaking=True)
                item.metric_type = new_metric
                if new_metric == "material":
                    # Drop activity-type joins when switching to material
                    self.db.query(RewardCampaignActivityType).filter(
                        RewardCampaignActivityType.campaign_id == item.id
                    ).delete(synchronize_session=False)

        if "activity_type_ids" in data and item.metric_type == "activity":
            new_ids = set(data.get("activity_type_ids") or [])
            existing = {
                row.activity_type_id for row in
                self.db.query(RewardCampaignActivityType.activity_type_id)
                .filter(
                    RewardCampaignActivityType.campaign_id == item.id,
                    RewardCampaignActivityType.deleted_date.is_(None),
                ).all()
            }
            to_add = new_ids - existing
            to_remove = existing - new_ids
            for at_id in to_add:
                self.db.add(RewardCampaignActivityType(
                    campaign_id=item.id,
                    activity_type_id=at_id,
                ))
            if to_remove:
                self.db.query(RewardCampaignActivityType).filter(
                    RewardCampaignActivityType.campaign_id == item.id,
                    RewardCampaignActivityType.activity_type_id.in_(to_remove),
                ).delete(synchronize_session=False)

        self.db.flush()
        return self._to_dict(item)

    def delete(self, id: int) -> dict:
        """Hard rule: only drafts can be deleted. Otherwise use archive."""
        item = self._get_or_404(id)
        if item.status != "draft":
            raise BadRequestException("Only draft campaigns can be deleted. Archive ended campaigns instead.")

        item.deleted_date = datetime.now(timezone.utc)
        self.db.flush()
        return {"id": id, "deleted": True}

    # ================================================================
    # Lifecycle transitions
    # ================================================================

    def publish(self, id: int) -> dict:
        """draft → active. Requires name + start_date + end_date."""
        item = self._get_or_404(id)
        if item.status != "draft":
            raise BadRequestException(f"Cannot publish from status '{item.status}'. Only drafts can be published.")
        if not item.name or not item.start_date or not item.end_date:
            raise BadRequestException("Required fields missing: name, start_date, end_date")

        item.status = "active"
        self.db.flush()
        return self._to_dict(item)

    def pause(self, id: int) -> dict:
        """active → paused."""
        item = self._get_or_404(id)
        effective = compute_effective_status(item)
        if effective != "active":
            raise BadRequestException(f"Cannot pause from status '{effective}'")
        item.status = "paused"
        self.db.flush()
        return self._to_dict(item)

    def resume(self, id: int) -> dict:
        """paused → active. Reject if campaign has already ended."""
        item = self._get_or_404(id)
        if item.status != "paused":
            raise BadRequestException(f"Cannot resume from status '{item.status}'")
        if item.end_date is not None:
            end = item.end_date
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if end < datetime.now(timezone.utc):
                raise BadRequestException("Campaign end_date has already passed. Extend the date first or archive.")
        item.status = "active"
        self.db.flush()
        return self._to_dict(item)

    def archive(self, id: int) -> dict:
        """ended → archived (only). Use effective_status to check."""
        item = self._get_or_404(id)
        effective = compute_effective_status(item)
        if effective != "ended":
            raise BadRequestException(f"Can only archive ended campaigns. Current effective status: '{effective}'")
        item.status = "archived"
        self.db.flush()
        return self._to_dict(item)

    # ================================================================
    # Duplicate (deep copy: config + claims + targets + droppoints)
    # ================================================================

    def duplicate(self, id: int, organization_id: int) -> dict:
        source = self._get_or_404(id)
        if source.organization_id != organization_id:
            raise BadRequestException("Campaign not in your organization")

        new_campaign = RewardCampaign(
            organization_id=source.organization_id,
            name=f"{source.name} (Copy)",
            description=source.description,
            image_id=source.image_id,
            start_date=datetime.now(timezone.utc),
            end_date=None,
            status="draft",
            points_per_transaction_limit=source.points_per_transaction_limit,
            points_per_day_limit=source.points_per_day_limit,
            target_participants=source.target_participants,
            budget_baht=source.budget_baht,
        )
        self.db.add(new_campaign)
        self.db.flush()  # need the id

        # Copy claims
        claims = (
            self.db.query(RewardCampaignClaim)
            .filter(
                RewardCampaignClaim.campaign_id == source.id,
                RewardCampaignClaim.deleted_date.is_(None),
            )
            .all()
        )
        for c in claims:
            self.db.add(RewardCampaignClaim(
                organization_id=c.organization_id,
                campaign_id=new_campaign.id,
                activity_material_id=c.activity_material_id,
                points=c.points,
                max_claims_total=c.max_claims_total,
                max_claims_per_user=c.max_claims_per_user,
            ))

        # Copy catalog links (but not stock — user must assign fresh)
        catalogs = (
            self.db.query(RewardCampaignCatalog)
            .filter(
                RewardCampaignCatalog.campaign_id == source.id,
                RewardCampaignCatalog.deleted_date.is_(None),
            )
            .all()
        )
        for cat in catalogs:
            self.db.add(RewardCampaignCatalog(
                campaign_id=new_campaign.id,
                catalog_id=cat.catalog_id,
                points_cost=cat.points_cost,
                start_date=None,
                end_date=None,
                status="active",
            ))

        # Copy droppoints (each needs a fresh hash — will be generated by service if we go through it;
        # here we inline a uuid since we have direct model access)
        import uuid
        drops = (
            self.db.query(RewardCampaignDroppoint)
            .filter(
                RewardCampaignDroppoint.campaign_id == source.id,
                RewardCampaignDroppoint.deleted_date.is_(None),
            )
            .all()
        )
        for d in drops:
            self.db.add(RewardCampaignDroppoint(
                campaign_id=new_campaign.id,
                droppoint_id=d.droppoint_id,
                tag_id=d.tag_id,
                hash=uuid.uuid4().hex,
            ))

        # Copy targets
        targets = (
            self.db.query(RewardCampaignTarget)
            .filter(
                RewardCampaignTarget.reward_campaign_id == source.id,
                RewardCampaignTarget.deleted_date.is_(None),
            )
            .all()
        )
        for t in targets:
            self.db.add(RewardCampaignTarget(
                reward_campaign_id=new_campaign.id,
                target_level=t.target_level,
                main_material_id=t.main_material_id,
                activity_material_id=t.activity_material_id,
                target_amount=t.target_amount,
                target_unit=t.target_unit,
            ))

        self.db.flush()
        return self._to_dict(new_campaign)

    # ================================================================
    # Detail — campaign + progress metrics (reuses overview_service pattern)
    # ================================================================

    def get_detail(self, id: int, organization_id: int) -> dict:
        """Return full campaign info + progress metrics. Reuses the aggregation
        pattern from overview_service.get_campaign_details but for a single campaign.
        """
        from sqlalchemy import func, distinct
        from ...models.rewards.points import RewardPointTransaction
        from ...models.rewards.redemptions import RewardRedemption
        from ...models.rewards.management import RewardActivityMaterial

        item = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not item:
            raise NotFoundException("Campaign not found")

        base = self._to_dict(item)

        participants = (
            self.db.query(func.count(distinct(RewardPointTransaction.reward_user_id)))
            .filter(
                RewardPointTransaction.reward_campaign_id == id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        weight = float(
            self.db.query(func.coalesce(func.sum(RewardPointTransaction.value), 0))
            .filter(
                RewardPointTransaction.reward_campaign_id == id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        ghg_kg = float(
            self.db.query(
                func.coalesce(
                    func.sum(RewardPointTransaction.value * RewardActivityMaterial.ghg_factor),
                    0,
                )
            )
            .select_from(RewardPointTransaction)
            .join(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .filter(
                RewardPointTransaction.reward_campaign_id == id,
                RewardPointTransaction.reference_type == "claim",
                RewardActivityMaterial.ghg_factor.isnot(None),
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        redemptions = (
            self.db.query(func.count(RewardRedemption.id))
            .filter(
                RewardRedemption.reward_campaign_id == id,
                RewardRedemption.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        base["participants_count"] = int(participants)
        base["total_weight_kg"] = weight
        base["total_ghg_kg"] = ghg_kg
        base["redemptions_count"] = int(redemptions)
        return base

    # ================================================================
    # Scoped ledgers — transactions + members (used by detail tabs 3, 4)
    # ================================================================

    def list_transactions(
        self,
        id: int,
        organization_id: int,
        ref_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Scoped transactions ledger for a single campaign — merges claims + redemptions."""
        from sqlalchemy import func
        from ...models.rewards.points import RewardPointTransaction
        from ...models.rewards.redemptions import RewardRedemption, RewardUser, OrganizationRewardUser
        from ...models.rewards.management import RewardActivityMaterial
        from ...models.rewards.catalog import RewardCatalog

        # Validate campaign belongs to org
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise NotFoundException("Campaign not found")

        items: list[dict] = []

        # --- CLAIMS ---
        if ref_type in (None, "all", "claim"):
            claim_rows = (
                self.db.query(
                    RewardPointTransaction,
                    RewardUser,
                    RewardActivityMaterial,
                )
                .outerjoin(RewardUser, RewardUser.id == RewardPointTransaction.reward_user_id)
                .outerjoin(
                    RewardActivityMaterial,
                    RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
                )
                .filter(
                    RewardPointTransaction.reward_campaign_id == id,
                    RewardPointTransaction.reference_type == "claim",
                    RewardPointTransaction.deleted_date.is_(None),
                )
            )
            if date_from:
                claim_rows = claim_rows.filter(RewardPointTransaction.claimed_date >= date_from)
            if date_to:
                claim_rows = claim_rows.filter(RewardPointTransaction.claimed_date <= date_to)

            for tx, user, am in claim_rows.all():
                user_name = (user.display_name if user else None) or (user.line_display_name if user else None) or f"User #{tx.reward_user_id}"
                if search and search.lower() not in user_name.lower():
                    continue
                items.append({
                    "id": f"claim-{tx.id}",
                    "type": "claim",
                    "datetime": self._safe_iso(tx.claimed_date or tx.created_date),
                    "member_name": user_name,
                    "reward_user_id": tx.reward_user_id,
                    "staff_id": tx.staff_id,
                    "item_name": am.name if am else None,
                    "item_type": am.type if am else None,
                    "value": float(tx.value) if tx.value is not None else None,
                    "unit": tx.unit,
                    "points": float(tx.points) if tx.points is not None else 0,
                    "status": "completed",
                })

        # --- REDEMPTIONS ---
        if ref_type in (None, "all", "redeem"):
            redeem_rows = (
                self.db.query(RewardRedemption, RewardUser, RewardCatalog)
                .outerjoin(RewardUser, RewardUser.id == RewardRedemption.reward_user_id)
                .outerjoin(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
                .filter(
                    RewardRedemption.reward_campaign_id == id,
                    RewardRedemption.deleted_date.is_(None),
                )
            )
            if date_from:
                redeem_rows = redeem_rows.filter(RewardRedemption.created_date >= date_from)
            if date_to:
                redeem_rows = redeem_rows.filter(RewardRedemption.created_date <= date_to)

            for r, user, cat in redeem_rows.all():
                user_name = (user.display_name if user else None) or (user.line_display_name if user else None) or f"User #{r.reward_user_id}"
                if search and search.lower() not in user_name.lower():
                    continue
                items.append({
                    "id": f"redeem-{r.id}",
                    "type": "redeem",
                    "datetime": self._safe_iso(r.created_date),
                    "member_name": user_name,
                    "reward_user_id": r.reward_user_id,
                    "staff_id": r.staff_id,
                    "item_name": cat.name if cat else None,
                    "item_type": "reward",
                    "value": float(r.quantity or 1),
                    "unit": "ชิ้น",
                    "points": -float(r.points_redeemed or 0),
                    "status": r.status,
                })

        # Sort desc by datetime, paginate
        items.sort(key=lambda x: x["datetime"] or "", reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        paged = items[start : start + page_size]

        return {
            "items": paged,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }

    def list_members(
        self,
        id: int,
        organization_id: int,
        search: str | None = None,
        sort: str = "points",
    ) -> list[dict]:
        """Members who claimed in THIS campaign, with scoped points + weight totals."""
        from sqlalchemy import func
        from ...models.rewards.points import RewardPointTransaction
        from ...models.rewards.redemptions import RewardUser, OrganizationRewardUser

        # Validate campaign
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise NotFoundException("Campaign not found")

        # Aggregate per user (only claim-type transactions = positive earn)
        rows = (
            self.db.query(
                RewardPointTransaction.reward_user_id.label("uid"),
                func.coalesce(func.sum(RewardPointTransaction.points), 0).label("points_earned"),
                func.coalesce(func.sum(RewardPointTransaction.value), 0).label("total_weight"),
                func.min(RewardPointTransaction.created_date).label("first_claim"),
            )
            .filter(
                RewardPointTransaction.reward_campaign_id == id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_user_id)
            .all()
        )

        result = []
        for r in rows:
            user = self.db.query(RewardUser).filter(RewardUser.id == r.uid).first()
            if not user:
                continue
            name = user.display_name or user.line_display_name or f"User #{r.uid}"
            if search and search.lower() not in name.lower():
                continue
            org_user = (
                self.db.query(OrganizationRewardUser)
                .filter(
                    OrganizationRewardUser.reward_user_id == r.uid,
                    OrganizationRewardUser.organization_id == organization_id,
                    OrganizationRewardUser.deleted_date.is_(None),
                )
                .first()
            )
            result.append({
                "reward_user_id": r.uid,
                "org_reward_user_id": org_user.id if org_user else None,
                "display_name": name,
                "line_picture_url": user.line_picture_url,
                "points_earned": float(r.points_earned or 0),
                "total_weight_kg": float(r.total_weight or 0),
                "first_claim_date": self._safe_iso(r.first_claim),
            })

        if sort == "weight":
            result.sort(key=lambda x: x["total_weight_kg"], reverse=True)
        elif sort == "joined":
            result.sort(key=lambda x: x["first_claim_date"] or "")
        else:
            result.sort(key=lambda x: x["points_earned"], reverse=True)

        return result

    def get_weekly_trend(self, id: int, organization_id: int, weeks: int = 8) -> list[dict]:
        """Return kg collected per ISO week for the last N weeks (default 8)."""
        from sqlalchemy import func
        from datetime import timedelta
        from ...models.rewards.points import RewardPointTransaction

        # Validate campaign
        campaign = (
            self.db.query(RewardCampaign)
            .filter(
                RewardCampaign.id == id,
                RewardCampaign.organization_id == organization_id,
                RewardCampaign.deleted_date.is_(None),
            )
            .first()
        )
        if not campaign:
            raise NotFoundException("Campaign not found")

        now = datetime.now(timezone.utc)
        start = now - timedelta(weeks=weeks)

        rows = (
            self.db.query(
                func.date_trunc('week', RewardPointTransaction.claimed_date).label('week_start'),
                func.coalesce(func.sum(RewardPointTransaction.value), 0).label('weight'),
            )
            .filter(
                RewardPointTransaction.reward_campaign_id == id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= start,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by('week_start')
            .order_by('week_start')
            .all()
        )

        return [
            {
                "week_start": r.week_start.isoformat() if r.week_start else None,
                "weight_kg": float(r.weight or 0),
            }
            for r in rows
        ]
