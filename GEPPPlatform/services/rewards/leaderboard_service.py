"""
Leaderboard Service — per-org ranking of users by GHG reduced (kg CO₂e).

Used by:
  - Admin /rewards → Members tab → Leaderboard sub-tab
  - LIFF user (per-org, hidden until user opens it)

Metric is GHG (not raw kg) because GHG weights heavier-impact materials more.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.rewards.points import RewardPointTransaction
from ...models.rewards.redemptions import RewardUser
from ...models.rewards.management import RewardActivityMaterial, RewardCampaign
from ...exceptions import BadRequestException
from .redeem_service import _estimate_ghg_per_kg, _is_weight_unit


VALID_PERIODS = ("week", "month", "all")


class LeaderboardService:
    def __init__(self, db: Session):
        self.db = db

    def _period_window(self, period: str) -> tuple[datetime | None, datetime | None]:
        """Resolve (start, end) for a named period. 'all' returns (None, None)."""
        if period not in VALID_PERIODS:
            raise BadRequestException(
                f"Invalid period '{period}'. Must be one of: {', '.join(VALID_PERIODS)}"
            )
        if period == "all":
            return (None, None)

        now = datetime.now(timezone.utc)
        end = now
        if period == "week":
            # Last 7 days (rolling)
            start = now - timedelta(days=7)
        else:  # month
            start = now - timedelta(days=30)
        return (start, end)

    def get_leaderboard(
        self,
        organization_id: int,
        period: str = "month",
        limit: int = 50,
        viewer_user_id: int | None = None,
    ) -> dict:
        """Rank users in `organization_id` by GHG reduced inside the period.

        Returns:
          {
            "period": "week" | "month" | "all",
            "metric": "ghg",
            "items": [
              { rank, reward_user_id, display_name, line_picture_url,
                ghg_kg_co2, kg_recycled, claims_count }
            ],
            "total_users": int,             # number of users with ≥1 claim in window
            "my_rank": int | None,          # rank of viewer_user_id (None if not opted-in / no claims)
            "my_value": { ghg_kg_co2, kg_recycled, claims_count } | None,
          }
        """
        start, end = self._period_window(period)

        # Pull every weight-unit claim for the org in the window, joined with material
        # so we can apply the GHG factor per material name. Outer-join campaign so we can
        # drop claims whose campaign was soft-deleted (matches the gamification summary).
        q = (
            self.db.query(
                RewardPointTransaction.reward_user_id.label("user_id"),
                RewardPointTransaction.value.label("kg"),
                RewardPointTransaction.unit.label("unit"),
                RewardPointTransaction.reward_campaign_id.label("campaign_id"),
                RewardActivityMaterial.name.label("material_name"),
                RewardActivityMaterial.type.label("material_type"),
                RewardCampaign.deleted_date.label("campaign_deleted"),
            )
            .outerjoin(
                RewardActivityMaterial,
                RewardActivityMaterial.id == RewardPointTransaction.reward_activity_materials_id,
            )
            .outerjoin(
                RewardCampaign,
                RewardCampaign.id == RewardPointTransaction.reward_campaign_id,
            )
            .filter(
                RewardPointTransaction.organization_id == organization_id,
                RewardPointTransaction.reference_type == "claim",
                RewardPointTransaction.points > 0,
                RewardPointTransaction.deleted_date.is_(None),
            )
        )
        if start is not None:
            q = q.filter(RewardPointTransaction.claimed_date >= start)
        if end is not None:
            q = q.filter(RewardPointTransaction.claimed_date <= end)

        rows = q.all()

        # Aggregate per user
        per_user: dict[int, dict] = {}
        for r in rows:
            qty = float(r.kg or 0)
            if qty <= 0 or not _is_weight_unit(r.unit):
                continue
            # Skip claims whose campaign was soft-deleted (orphaned rows shouldn't count)
            if r.campaign_id is not None and r.campaign_deleted is not None:
                continue
            # Skip non-material claims (activity rows don't reduce GHG even if logged as weight)
            if r.material_type and r.material_type != "material":
                continue
            ghg = qty * _estimate_ghg_per_kg(r.material_name)
            acc = per_user.setdefault(r.user_id, {"ghg": 0.0, "kg": 0.0, "claims": 0})
            acc["ghg"] += ghg
            acc["kg"] += qty
            acc["claims"] += 1

        # Also include claims_count from non-material rows? No — leaderboard is about GHG,
        # so only material-weight claims qualify. Users with only activity claims won't appear.

        if not per_user:
            return {
                "period": period,
                "metric": "ghg",
                "items": [],
                "total_users": 0,
                "my_rank": None,
                "my_value": None,
            }

        # Rank everyone
        ranked = sorted(
            per_user.items(),
            key=lambda kv: (-kv[1]["ghg"], -kv[1]["kg"], kv[0]),  # ghg desc, kg desc, id asc as tiebreak
        )
        total_users = len(ranked)

        # Top N user IDs → bulk fetch user records (name + avatar)
        top_user_ids = [uid for uid, _ in ranked[:limit]]
        users_map: dict[int, RewardUser] = {
            u.id: u for u in self.db.query(RewardUser).filter(RewardUser.id.in_(top_user_ids)).all()
        }

        items = []
        for idx, (uid, acc) in enumerate(ranked[:limit]):
            user = users_map.get(uid)
            name = None
            if user:
                name = user.display_name or user.line_display_name
            if not name:
                name = f"User #{uid}"
            items.append({
                "rank": idx + 1,
                "reward_user_id": uid,
                "display_name": name,
                "line_picture_url": user.line_picture_url if user else None,
                "ghg_kg_co2": round(acc["ghg"], 2),
                "kg_recycled": round(acc["kg"], 2),
                "claims_count": acc["claims"],
            })

        # Compute my_rank — walk full ranked list (cheap; capped by org size)
        my_rank = None
        my_value = None
        if viewer_user_id is not None:
            for idx, (uid, acc) in enumerate(ranked):
                if uid == viewer_user_id:
                    my_rank = idx + 1
                    my_value = {
                        "ghg_kg_co2": round(acc["ghg"], 2),
                        "kg_recycled": round(acc["kg"], 2),
                        "claims_count": acc["claims"],
                    }
                    break

        return {
            "period": period,
            "metric": "ghg",
            "items": items,
            "total_users": total_users,
            "my_rank": my_rank,
            "my_value": my_value,
        }
