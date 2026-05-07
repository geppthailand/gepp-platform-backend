"""
CRM Campaign Scheduler — tick function.

Called every minute by `campaign_scheduler_lambda.lambda_handler`.

Public API:
    tick(db, max_campaigns=50, max_events_per_campaign=500) -> dict

Algorithm per call:
  1. Load up to max_campaigns running trigger campaigns, ordered by
     last_trigger_eval_at NULLS FIRST (least-recently evaluated first).
  2. For each campaign, query new crm_events since last_trigger_eval_at.
  3. Per event: apply delay_days guard, property_filters, segment membership,
     cooldown — then call delivery_sender.enqueue_delivery.
  4. Commit after each campaign independently (one bad campaign ≠ rollback all).
  5. Return summary dict.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from .cooldown import check_cooldown, _DEFAULT_COOLDOWN_DAYS
from . import delivery_sender
from .logger import crm_log, new_correlation_id
from .property_filter import matches as _prop_matches

logger = logging.getLogger(__name__)


def tick(
    db: Session,
    max_campaigns: int = 50,
    max_events_per_campaign: int = 500,
) -> Dict[str, Any]:
    """
    Evaluate all running trigger campaigns and fan out deliveries for matching events.

    Returns a summary dict:
        {
            "campaigns_processed":   int,
            "events_evaluated":      int,
            "deliveries_enqueued":   int,
            "deliveries_skipped":    int,
        }
    """
    summary = {
        "campaigns_processed": 0,
        "events_evaluated":    0,
        "deliveries_enqueued": 0,
        "deliveries_skipped":  0,
    }
    _t0  = time.monotonic()
    _cid = new_correlation_id()

    # ── 1. Select campaigns to evaluate ──────────────────────────────────────
    campaign_rows = db.execute(
        text("""
            SELECT id, organization_id, name, campaign_type,
                   trigger_event, trigger_config, segment_id,
                   template_id, status,
                   started_at, last_trigger_eval_at,
                   send_from_name, send_from_email, reply_to
            FROM crm_campaigns
            WHERE status = 'running'
              AND campaign_type = 'trigger'
              AND deleted_date IS NULL
            ORDER BY last_trigger_eval_at NULLS FIRST
            LIMIT :lim
        """),
        {"lim": max_campaigns},
    ).fetchall()

    crm_log("scheduler.tick.start",
            campaigns_to_process=len(campaign_rows),
            correlation_id=_cid)

    for camp_row in campaign_rows:
        campaign = _row_to_campaign(camp_row)
        campaign_id = campaign["id"]
        try:
            c_enqueued, c_skipped, c_events = _process_campaign(
                db, campaign, max_events_per_campaign
            )
            summary["campaigns_processed"] += 1
            summary["events_evaluated"]    += c_events
            summary["deliveries_enqueued"] += c_enqueued
            summary["deliveries_skipped"]  += c_skipped
        except Exception as exc:
            # Isolate bad campaigns — log and continue
            logger.error(
                "campaign_scheduler: error processing campaign=%s: %s",
                campaign_id, exc, exc_info=True,
            )
            try:
                db.rollback()
            except Exception:
                pass

    crm_log("scheduler.tick.done",
            deliveries_enqueued=summary["deliveries_enqueued"],
            campaigns_processed=summary["campaigns_processed"],
            latency_ms=int((time.monotonic() - _t0) * 1000),
            correlation_id=_cid)

    return summary


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _process_campaign(
    db: Session,
    campaign: Dict[str, Any],
    max_events: int,
) -> tuple:
    """
    Process one trigger campaign.  Commits after the full campaign is done.

    Returns (enqueued, skipped, events_evaluated).
    """
    campaign_id     = campaign["id"]
    trigger_event   = campaign["trigger_event"] or ""
    trigger_config  = campaign["trigger_config"] or {}
    segment_id      = campaign["segment_id"]
    org_id          = campaign["organization_id"]
    last_eval_at    = campaign["last_trigger_eval_at"]
    started_at      = campaign["started_at"]

    # ── Determine lookback window ─────────────────────────────────────────
    if last_eval_at:
        since = last_eval_at
    elif started_at:
        since = started_at
    else:
        since = datetime.now(timezone.utc) - timedelta(days=7)

    # ── Query matching events ─────────────────────────────────────────────
    # Note: property_filters are now evaluated in-memory via property_filter.matches()
    # so we can support richer operators (gt/lt/in/contains/exists/AND/OR).
    # We still push event_type + since to SQL for efficiency; the property filter
    # runs as a post-fetch Python filter on the returned rows.
    prop_filters = trigger_config.get("property_filters") or None

    params: Dict[str, Any] = {
        "event_type": trigger_event,
        "since":      since,
        "lim":        max_events,
    }

    event_rows = db.execute(
        text("""
            SELECT e.id, e.user_location_id, e.organization_id,
                   e.properties, e.occurred_at,
                   ul.email AS user_email
            FROM crm_events e
            LEFT JOIN user_locations ul
                   ON ul.id = e.user_location_id
                  AND ul.deleted_date IS NULL
            WHERE e.event_type   = :event_type
              AND e.occurred_at  > :since
            ORDER BY e.occurred_at ASC
            LIMIT :lim
        """),
        params,
    ).fetchall()

    # ── In-memory property filter (rich operators via property_filter module) ─
    if prop_filters and event_rows:
        event_rows = [
            evt for evt in event_rows
            if _prop_matches(evt[3] or {}, prop_filters)
        ]

    enqueued = 0
    skipped  = 0

    delay_days    = int(trigger_config.get("delay_days") or 0)
    cooldown_days = int(trigger_config.get("cooldown_days") or _DEFAULT_COOLDOWN_DAYS)
    now_utc       = datetime.now(timezone.utc)

    for evt in event_rows:
        event_id         = evt[0]
        user_location_id = evt[1]
        evt_org_id       = evt[2] or org_id
        evt_occurred     = evt[4]
        user_email       = evt[5]

        # ── delay_days guard ─────────────────────────────────────────────
        if delay_days > 0:
            if evt_occurred.tzinfo is None:
                evt_occurred = evt_occurred.replace(tzinfo=timezone.utc)
            age_days = (now_utc - evt_occurred).total_seconds() / 86400
            if age_days < delay_days:
                skipped += 1
                logger.debug(
                    "scheduler: campaign=%s event=%s skipped — delay not elapsed (%.1fd < %dd)",
                    campaign_id, event_id, age_days, delay_days,
                )
                continue

        # ── Segment membership check ─────────────────────────────────────
        if segment_id and user_location_id:
            member_row = db.execute(
                text("""
                    SELECT 1 FROM crm_segment_members
                    WHERE segment_id  = :sid
                      AND member_id   = :uid
                      AND member_type = 'user'
                    LIMIT 1
                """),
                {"sid": segment_id, "uid": user_location_id},
            ).fetchone()
            if not member_row:
                skipped += 1
                logger.debug(
                    "scheduler: campaign=%s event=%s skipped — user=%s not in segment=%s",
                    campaign_id, event_id, user_location_id, segment_id,
                )
                continue

        # ── Cooldown check ───────────────────────────────────────────────
        if user_location_id:
            is_blocked, _ = check_cooldown(db, campaign_id, user_location_id, cooldown_days)
            if is_blocked:
                skipped += 1
                logger.debug(
                    "scheduler: campaign=%s event=%s skipped — cooldown user=%s",
                    campaign_id, event_id, user_location_id,
                )
                continue

        # ── Resolve recipient email ───────────────────────────────────────
        recipient_email = user_email
        if not recipient_email and user_location_id:
            email_row = db.execute(
                text("SELECT email FROM user_locations WHERE id = :uid AND deleted_date IS NULL"),
                {"uid": user_location_id},
            ).fetchone()
            recipient_email = email_row[0] if email_row else None

        if not recipient_email:
            skipped += 1
            logger.warning(
                "scheduler: campaign=%s event=%s skipped — no email for user=%s",
                campaign_id, event_id, user_location_id,
            )
            continue

        # ── Enqueue delivery ─────────────────────────────────────────────
        result = delivery_sender.enqueue_delivery(
            db,
            campaign,
            user_location_id=user_location_id,
            recipient_email=recipient_email,
            render_context={"event_properties": evt[3] or {}},
        )

        if result.get("skipped"):
            skipped += 1
        else:
            enqueued += 1

    # ── Advance last_trigger_eval_at ──────────────────────────────────────
    db.execute(
        text("""
            UPDATE crm_campaigns
            SET last_trigger_eval_at = NOW(),
                updated_date = NOW()
            WHERE id = :id
        """),
        {"id": campaign_id},
    )
    db.commit()

    logger.info(
        "scheduler: campaign=%s processed %d events → enqueued=%d skipped=%d",
        campaign_id, len(event_rows), enqueued, skipped,
    )
    return enqueued, skipped, len(event_rows)


def retry_soft_bounces(
    db: Session,
    max_retries: int = 3,
    max_per_tick: int = 100,
) -> Dict[str, Any]:
    """
    Retry deliveries that soft-bounced or failed transiently.

    Selects rows where:
      - next_retry_at IS NOT NULL AND next_retry_at < NOW()
      - retry_count < max_retries
      - status IN ('soft_bounced', 'failed')

    For each delivery:
      - Re-fetches the associated campaign to build the campaign dict.
      - Calls delivery_sender.enqueue_delivery with existing_delivery_id so the
        SAME row is updated (retry_count incremented by enqueue_delivery).
      - If retry_count reaches max_retries AND the send fails again, marks the
        row permanently as 'failed' with next_retry_at = NULL.

    Returns a summary dict:
        {
            "retried":   int,   # attempts made
            "succeeded": int,   # transitioned to 'sent'
            "exhausted": int,   # reached max_retries, permanently failed
            "skipped":   int,   # cooldown / unsub etc.
        }
    """
    summary = {"retried": 0, "succeeded": 0, "exhausted": 0, "skipped": 0}

    rows = db.execute(
        text("""
            SELECT d.id, d.campaign_id, d.user_location_id, d.recipient_email,
                   d.retry_count,
                   c.id         AS c_id,
                   c.organization_id,
                   c.name,
                   c.campaign_type,
                   c.trigger_event,
                   c.trigger_config,
                   c.segment_id,
                   c.template_id,
                   c.status     AS c_status,
                   c.started_at,
                   c.last_trigger_eval_at,
                   c.send_from_name,
                   c.send_from_email,
                   c.reply_to
            FROM crm_campaign_deliveries d
            JOIN crm_campaigns c ON c.id = d.campaign_id
            WHERE d.next_retry_at IS NOT NULL
              AND d.next_retry_at < NOW()
              AND d.retry_count   < :max_retries
              AND d.status        IN ('soft_bounced', 'failed')
            ORDER BY d.next_retry_at ASC
            LIMIT :limit
        """),
        {"max_retries": max_retries, "limit": max_per_tick},
    ).fetchall()

    for row in rows:
        delivery_id  = row[0]
        retry_count  = row[4]

        # Reconstruct a campaign dict from the JOIN columns
        def _tz(dt):
            if dt and getattr(dt, "tzinfo", None) is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        campaign = {
            "id":                   row[5],
            "organization_id":      row[6],
            "name":                 row[7],
            "campaign_type":        row[8],
            "trigger_event":        row[9],
            "trigger_config":       row[10] or {},
            "segment_id":           row[11],
            "template_id":          row[12],
            "status":               row[13],
            "started_at":           _tz(row[14]),
            "last_trigger_eval_at": _tz(row[15]),
            "send_from_name":       row[16],
            "send_from_email":      row[17],
            "reply_to":             row[18],
        }

        summary["retried"] += 1
        try:
            result = delivery_sender.enqueue_delivery(
                db,
                campaign,
                user_location_id=row[2],
                recipient_email=row[3],
                render_context={},
                existing_delivery_id=delivery_id,
            )
        except Exception as exc:
            logger.error(
                "retry_soft_bounces: unexpected error for delivery=%s: %s",
                delivery_id, exc, exc_info=True,
            )
            # Bump retry_count + clear next_retry_at so we don't loop on crash
            db.execute(
                text("""
                    UPDATE crm_campaign_deliveries
                    SET retry_count    = retry_count + 1,
                        next_retry_at  = NULL,
                        status         = CASE WHEN retry_count + 1 >= :max_r THEN 'failed' ELSE status END,
                        updated_date   = NOW()
                    WHERE id = :id
                """),
                {"id": delivery_id, "max_r": max_retries},
            )
            db.commit()
            summary["exhausted"] += 1
            continue

        if result.get("skipped"):
            summary["skipped"] += 1
        elif result.get("error"):
            # enqueue_delivery returned an error dict — check exhaustion
            new_count = retry_count + 1
            if new_count >= max_retries:
                # Permanently failed — clear next_retry_at
                db.execute(
                    text("""
                        UPDATE crm_campaign_deliveries
                        SET status = 'failed', next_retry_at = NULL, updated_date = NOW()
                        WHERE id = :id
                    """),
                    {"id": delivery_id},
                )
                db.commit()
                summary["exhausted"] += 1
            else:
                summary["skipped"] += 1
        else:
            status = result.get("status", "")
            if status == "sent":
                # Clear next_retry_at on successful send
                db.execute(
                    text("""
                        UPDATE crm_campaign_deliveries
                        SET next_retry_at = NULL, updated_date = NOW()
                        WHERE id = :id
                    """),
                    {"id": delivery_id},
                )
                db.commit()
                summary["succeeded"] += 1
            else:
                # Still failed after retry — check exhaustion
                new_count = retry_count + 1
                if new_count >= max_retries:
                    db.execute(
                        text("""
                            UPDATE crm_campaign_deliveries
                            SET status = 'failed', next_retry_at = NULL, updated_date = NOW()
                            WHERE id = :id
                        """),
                        {"id": delivery_id},
                    )
                    db.commit()
                    summary["exhausted"] += 1
                else:
                    summary["skipped"] += 1

        logger.info(
            "retry_soft_bounces: delivery=%s retry_count=%s result=%s",
            delivery_id, retry_count, result.get("status", result),
        )

    return summary


def _row_to_campaign(row) -> Dict[str, Any]:
    """Convert a raw DB row from the campaign SELECT into a dict usable by delivery_sender."""
    last_eval = row[10]
    started   = row[9]

    def _tz(dt):
        if dt and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    return {
        "id":                   row[0],
        "organization_id":      row[1],
        "name":                 row[2],
        "campaign_type":        row[3],
        "trigger_event":        row[4],
        "trigger_config":       row[5] or {},
        "segment_id":           row[6],
        "template_id":          row[7],
        "status":               row[8],
        "started_at":           _tz(started),
        "last_trigger_eval_at": _tz(last_eval),
        "send_from_name":       row[11],
        "send_from_email":      row[12],
        "reply_to":             row[13],
    }
