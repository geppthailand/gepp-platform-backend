"""
Staff Service — performance metrics + revoke staff role.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import func, distinct, case
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    RewardRedemption,
    Droppoint,
)
from ...models.rewards.points import RewardPointTransaction
from ...exceptions import NotFoundException, BadRequestException


class StaffService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _today_start(now: datetime) -> datetime:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def get_kpis(self, organization_id: int) -> dict:
        now = datetime.now(timezone.utc)
        today = self._today_start(now)

        total_staff = int(
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.role == "staff",
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        # Active today = distinct staff who have at least 1 claim today
        active_today = int(
            self.db.query(func.count(distinct(RewardPointTransaction.staff_id)))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.staff_id.isnot(None),
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= today,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        claims_today_total = int(
            self.db.query(func.count(RewardPointTransaction.id))
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.staff_id.isnot(None),
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= today,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .scalar() or 0
        )

        return {
            "total_staff": total_staff,
            "active_today": active_today,
            "claims_today_total": claims_today_total,
        }

    def list_performance(self, organization_id: int) -> list[dict]:
        """Each staff with claim aggregates (today/7d/30d) + recent droppoints."""
        now = datetime.now(timezone.utc)
        today = self._today_start(now)
        d7 = now - timedelta(days=7)
        d30 = now - timedelta(days=30)

        # Base: staff members
        staff_rows = (
            self.db.query(OrganizationRewardUser, RewardUser)
            .join(RewardUser, RewardUser.id == OrganizationRewardUser.reward_user_id)
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.role == "staff",
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .order_by(OrganizationRewardUser.id.desc())
            .all()
        )
        if not staff_rows:
            return []

        staff_ids = [ou.id for ou, _ in staff_rows]

        # Aggregate claims per window — one SQL pass
        agg_rows = (
            self.db.query(
                RewardPointTransaction.staff_id,
                func.coalesce(
                    func.sum(case((RewardPointTransaction.claimed_date >= today, 1), else_=0)),
                    0,
                ).label("claims_today"),
                func.coalesce(
                    func.sum(case((RewardPointTransaction.claimed_date >= d7, 1), else_=0)),
                    0,
                ).label("claims_7d"),
                func.coalesce(func.count(RewardPointTransaction.id), 0).label("claims_30d"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                RewardPointTransaction.claimed_date >= today,
                                RewardPointTransaction.value,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("weight_today_kg"),
                func.coalesce(
                    func.sum(
                        case(
                            (RewardPointTransaction.claimed_date >= d7, RewardPointTransaction.value),
                            else_=0,
                        )
                    ),
                    0,
                ).label("weight_7d_kg"),
                func.coalesce(func.sum(RewardPointTransaction.value), 0).label("weight_30d_kg"),
                func.max(RewardPointTransaction.claimed_date).label("last_active"),
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.staff_id.in_(staff_ids),
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= d30,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.staff_id)
            .all()
        )
        agg_map = {row.staff_id: row for row in agg_rows}

        # Confirms today per staff
        confirm_rows = (
            self.db.query(
                RewardRedemption.staff_id,
                func.count(RewardRedemption.id).label("confirms_today"),
            )
            .filter(
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.staff_id.in_(staff_ids),
                RewardRedemption.status == "completed",
                RewardRedemption.updated_date >= today,
                RewardRedemption.deleted_date.is_(None),
            )
            .group_by(RewardRedemption.staff_id)
            .all()
        )
        confirm_map = {r.staff_id: int(r.confirms_today) for r in confirm_rows}

        # Droppoints recent (last 30d)
        droppoint_rows = (
            self.db.query(
                RewardPointTransaction.staff_id,
                RewardPointTransaction.droppoint_id,
                Droppoint.name.label("droppoint_name"),
            )
            .outerjoin(Droppoint, Droppoint.id == RewardPointTransaction.droppoint_id)
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.staff_id.in_(staff_ids),
                RewardPointTransaction.droppoint_id.isnot(None),
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= d30,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .distinct()
            .all()
        )
        droppoint_map: dict[int, list[dict]] = {}
        for row in droppoint_rows:
            if row.droppoint_id is None:
                continue
            droppoint_map.setdefault(row.staff_id, []).append({
                "id": row.droppoint_id,
                "name": row.droppoint_name,
            })

        result = []
        for org_user, user in staff_rows:
            agg = agg_map.get(org_user.id)
            result.append({
                "id": org_user.id,
                "reward_user_id": user.id,
                "display_name": user.display_name or user.line_display_name,
                "line_picture_url": user.line_picture_url,
                "is_active": org_user.is_active,
                "claims_today": int(agg.claims_today) if agg else 0,
                "claims_7d": int(agg.claims_7d) if agg else 0,
                "claims_30d": int(agg.claims_30d) if agg else 0,
                "weight_today_kg": float(agg.weight_today_kg or 0) if agg else 0.0,
                "weight_7d_kg": float(agg.weight_7d_kg or 0) if agg else 0.0,
                "weight_30d_kg": float(agg.weight_30d_kg or 0) if agg else 0.0,
                "confirms_today": confirm_map.get(org_user.id, 0),
                "last_active_date": (
                    agg.last_active.isoformat()
                    if agg and agg.last_active
                    else None
                ),
                "droppoints_recent": droppoint_map.get(org_user.id, []),
            })
        return result

    def revoke_staff(self, org_reward_user_id: int, organization_id: int) -> dict:
        """Demote staff → user. Historical claims/confirms are preserved."""
        org_user = (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.id == org_reward_user_id,
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .first()
        )
        if not org_user:
            raise NotFoundException("Staff not found")
        if org_user.role != "staff":
            raise BadRequestException("Member is not a staff")

        org_user.role = "user"
        self.db.flush()
        return {"id": org_user.id, "role": "user"}
