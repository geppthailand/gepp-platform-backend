"""
Campaign impact / lift analysis — BE Sonnet 2, Sprint 2.

Public API:
    compute_impact(db, campaign_id, window_days=30) -> dict

Algorithm:
  1. Load campaign's started_at.
  2. Derive recipient set from crm_campaign_deliveries (sent/delivered/opened/clicked).
  3. Count engagement events (6 types) in the [started_at - window_days, started_at] window.
  4. Count same events in [started_at, started_at + window_days].
  5. Compute lift % per event type and an aggregate total lift.

Response shape (documented for FE Sonnet 2):
  {
    "campaignId": int,
    "windowDays": int,
    "recipientCount": int,
    "started": bool,           -- False if campaign has never run
    "partial": bool,           -- True when after-window is still in progress
    "actualAfterDays": int,    -- How many days of after-window have elapsed
    "before": {
      "loginCount": int,
      "transactionCount": int,
      "qrCount": int,
      "traceabilityCount": int,
      "griCount": int,
      "rewardCount": int,
    },
    "after": { same keys },
    "lift": { same keys, values are float (%) },
    "totalEventsBefore": int,
    "totalEventsAfter": int,
    "totalLiftPct": float,     -- None when before == 0 (undefined lift)
  }
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import NotFoundException

logger = logging.getLogger(__name__)

# Engagement event types that map to our 6 engagement dimensions.
# Keys → the dimension name we return; values → list of crm_events.event_type values.
_DIMENSION_EVENTS: Dict[str, list] = {
    "loginCount":        ["user_login"],
    "transactionCount":  ["transaction_created", "transaction_qr_input"],
    "qrCount":           ["transaction_qr_input"],
    "traceabilityCount": ["traceability_created", "transport_confirmed", "disposal_recorded"],
    "griCount":          ["gri_data_submitted"],
    "rewardCount":       ["reward_claimed", "reward_redeemed"],
}

# Flat list of all relevant event types (for the single COUNT(*) query)
_ALL_EVENT_TYPES = sorted({et for ets in _DIMENSION_EVENTS.values() for et in ets})


def _count_events_by_dimension(
    db: Session,
    user_ids: list,
    from_dt: datetime,
    to_dt: datetime,
) -> Dict[str, int]:
    """
    Return a dict {dimensionName: count} for the given recipients and time window.

    Uses a single query with conditional COUNT(*) FILTER to avoid N+1.
    If user_ids is empty, all counts are 0.
    """
    if not user_ids:
        return {k: 0 for k in _DIMENSION_EVENTS}

    # Build FILTER clauses for each dimension
    filter_clauses = []
    for dim, event_types in _DIMENSION_EVENTS.items():
        escaped = ", ".join(f"'{et}'" for et in event_types)
        filter_clauses.append(
            f"COUNT(*) FILTER (WHERE event_type IN ({escaped})) AS {dim}"
        )

    # user_ids is a Python list; we pass as a PostgreSQL ANY array
    sql = text(f"""
        SELECT {', '.join(filter_clauses)}
        FROM crm_events
        WHERE user_location_id = ANY(:uids)
          AND occurred_at >= :from_dt
          AND occurred_at < :to_dt
    """)
    row = db.execute(sql, {
        'uids': user_ids,
        'from_dt': from_dt,
        'to_dt': to_dt,
    }).fetchone()

    if not row:
        return {k: 0 for k in _DIMENSION_EVENTS}

    return {dim: int(row[i] or 0) for i, dim in enumerate(_DIMENSION_EVENTS)}


def _lift_pct(before: int, after: int) -> Optional[float]:
    """Return (after-before)/before*100 as a float, or None if before==0."""
    if before == 0:
        return None
    return round((after - before) / before * 100, 2)


def compute_impact(
    db: Session,
    campaign_id: int,
    window_days: int = 30,
) -> Dict[str, Any]:
    """
    Compute engagement lift for campaign_id over a symmetric window around started_at.

    Args:
        db:           SQLAlchemy session.
        campaign_id:  PK of crm_campaigns.
        window_days:  Days before and after started_at to compare.

    Returns:
        Impact dict (see module docstring for full shape).

    Raises:
        NotFoundException: if campaign doesn't exist.
    """
    # ── 1. Load campaign ──────────────────────────────────────────────────────
    camp_row = db.execute(
        text("""
            SELECT id, started_at
            FROM crm_campaigns
            WHERE id = :id AND deleted_date IS NULL
        """),
        {'id': campaign_id},
    ).fetchone()

    if not camp_row:
        raise NotFoundException(f"Campaign {campaign_id} not found")

    started_at: Optional[datetime] = camp_row[1]

    # ── 2. Not-started fast path ───────────────────────────────────────────────
    if started_at is None:
        zero_dims = {k: 0 for k in _DIMENSION_EVENTS}
        return {
            "campaignId":      campaign_id,
            "windowDays":      window_days,
            "recipientCount":  0,
            "started":         False,
            "partial":         False,
            "actualAfterDays": 0,
            "before":          zero_dims,
            "after":           zero_dims,
            "lift":            {k: None for k in _DIMENSION_EVENTS},
            "totalEventsBefore": 0,
            "totalEventsAfter":  0,
            "totalLiftPct":    None,
        }

    # Normalise to UTC
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    window_delta = timedelta(days=window_days)

    before_from = started_at - window_delta
    before_to   = started_at                          # exclusive upper bound
    after_from  = started_at
    after_to    = started_at + window_delta           # may be in the future

    # ── 3. Determine if after-window is complete or partial ───────────────────
    if now_utc >= after_to:
        partial = False
        actual_after_days = window_days
    else:
        partial = True
        actual_after_days = max(0, (now_utc - after_from).days)
        after_to = now_utc  # clamp to now so we count real data only

    # ── 4. Get recipient set ───────────────────────────────────────────────────
    uid_rows = db.execute(
        text("""
            SELECT DISTINCT user_location_id
            FROM crm_campaign_deliveries
            WHERE campaign_id = :cid
              AND status IN ('sent', 'delivered', 'opened', 'clicked')
              AND user_location_id IS NOT NULL
        """),
        {'cid': campaign_id},
    ).fetchall()
    recipient_ids = [r[0] for r in uid_rows]
    recipient_count = len(recipient_ids)

    # ── 5. Count engagement per window ────────────────────────────────────────
    before_dims = _count_events_by_dimension(db, recipient_ids, before_from, before_to)
    after_dims  = _count_events_by_dimension(db, recipient_ids, after_from,  after_to)

    # ── 6. Compute lift ───────────────────────────────────────────────────────
    lift_dims = {
        k: _lift_pct(before_dims[k], after_dims[k])
        for k in _DIMENSION_EVENTS
    }

    total_before = sum(before_dims.values())
    total_after  = sum(after_dims.values())
    total_lift   = _lift_pct(total_before, total_after)

    return {
        "campaignId":        campaign_id,
        "windowDays":        window_days,
        "recipientCount":    recipient_count,
        "started":           True,
        "partial":           partial,
        "actualAfterDays":   actual_after_days,
        "before":            before_dims,
        "after":             after_dims,
        "lift":              lift_dims,
        "totalEventsBefore": total_before,
        "totalEventsAfter":  total_after,
        "totalLiftPct":      total_lift,
    }
