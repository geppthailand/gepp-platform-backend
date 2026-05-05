"""
CRM health endpoint — GET /api/admin/crm-health

Returns a composite JSON object describing the live state of every CRM subsystem:
  • scheduler       — last trigger-campaign tick freshness
  • profileRefresh  — last nightly profile rollup age
  • events          — last crm_events row age
  • deliveries      — stuck/failed/pending queue depth
  • config          — env-var presence (bool, never the value)
  • overall         — worst-of all sub-statuses

Thresholds (chosen to give ~30 min grace above the expected cadence):
  scheduler:
    healthy   < 120 s since last tick (scheduler runs every 60 s)
    degraded  120–300 s
    unhealthy > 300 s   (or no running trigger campaigns → healthy + note)
  profileRefresh:
    healthy   < 26 h  (runs nightly, 24 h cadence + 2 h grace)
    degraded  26–48 h
    unhealthy ≥ 48 h  (or never run → unhealthy)
  events:
    healthy   < 3600 s  (1 h)
    degraded  1–24 h
    unhealthy > 24 h    (or no events ever → degraded, not critical)
  deliveries:
    healthy   stuckSending24h == 0 AND failed24h < 10
    degraded  stuckSending24h > 0 OR failed24h in [10, 50)
    unhealthy stuckSending24h > 5  OR failed24h >= 50
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Threshold constants ───────────────────────────────────────────────────────

_SCHEDULER_DEGRADED_S   = 120    # 2 minutes
_SCHEDULER_UNHEALTHY_S  = 300    # 5 minutes

_PROFILE_HEALTHY_H      = 26
_PROFILE_DEGRADED_H     = 48

_EVENTS_HEALTHY_S       = 3600       # 1 hour
_EVENTS_UNHEALTHY_S     = 86400      # 24 hours

_DELIVERY_STUCK_DEGRADED    = 1
_DELIVERY_STUCK_UNHEALTHY   = 5
_DELIVERY_FAILED_DEGRADED   = 10
_DELIVERY_FAILED_UNHEALTHY  = 50


# ── Sub-status helpers ────────────────────────────────────────────────────────

_STATUS_RANK = {"healthy": 0, "degraded": 1, "unhealthy": 2}


def _worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))


def _seconds_status(seconds: Optional[float], degraded_threshold: float, unhealthy_threshold: float) -> str:
    if seconds is None:
        return "unhealthy"
    if seconds < degraded_threshold:
        return "healthy"
    if seconds < unhealthy_threshold:
        return "degraded"
    return "unhealthy"


# ── Sub-check implementations ─────────────────────────────────────────────────

def _check_scheduler(db: Session) -> Dict[str, Any]:
    """
    last_trigger_eval_at from running trigger campaigns.
    If no running trigger campaigns exist the scheduler has nothing to do → healthy.
    """
    row = db.execute(
        text("""
            SELECT MAX(last_trigger_eval_at)
            FROM crm_campaigns
            WHERE campaign_type = 'trigger'
              AND status IN ('running', 'completed')
              AND deleted_date IS NULL
        """)
    ).fetchone()

    last_tick_at: Optional[datetime] = row[0] if row else None

    # Check whether any running trigger campaigns exist at all
    running_count = db.execute(
        text("""
            SELECT COUNT(*) FROM crm_campaigns
            WHERE campaign_type = 'trigger' AND status = 'running'
              AND deleted_date IS NULL
        """)
    ).scalar() or 0

    if running_count == 0:
        return {
            "lastTickAt": last_tick_at.isoformat() if last_tick_at else None,
            "secondsSinceLastTick": None,
            "lagSeconds": 0,
            "status": "healthy",
            "note": "no running trigger campaigns",
        }

    now_utc = datetime.now(timezone.utc)
    if last_tick_at is None:
        seconds_since = None
    else:
        if last_tick_at.tzinfo is None:
            last_tick_at = last_tick_at.replace(tzinfo=timezone.utc)
        seconds_since = (now_utc - last_tick_at).total_seconds()

    status = _seconds_status(seconds_since, _SCHEDULER_DEGRADED_S, _SCHEDULER_UNHEALTHY_S)
    lag = max(0, (seconds_since or 0) - 60)  # expected cadence is 60s

    return {
        "lastTickAt": last_tick_at.isoformat() if last_tick_at else None,
        "secondsSinceLastTick": int(seconds_since) if seconds_since is not None else None,
        "lagSeconds": int(lag),
        "status": status,
    }


def _check_profile_refresh(db: Session) -> Dict[str, Any]:
    """Age of the most recent nightly profile rollup."""
    row = db.execute(
        text("SELECT MAX(last_profile_refresh_at) FROM crm_org_profiles")
    ).fetchone()

    last_refresh_at: Optional[datetime] = row[0] if row else None

    if last_refresh_at is None:
        return {
            "lastRefreshAt": None,
            "ageHours": None,
            "status": "unhealthy",
            "note": "profile refresher has never run",
        }

    now_utc = datetime.now(timezone.utc)
    if last_refresh_at.tzinfo is None:
        last_refresh_at = last_refresh_at.replace(tzinfo=timezone.utc)
    age_hours = (now_utc - last_refresh_at).total_seconds() / 3600.0

    if age_hours < _PROFILE_HEALTHY_H:
        status = "healthy"
    elif age_hours < _PROFILE_DEGRADED_H:
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "lastRefreshAt": last_refresh_at.isoformat(),
        "ageHours": round(age_hours, 1),
        "status": status,
    }


def _check_events(db: Session) -> Dict[str, Any]:
    """Staleness of the most recent crm_events row."""
    row = db.execute(
        text("SELECT MAX(occurred_at), COUNT(*) FROM crm_events")
    ).fetchone()

    last_event_at: Optional[datetime] = row[0] if row else None
    total_rows = int(row[1] or 0) if row else 0

    if last_event_at is None:
        return {
            "totalRows": total_rows,
            "lastEventAt": None,
            "secondsSinceLastEvent": None,
            "status": "degraded",
            "note": "no events recorded yet",
        }

    now_utc = datetime.now(timezone.utc)
    if last_event_at.tzinfo is None:
        last_event_at = last_event_at.replace(tzinfo=timezone.utc)
    seconds_since = (now_utc - last_event_at).total_seconds()

    status = _seconds_status(seconds_since, _EVENTS_HEALTHY_S, _EVENTS_UNHEALTHY_S)

    return {
        "totalRows": total_rows,
        "lastEventAt": last_event_at.isoformat(),
        "secondsSinceLastEvent": int(seconds_since),
        "status": status,
    }


def _check_deliveries(db: Session) -> Dict[str, Any]:
    """Queue depth — pending, stuck-sending, and failed deliveries in last 24 h."""
    row = db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'pending'
                      AND created_date > NOW() - INTERVAL '24 hours'
                )                                                  AS pending_24h,
                COUNT(*) FILTER (
                    WHERE status = 'sending'
                      AND COALESCE(updated_date, created_date) < NOW() - INTERVAL '5 minutes'
                )                                                  AS stuck_sending,
                COUNT(*) FILTER (
                    WHERE status = 'failed'
                      AND created_date > NOW() - INTERVAL '24 hours'
                )                                                  AS failed_24h
            FROM crm_campaign_deliveries
        """)
    ).fetchone()

    pending   = int(row[0] or 0) if row else 0
    stuck     = int(row[1] or 0) if row else 0
    failed    = int(row[2] or 0) if row else 0

    if stuck >= _DELIVERY_STUCK_UNHEALTHY or failed >= _DELIVERY_FAILED_UNHEALTHY:
        status = "unhealthy"
    elif stuck >= _DELIVERY_STUCK_DEGRADED or failed >= _DELIVERY_FAILED_DEGRADED:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "pending24h": pending,
        "stuckSending24h": stuck,
        "failed24h": failed,
        "status": status,
    }


def _check_config() -> Dict[str, Any]:
    """Check required env vars are set (bool only — never expose values)."""
    return {
        "mailchimpWebhookKeyConfigured": bool(os.environ.get("MAILCHIMP_WEBHOOK_KEY")),
        "openrouterKeyConfigured": bool(os.environ.get("OPENROUTER_API_KEY")),
        "crmUnsubSecretConfigured": bool(os.environ.get("CRM_UNSUB_SECRET")),
    }


# ── Public entry point ────────────────────────────────────────────────────────

def get_crm_health(db: Session) -> Dict[str, Any]:
    """
    Collect all sub-checks and return the composite health document.
    Each sub-check is guarded so one DB failure doesn't hide the others.
    """
    results: Dict[str, Any] = {}

    def _safe(key: str, fn, *args, **kwargs):
        try:
            results[key] = fn(*args, **kwargs)
        except Exception as exc:
            logger.error("crm-health: sub-check '%s' failed: %s", key, exc)
            results[key] = {"status": "unhealthy", "error": str(exc)}

    _safe("scheduler",      _check_scheduler,      db)
    _safe("profileRefresh", _check_profile_refresh, db)
    _safe("events",         _check_events,          db)
    _safe("deliveries",     _check_deliveries,      db)
    results["config"] = _check_config()   # no DB call — never fails

    sub_statuses = [v.get("status", "unhealthy") for v in results.values() if isinstance(v, dict) and "status" in v]
    results["overall"] = _worst(*sub_statuses) if sub_statuses else "unhealthy"

    return results
