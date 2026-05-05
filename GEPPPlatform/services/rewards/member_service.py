"""
Member Service - Manage organization reward members (enhanced)
"""

from __future__ import annotations  # guard against future list/get methods shadowing builtins

from datetime import datetime, timezone, timedelta

from sqlalchemy import func, or_, and_, case
from sqlalchemy.orm import Session

from ...models.rewards.redemptions import (
    RewardUser,
    OrganizationRewardUser,
    RewardRedemption,
    Droppoint,
)
from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.catalog import RewardCatalog, RewardStock
from ...models.rewards.management import (
    RewardCampaign,
    RewardActivityMaterial,
)
from ...exceptions import NotFoundException, BadRequestException


class MemberService:
    def __init__(self, db: Session):
        self.db = db

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _start_of_month(now: datetime) -> datetime:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _get_member_aggregates(self, reward_user_ids: list[int], organization_id: int) -> dict[int, dict]:
        """Batch-compute lifetime earned / redeemed / last_active for a list of users.

        Returns: { reward_user_id: {lifetime_earned, redeemed, current_balance, last_active_date} }
        """
        if not reward_user_ids:
            return {}

        # Earned = sum points where reference_type in ('claim','refund'), redeemed = abs sum where 'redeem'
        # Refund also adds to balance (effectively a credit)
        earned_rows = (
            self.db.query(
                RewardPointTransaction.reward_user_id,
                func.coalesce(
                    func.sum(
                        case(
                            (RewardPointTransaction.reference_type == "redeem", 0),
                            else_=RewardPointTransaction.points,
                        )
                    ),
                    0,
                ).label("earned"),
                func.coalesce(
                    func.sum(
                        case(
                            (RewardPointTransaction.reference_type == "redeem", RewardPointTransaction.points),
                            else_=0,
                        )
                    ),
                    0,
                ).label("redeemed"),
                func.max(
                    case(
                        (RewardPointTransaction.reference_type == "claim", RewardPointTransaction.claimed_date),
                        else_=None,
                    )
                ).label("last_active"),
            )
            .filter(
                RewardPointTransaction.reward_user_id.in_(reward_user_ids),
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_user_id)
            .all()
        )

        out = {}
        for row in earned_rows:
            earned = float(row.earned or 0)
            redeemed = float(row.redeemed or 0)
            out[row.reward_user_id] = {
                "lifetime_earned": earned,
                "redeemed": redeemed,
                "current_balance": earned - redeemed,
                "last_active_date": row.last_active.isoformat() if row.last_active else None,
            }
        return out

    # ── List + Filters ───────────────────────────────────────────────────

    def list_members(self, organization_id: int, filters: dict | None = None) -> dict:
        """List members with filters + aggregates + KPIs.

        filters: {
          role?: 'user'|'staff',
          is_active?: bool,
          search?: str (name/email/phone/line_user_id),
          date_from?: str ISO,
          date_to?: str ISO,
          page?: int,
          page_size?: int,
          sort?: 'joined_desc'|'joined_asc'|'points_desc'|'last_active_desc',
        }
        Returns: { items, total, page, page_size, meta: { kpis } }
        """
        f = filters or {}
        page = max(1, int(f.get("page") or 1))
        page_size = max(1, min(200, int(f.get("page_size") or 10)))
        offset = (page - 1) * page_size

        q = (
            self.db.query(OrganizationRewardUser, RewardUser)
            .join(RewardUser, RewardUser.id == OrganizationRewardUser.reward_user_id)
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
        )

        if f.get("role") in ("user", "staff"):
            q = q.filter(OrganizationRewardUser.role == f["role"])
        if "is_active" in f and f["is_active"] is not None:
            q = q.filter(OrganizationRewardUser.is_active == bool(f["is_active"]))
        if f.get("date_from"):
            q = q.filter(OrganizationRewardUser.created_date >= f["date_from"])
        if f.get("date_to"):
            q = q.filter(OrganizationRewardUser.created_date <= f["date_to"])
        if f.get("search"):
            like = f"%{f['search']}%"
            q = q.filter(
                or_(
                    RewardUser.display_name.ilike(like),
                    RewardUser.line_display_name.ilike(like),
                    RewardUser.email.ilike(like),
                    RewardUser.phone_number.ilike(like),
                    RewardUser.line_user_id.ilike(like),
                )
            )

        total = q.count()

        # Sort
        sort = f.get("sort") or "joined_desc"
        sort_col = {
            "joined_desc": OrganizationRewardUser.created_date.desc(),
            "joined_asc": OrganizationRewardUser.created_date.asc(),
        }.get(sort, OrganizationRewardUser.created_date.desc())
        q = q.order_by(sort_col)

        rows = q.offset(offset).limit(page_size).all()
        reward_user_ids = [user.id for _, user in rows]
        aggs = self._get_member_aggregates(reward_user_ids, organization_id)

        items = []
        for org_user, user in rows:
            agg = aggs.get(user.id, {
                "lifetime_earned": 0.0,
                "redeemed": 0.0,
                "current_balance": 0.0,
                "last_active_date": None,
            })
            items.append({
                "id": org_user.id,
                "reward_user_id": user.id,
                "organization_id": org_user.organization_id,
                "display_name": user.display_name or user.line_display_name,
                "line_picture_url": user.line_picture_url,
                "email": user.email,
                "phone_number": user.phone_number,
                "line_user_id": user.line_user_id,
                "role": org_user.role,
                "is_active": org_user.is_active,
                "created_date": org_user.created_date.isoformat() if org_user.created_date else None,
                "updated_date": org_user.updated_date.isoformat() if org_user.updated_date else None,
                "lifetime_earned": agg["lifetime_earned"],
                "current_balance": agg["current_balance"],
                "claimed_points": agg["lifetime_earned"],  # legacy alias for existing callers
                "last_active_date": agg["last_active_date"],
            })

        # KPIs (not scoped to current page — query whole org)
        meta_kpis = self._compute_kpis(organization_id)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "meta": {"kpis": meta_kpis},
        }

    def _compute_kpis(self, organization_id: int) -> dict:
        now = datetime.now(timezone.utc)
        month_start = self._start_of_month(now)

        total = int(
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .scalar() or 0
        )
        active = int(
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
                OrganizationRewardUser.is_active.is_(True),
            )
            .scalar() or 0
        )
        staff = int(
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
                OrganizationRewardUser.role == "staff",
            )
            .scalar() or 0
        )
        new_this_month = int(
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
                OrganizationRewardUser.created_date >= month_start,
            )
            .scalar() or 0
        )
        return {
            "total": total,
            "active": active,
            "staff": staff,
            "new_this_month": new_this_month,
        }

    # ── Detail ────────────────────────────────────────────────────────────

    def get_detail(self, org_reward_user_id: int, organization_id: int) -> dict:
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
            raise NotFoundException("Member not found")

        user = self.db.query(RewardUser).filter(RewardUser.id == org_user.reward_user_id).first()
        if not user:
            raise NotFoundException("Reward user not found")

        agg = self._get_member_aggregates([user.id], organization_id).get(user.id, {
            "lifetime_earned": 0.0,
            "redeemed": 0.0,
            "current_balance": 0.0,
            "last_active_date": None,
        })

        # Points per campaign
        points_by_campaign = (
            self.db.query(
                RewardCampaign.id.label("campaign_id"),
                RewardCampaign.name.label("campaign_name"),
                func.coalesce(
                    func.sum(
                        case(
                            (RewardPointTransaction.reference_type == "redeem", 0),
                            else_=RewardPointTransaction.points,
                        )
                    ),
                    0,
                ).label("earned"),
                func.coalesce(
                    func.sum(
                        case(
                            (RewardPointTransaction.reference_type == "redeem", RewardPointTransaction.points),
                            else_=0,
                        )
                    ),
                    0,
                ).label("redeemed"),
            )
            .join(RewardPointTransaction, RewardPointTransaction.reward_campaign_id == RewardCampaign.id)
            .filter(
                RewardPointTransaction.reward_user_id == org_user.reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardCampaign.id, RewardCampaign.name)
            .all()
        )

        claimed_points_list = [
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "total_points": float(row.earned),  # legacy key, = lifetime earned for this campaign
                "lifetime_earned": float(row.earned),
                "redeemed": float(row.redeemed),
                "balance": float(row.earned) - float(row.redeemed),
            }
            for row in points_by_campaign
        ]

        # Last claimed date per campaign (for legacy display)
        last_claim_rows = (
            self.db.query(
                RewardPointTransaction.reward_campaign_id,
                func.max(RewardPointTransaction.claimed_date).label("last_claimed"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == org_user.reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(RewardPointTransaction.reward_campaign_id)
            .all()
        )
        last_claim_map = {r.reward_campaign_id: r.last_claimed for r in last_claim_rows}
        for row in claimed_points_list:
            lc = last_claim_map.get(row["campaign_id"])
            row["last_claimed"] = lc.isoformat() if lc else None

        # Redemptions
        redemptions = (
            self.db.query(
                RewardRedemption,
                RewardCatalog.name.label("catalog_name"),
                RewardCampaign.name.label("campaign_name"),
            )
            .join(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
            .join(RewardCampaign, RewardCampaign.id == RewardRedemption.reward_campaign_id)
            .filter(
                RewardRedemption.reward_user_id == org_user.reward_user_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .order_by(RewardRedemption.created_date.desc())
            .all()
        )
        redemption_list = [
            {
                "id": r.id,
                "catalog_name": catalog_name,
                "campaign_name": campaign_name,
                "quantity": r.quantity,
                "points_redeemed": r.points_redeemed,
                "status": r.status,
                "hash": r.hash,
                "note": r.note,
                "created_date": r.created_date.isoformat() if r.created_date else None,
                "updated_date": r.updated_date.isoformat() if r.updated_date else None,
            }
            for r, catalog_name, campaign_name in redemptions
        ]

        return {
            "id": org_user.id,
            "reward_user_id": user.id,
            "display_name": user.display_name or user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "email": user.email,
            "phone_number": user.phone_number,
            "line_user_id": user.line_user_id,
            "whatsapp_user_id": user.whatsapp_user_id,
            "wechat_user_id": user.wechat_user_id,
            "role": org_user.role,
            "is_active": org_user.is_active,
            "created_date": org_user.created_date.isoformat() if org_user.created_date else None,
            "updated_date": org_user.updated_date.isoformat() if org_user.updated_date else None,
            "lifetime_earned": agg["lifetime_earned"],
            "current_balance": agg["current_balance"],
            "last_active_date": agg["last_active_date"],
            "claimed_points_list": claimed_points_list,
            "redemption_list": redemption_list,
        }

    # ── Timeline ──────────────────────────────────────────────────────────

    def get_timeline(self, org_reward_user_id: int, organization_id: int, days: int = 30) -> dict:
        """Activity timeline — merged claims + redemptions + 12-week chart data."""
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
            raise NotFoundException("Member not found")

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Claim entries
        claim_rows = (
            self.db.query(
                RewardPointTransaction,
                RewardCampaign.name.label("campaign_name"),
                RewardActivityMaterial.name.label("activity_name"),
                Droppoint.name.label("droppoint_name"),
            )
            .outerjoin(RewardCampaign, RewardCampaign.id == RewardPointTransaction.reward_campaign_id)
            .outerjoin(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .outerjoin(Droppoint, Droppoint.id == RewardPointTransaction.droppoint_id)
            .filter(
                RewardPointTransaction.reward_user_id == org_user.reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= cutoff,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .order_by(RewardPointTransaction.claimed_date.desc())
            .all()
        )

        # Redemption entries
        redeem_rows = (
            self.db.query(
                RewardRedemption,
                RewardCatalog.name.label("catalog_name"),
                RewardCampaign.name.label("campaign_name"),
            )
            .outerjoin(RewardCatalog, RewardCatalog.id == RewardRedemption.catalog_id)
            .outerjoin(RewardCampaign, RewardCampaign.id == RewardRedemption.reward_campaign_id)
            .filter(
                RewardRedemption.reward_user_id == org_user.reward_user_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.created_date >= cutoff,
                RewardRedemption.deleted_date.is_(None),
            )
            .order_by(RewardRedemption.created_date.desc())
            .all()
        )

        timeline = []
        for pt, campaign_name, activity_name, droppoint_name in claim_rows:
            timeline.append({
                "type": "claim",
                "date": pt.claimed_date.isoformat() if pt.claimed_date else None,
                "points": float(pt.points or 0),
                "campaign_name": campaign_name,
                "activity_material_name": activity_name,
                "value": float(pt.value or 0) if pt.value is not None else None,
                "unit": pt.unit,
                "droppoint_name": droppoint_name,
            })
        for r, catalog_name, campaign_name in redeem_rows:
            timeline.append({
                "type": "redeem",
                "date": r.created_date.isoformat() if r.created_date else None,
                "points": -float(r.points_redeemed or 0),
                "campaign_name": campaign_name,
                "catalog_name": catalog_name,
                "quantity": r.quantity,
                "status": r.status,
                "redemption_id": r.id,
            })
        timeline.sort(key=lambda e: e["date"] or "", reverse=True)

        # 12-week bar chart (claims count + weight by week)
        week_cutoff = now - timedelta(weeks=12)
        # date_trunc('week', ...) behavior: week starts Monday in Postgres
        weekly_rows = (
            self.db.query(
                func.date_trunc("week", RewardPointTransaction.claimed_date).label("week_start"),
                func.count(RewardPointTransaction.id).label("claims_count"),
                func.coalesce(func.sum(RewardPointTransaction.value), 0).label("weight_kg"),
            )
            .filter(
                RewardPointTransaction.reward_user_id == org_user.reward_user_id,
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.claimed_date >= week_cutoff,
                RewardPointTransaction.deleted_date.is_(None),
            )
            .group_by(func.date_trunc("week", RewardPointTransaction.claimed_date))
            .order_by(func.date_trunc("week", RewardPointTransaction.claimed_date).asc())
            .all()
        )
        weekly_claim_chart = [
            {
                "week_start": row.week_start.isoformat() if row.week_start else None,
                "claims_count": int(row.claims_count or 0),
                "weight_kg": float(row.weight_kg or 0),
            }
            for row in weekly_rows
        ]

        return {
            "timeline": timeline,
            "weekly_claim_chart": weekly_claim_chart,
        }

    # ── Mutations ────────────────────────────────────────────────────────

    def update_role(self, org_reward_user_id: int, role: str, organization_id: int = None) -> dict:
        if role not in ("user", "staff"):
            raise BadRequestException("Role must be 'user' or 'staff'")

        q = self.db.query(OrganizationRewardUser).filter(
            OrganizationRewardUser.id == org_reward_user_id,
            OrganizationRewardUser.deleted_date.is_(None),
        )
        if organization_id is not None:
            q = q.filter(OrganizationRewardUser.organization_id == organization_id)
        org_user = q.first()
        if not org_user:
            raise NotFoundException("Member not found")

        org_user.role = role
        self.db.flush()
        return {"id": org_user.id, "role": org_user.role}

    def toggle_active(self, org_reward_user_id: int, organization_id: int = None) -> dict:
        q = self.db.query(OrganizationRewardUser).filter(
            OrganizationRewardUser.id == org_reward_user_id,
            OrganizationRewardUser.deleted_date.is_(None),
        )
        if organization_id is not None:
            q = q.filter(OrganizationRewardUser.organization_id == organization_id)
        org_user = q.first()
        if not org_user:
            raise NotFoundException("Member not found")

        org_user.is_active = not org_user.is_active
        self.db.flush()
        return {"id": org_user.id, "is_active": org_user.is_active}

    def bulk_toggle_active(
        self,
        org_reward_user_ids: list[int],
        is_active: bool,
        organization_id: int,
    ) -> dict:
        if not org_reward_user_ids:
            raise BadRequestException("ids must not be empty")

        # Validate all belong to org
        valid_count = (
            self.db.query(func.count(OrganizationRewardUser.id))
            .filter(
                OrganizationRewardUser.id.in_(org_reward_user_ids),
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .scalar() or 0
        )
        if valid_count != len(org_reward_user_ids):
            raise BadRequestException("Some ids do not belong to your organization")

        (
            self.db.query(OrganizationRewardUser)
            .filter(
                OrganizationRewardUser.id.in_(org_reward_user_ids),
                OrganizationRewardUser.organization_id == organization_id,
                OrganizationRewardUser.deleted_date.is_(None),
            )
            .update({"is_active": is_active}, synchronize_session=False)
        )
        self.db.flush()
        return {"updated_count": len(org_reward_user_ids), "is_active": is_active}

    def admin_confirm_redemption(
        self,
        redemption_id: int,
        organization_id: int,
        admin_user_id: int | None = None,
    ) -> dict:
        """Confirm redemption as admin — same side-effects as staff QR confirm.

        Differs from ConfirmService.confirm_redemption: bypasses QR hash auth,
        and sets staff_id=NULL (admin isn't a staff reward user).
        Stock deduction + atomic status change mirror ConfirmService._confirm_single.
        """
        from sqlalchemy import update, or_ as sql_or

        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.id == redemption_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .first()
        )
        if not redemption:
            raise NotFoundException("Redemption not found")
        if redemption.status == "completed":
            return {
                "already_completed": True,
                "completed_at": redemption.updated_date.isoformat() if redemption.updated_date else None,
            }
        if redemption.status == "canceled":
            raise BadRequestException("Redemption was canceled")
        if redemption.status != "inprogress":
            raise BadRequestException(f"Unexpected status: {redemption.status}")

        now = datetime.now(timezone.utc)
        admin_note = f"Confirmed by admin #{admin_user_id}" if admin_user_id else "Confirmed by admin"

        # Atomic status transition
        result = self.db.execute(
            update(RewardRedemption)
            .where(
                RewardRedemption.id == redemption_id,
                RewardRedemption.status == "inprogress",
            )
            .values(status="completed", updated_date=now, note=admin_note)
        )
        self.db.flush()
        if result.rowcount == 0:
            self.db.refresh(redemption)
            if redemption.status == "completed":
                return {
                    "already_completed": True,
                    "completed_at": redemption.updated_date.isoformat() if redemption.updated_date else None,
                }
            raise BadRequestException(f"Unexpected status: {redemption.status}")

        self.db.refresh(redemption)

        # Check + deduct stock (mirror ConfirmService._deduct_stock)
        current_stock = (
            self.db.query(func.coalesce(func.sum(RewardStock.values), 0))
            .filter(
                RewardStock.reward_catalog_id == redemption.catalog_id,
                sql_or(
                    RewardStock.reward_campaign_id == redemption.reward_campaign_id,
                    RewardStock.reward_campaign_id.is_(None),
                ),
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

        stock_record = RewardStock(
            reward_catalog_id=redemption.catalog_id,
            values=-redemption.quantity,
            reward_campaign_id=redemption.reward_campaign_id,
            note="redemption_confirmed_by_admin",
            reward_user_id=redemption.reward_user_id,
            ledger_type="redeem",
            admin_user_id=admin_user_id,
        )
        self.db.add(stock_record)
        self.db.flush()
        redemption.stock_action_id = stock_record.id
        self.db.flush()

        return {"success": True, "redemption_id": redemption.id, "status": "completed"}

    def admin_cancel_redemption(
        self,
        redemption_id: int,
        organization_id: int,
        admin_user_id: int | None = None,
        note: str | None = None,
    ) -> dict:
        """Cancel inprogress redemption as admin — refund points."""
        redemption = (
            self.db.query(RewardRedemption)
            .filter(
                RewardRedemption.id == redemption_id,
                RewardRedemption.organization_id == organization_id,
                RewardRedemption.deleted_date.is_(None),
            )
            .first()
        )
        if not redemption:
            raise NotFoundException("Redemption not found")
        if redemption.status != "inprogress":
            raise BadRequestException(f"Cannot cancel redemption with status '{redemption.status}'")

        now = datetime.now(timezone.utc)
        redemption.status = "canceled"
        redemption.updated_date = now
        redemption.note = note or (f"Canceled by admin #{admin_user_id}" if admin_user_id else "Canceled by admin")
        self.db.flush()

        refund_txn = RewardPointTransaction(
            organization_id=redemption.organization_id,
            reward_user_id=redemption.reward_user_id,
            points=redemption.points_redeemed,
            reward_campaign_id=redemption.reward_campaign_id,
            claimed_date=now,
            reference_type="refund",
        )
        self.db.add(refund_txn)
        self.db.flush()

        return {
            "success": True,
            "redemption_id": redemption.id,
            "refunded_points": redemption.points_redeemed,
        }
