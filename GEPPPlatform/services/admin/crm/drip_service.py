"""
CRM Drip Sequences service — Sprint 10.

Non-negotiables enforced here:
  - All SQL via text() + bind params.  No string interpolation.
  - enroll() is idempotent: returns existing active enrollment if already enrolled.
  - tick_enrollments() uses SELECT ... FOR UPDATE SKIP LOCKED to avoid races.
  - Auto-enrollment triggered by lead_created / lead_status_changed events.
  - On exception per-enrollment: status='errored', crm_log, continue.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from ....exceptions import BadRequestException, NotFoundException
from .logger import crm_log, new_correlation_id
from .property_filter import matches as _prop_matches
from . import delivery_sender

logger = logging.getLogger(__name__)

# Valid status transitions
_VALID_STATUSES = {'draft', 'active', 'paused', 'archived'}
_STATUS_TRANSITIONS = {
    'draft':    {'active', 'archived'},
    'active':   {'paused', 'archived'},
    'paused':   {'active', 'archived'},
    'archived': set(),
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_json(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val)


def _serialize(row) -> Dict[str, Any]:
    d = dict(row._mapping)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# ─── List / Get ──────────────────────────────────────────────────────────────

def list_sequences(
    db: Session,
    org_id: Optional[int],
    filters: Dict[str, Any],
    page: int = 1,
    page_size: int = 25,
) -> Dict[str, Any]:
    """org_id=None bypasses org filter (super-admin only — enforced in handler)."""
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    offset = (page - 1) * page_size

    where = ["deleted_date IS NULL"]
    params: Dict[str, Any] = {}
    if org_id is not None:
        where.append("organization_id = :org_id")
        params["org_id"] = org_id

    if filters.get("status"):
        where.append("status = :status")
        params["status"] = filters["status"]
    if filters.get("trigger_event"):
        where.append("trigger_event = :trigger_event")
        params["trigger_event"] = filters["trigger_event"]
    if filters.get("q"):
        where.append("(name ILIKE :q OR description ILIKE :q)")
        params["q"] = f"%{filters['q']}%"

    where_sql = " AND ".join(where)
    total = db.execute(
        text(f"SELECT COUNT(*) FROM crm_drip_sequences WHERE {where_sql}"),
        params,
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT id, organization_id, name, description, trigger_event,
                   trigger_config, status, created_by, created_date, updated_date
            FROM crm_drip_sequences
            WHERE {where_sql}
            ORDER BY created_date DESC
            LIMIT :lim OFFSET :off
        """),
        {**params, "lim": page_size, "off": offset},
    ).fetchall()

    return {
        "items": [_serialize(r) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def get_sequence(
    db: Session,
    sequence_id: int,
    org_id: int,
) -> Dict[str, Any]:
    """Return sequence with nested steps list."""
    row = db.execute(
        text("""
            SELECT id, organization_id, name, description, trigger_event,
                   trigger_config, status, created_by, created_date, updated_date
            FROM crm_drip_sequences
            WHERE id = :id AND organization_id = :org_id AND deleted_date IS NULL
        """),
        {"id": sequence_id, "org_id": org_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Drip sequence {sequence_id} not found")

    seq = _serialize(row)
    seq["steps"] = _get_steps(db, sequence_id)
    return seq


def _get_steps(db: Session, sequence_id: int) -> List[Dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, sequence_id, step_index, template_id, delay_days, delay_hours, skip_filter
            FROM crm_drip_steps
            WHERE sequence_id = :seq_id
            ORDER BY step_index ASC
        """),
        {"seq_id": sequence_id},
    ).fetchall()
    return [_serialize(r) for r in rows]


# ─── Create / Update / Delete ────────────────────────────────────────────────

def create_sequence(
    db: Session,
    org_id: int,
    data: Dict[str, Any],
    created_by: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a drip sequence with optional initial steps.
    data shape: {name, description?, triggerEvent?, triggerConfig?, steps?: [{templateId, delayDays, delayHours, skipFilter?}]}
    """
    name = (data.get("name") or "").strip()
    if not name:
        raise BadRequestException("name is required")

    now = _now()
    row = db.execute(
        text("""
            INSERT INTO crm_drip_sequences
                (organization_id, name, description, trigger_event, trigger_config,
                 status, created_by, created_date, updated_date)
            VALUES
                (:org_id, :name, :desc, :trigger_event, CAST(:trigger_config AS jsonb),
                 'draft', :created_by, :now, :now)
            RETURNING id
        """),
        {
            "org_id":         org_id,
            "name":           name,
            "desc":           data.get("description") or None,
            "trigger_event":  data.get("triggerEvent") or data.get("trigger_event") or None,
            "trigger_config": _to_json(data.get("triggerConfig") or data.get("trigger_config")),
            "created_by":     created_by or None,
            "now":            now,
        },
    ).fetchone()
    db.commit()

    sequence_id = row[0]
    _replace_steps(db, sequence_id, data.get("steps") or [])
    return get_sequence(db, sequence_id, org_id)


def update_sequence(
    db: Session,
    sequence_id: int,
    org_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Update sequence fields + atomically replace steps (DELETE+INSERT)."""
    existing = get_sequence(db, sequence_id, org_id)
    if existing["status"] == "archived":
        raise BadRequestException("Cannot update an archived drip sequence")

    now = _now()
    db.execute(
        text("""
            UPDATE crm_drip_sequences
            SET name           = COALESCE(:name, name),
                description    = COALESCE(:desc, description),
                trigger_event  = COALESCE(:trigger_event, trigger_event),
                trigger_config = COALESCE(CAST(:trigger_config AS jsonb), trigger_config),
                updated_date   = :now
            WHERE id = :id AND organization_id = :org_id AND deleted_date IS NULL
        """),
        {
            "id":             sequence_id,
            "org_id":         org_id,
            "name":           (data.get("name") or "").strip() or None,
            "desc":           data.get("description"),
            "trigger_event":  data.get("triggerEvent") or data.get("trigger_event"),
            "trigger_config": _to_json(data.get("triggerConfig") or data.get("trigger_config")),
            "now":            now,
        },
    )
    db.commit()

    if "steps" in data:
        _replace_steps(db, sequence_id, data["steps"])

    return get_sequence(db, sequence_id, org_id)


def delete_sequence(
    db: Session,
    sequence_id: int,
    org_id: int,
) -> Dict[str, Any]:
    """Soft-delete: sets deleted_date. Stops active enrollments."""
    now = _now()
    result = db.execute(
        text("""
            UPDATE crm_drip_sequences
            SET deleted_date = :now, updated_date = :now, status = 'archived'
            WHERE id = :id AND organization_id = :org_id AND deleted_date IS NULL
            RETURNING id
        """),
        {"id": sequence_id, "org_id": org_id, "now": now},
    ).fetchone()
    if not result:
        raise NotFoundException(f"Drip sequence {sequence_id} not found")

    # Stop active enrollments
    db.execute(
        text("""
            UPDATE crm_drip_enrollments
            SET status = 'stopped'
            WHERE sequence_id = :seq_id AND status = 'active'
        """),
        {"seq_id": sequence_id},
    )
    db.commit()
    return {"id": sequence_id, "deleted": True}


def set_status(
    db: Session,
    sequence_id: int,
    org_id: int,
    new_status: str,
) -> Dict[str, Any]:
    """Transition sequence status.  Validates allowed transitions."""
    if new_status not in _VALID_STATUSES:
        raise BadRequestException(f"Invalid status '{new_status}'")

    seq = get_sequence(db, sequence_id, org_id)
    current = seq["status"]
    allowed = _STATUS_TRANSITIONS.get(current, set())
    if new_status not in allowed and new_status != current:
        raise BadRequestException(
            f"Cannot transition from '{current}' to '{new_status}'"
        )

    db.execute(
        text("""
            UPDATE crm_drip_sequences
            SET status = :status, updated_date = NOW()
            WHERE id = :id AND organization_id = :org_id AND deleted_date IS NULL
        """),
        {"id": sequence_id, "org_id": org_id, "status": new_status},
    )
    db.commit()
    return get_sequence(db, sequence_id, org_id)


def _replace_steps(db: Session, sequence_id: int, steps: List[Dict[str, Any]]) -> None:
    """Atomically replace all steps for a sequence (DELETE + INSERT in a tx)."""
    db.execute(
        text("DELETE FROM crm_drip_steps WHERE sequence_id = :seq_id"),
        {"seq_id": sequence_id},
    )
    for idx, step in enumerate(steps):
        db.execute(
            text("""
                INSERT INTO crm_drip_steps
                    (sequence_id, step_index, template_id, delay_days, delay_hours, skip_filter)
                VALUES
                    (:seq_id, :idx, :template_id, :delay_days, :delay_hours, CAST(:skip_filter AS jsonb))
            """),
            {
                "seq_id":      sequence_id,
                "idx":         idx,
                "template_id": step.get("templateId") or step.get("template_id"),
                "delay_days":  int(step.get("delayDays") or step.get("delay_days") or 0),
                "delay_hours": int(step.get("delayHours") or step.get("delay_hours") or 0),
                "skip_filter": _to_json(step.get("skipFilter") or step.get("skip_filter")),
            },
        )
    db.commit()


# ─── Enrollment ──────────────────────────────────────────────────────────────

def enroll(
    db: Session,
    sequence_id: int,
    *,
    lead_id: Optional[int] = None,
    user_location_id: Optional[int] = None,
    org_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Enroll a lead or user in a drip sequence.

    Idempotent: if the lead/user already has an active enrollment in this sequence,
    returns the existing enrollment without creating a duplicate.

    next_step_at = NOW() + first_step_delay (or NOW() if sequence has no steps).
    """
    if not lead_id and not user_location_id:
        raise BadRequestException("Either lead_id or user_location_id is required")

    # Load sequence + steps
    seq_row = db.execute(
        text("""
            SELECT id, status FROM crm_drip_sequences
            WHERE id = :id AND deleted_date IS NULL
        """),
        {"id": sequence_id},
    ).fetchone()
    if not seq_row:
        raise NotFoundException(f"Drip sequence {sequence_id} not found")
    if seq_row[1] not in ('active',):
        raise BadRequestException(f"Cannot enroll in a sequence with status '{seq_row[1]}'")

    # Idempotency: check for existing active enrollment
    if lead_id:
        existing = db.execute(
            text("""
                SELECT id FROM crm_drip_enrollments
                WHERE sequence_id = :seq_id AND lead_id = :lead_id AND status = 'active'
                LIMIT 1
            """),
            {"seq_id": sequence_id, "lead_id": lead_id},
        ).fetchone()
    else:
        existing = db.execute(
            text("""
                SELECT id FROM crm_drip_enrollments
                WHERE sequence_id = :seq_id AND user_location_id = :uid AND status = 'active'
                LIMIT 1
            """),
            {"seq_id": sequence_id, "uid": user_location_id},
        ).fetchone()

    if existing:
        return _get_enrollment(db, existing[0])

    # Compute next_step_at from first step's delay
    first_step = db.execute(
        text("""
            SELECT delay_days, delay_hours FROM crm_drip_steps
            WHERE sequence_id = :seq_id ORDER BY step_index ASC LIMIT 1
        """),
        {"seq_id": sequence_id},
    ).fetchone()

    now = _now()
    if first_step:
        delay = timedelta(days=int(first_step[0] or 0), hours=int(first_step[1] or 0))
        next_step_at = now + delay
    else:
        next_step_at = now

    row = db.execute(
        text("""
            INSERT INTO crm_drip_enrollments
                (sequence_id, lead_id, user_location_id, current_step, next_step_at,
                 status, enrolled_at)
            VALUES
                (:seq_id, :lead_id, :uid, 0, :next_step_at, 'active', :now)
            RETURNING id
        """),
        {
            "seq_id":      sequence_id,
            "lead_id":     lead_id,
            "uid":         user_location_id,
            "next_step_at": next_step_at,
            "now":         now,
        },
    ).fetchone()
    db.commit()
    return _get_enrollment(db, row[0])


def _get_enrollment(db: Session, enrollment_id: int) -> Dict[str, Any]:
    row = db.execute(
        text("""
            SELECT id, sequence_id, lead_id, user_location_id, current_step,
                   next_step_at, status, enrolled_at, completed_at
            FROM crm_drip_enrollments WHERE id = :id
        """),
        {"id": enrollment_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Enrollment {enrollment_id} not found")
    return _serialize(row)


def list_enrollments(
    db: Session,
    sequence_id: int,
    org_id: int,
    page: int = 1,
    page_size: int = 25,
) -> Dict[str, Any]:
    # Verify sequence ownership
    seq = db.execute(
        text("SELECT id FROM crm_drip_sequences WHERE id = :id AND organization_id = :org_id AND deleted_date IS NULL"),
        {"id": sequence_id, "org_id": org_id},
    ).fetchone()
    if not seq:
        raise NotFoundException(f"Drip sequence {sequence_id} not found")

    page = max(1, page)
    page_size = max(1, min(200, page_size))
    offset = (page - 1) * page_size

    total = db.execute(
        text("SELECT COUNT(*) FROM crm_drip_enrollments WHERE sequence_id = :seq_id"),
        {"seq_id": sequence_id},
    ).scalar()

    rows = db.execute(
        text("""
            SELECT id, sequence_id, lead_id, user_location_id, current_step,
                   next_step_at, status, enrolled_at, completed_at
            FROM crm_drip_enrollments
            WHERE sequence_id = :seq_id
            ORDER BY enrolled_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"seq_id": sequence_id, "lim": page_size, "off": offset},
    ).fetchall()

    return {
        "items": [_serialize(r) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


# ─── Scheduler tick ──────────────────────────────────────────────────────────

def tick_enrollments(
    db: Session,
    batch_size: int = 200,
) -> Dict[str, Any]:
    """
    Process due enrollments.

    Algorithm:
    1. SELECT active enrollments WHERE next_step_at <= NOW() FOR UPDATE SKIP LOCKED
    2. For each: load current step, check skip_filter, enqueue delivery if not skipped
    3. Advance current_step; if last step → mark completed; else compute next_step_at
    4. On exception: mark errored, crm_log, continue

    Returns: {processed, advanced, completed, errored}
    """
    summary = {"processed": 0, "advanced": 0, "completed": 0, "errored": 0}
    _cid = new_correlation_id()

    now = _now()

    due_rows = db.execute(
        text("""
            SELECT e.id, e.sequence_id, e.lead_id, e.user_location_id, e.current_step
            FROM crm_drip_enrollments e
            WHERE e.status = 'active'
              AND e.next_step_at <= :now
            ORDER BY e.next_step_at ASC
            LIMIT :batch
            FOR UPDATE SKIP LOCKED
        """),
        {"now": now, "batch": batch_size},
    ).fetchall()

    crm_log("drip.tick.start", due_count=len(due_rows), correlation_id=_cid)

    for enrollment_row in due_rows:
        enrollment_id    = enrollment_row[0]
        sequence_id      = enrollment_row[1]
        lead_id          = enrollment_row[2]
        user_location_id = enrollment_row[3]
        current_step     = enrollment_row[4]

        try:
            _process_enrollment(
                db, enrollment_id, sequence_id,
                lead_id, user_location_id, current_step,
                now, summary,
            )
        except Exception as exc:
            logger.error(
                "drip.tick: error processing enrollment=%s: %s",
                enrollment_id, exc, exc_info=True,
            )
            crm_log("drip.tick.error", enrollment_id=enrollment_id, error=str(exc))
            try:
                db.execute(
                    text("""
                        UPDATE crm_drip_enrollments
                        SET status = 'errored' WHERE id = :id
                    """),
                    {"id": enrollment_id},
                )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
            summary["errored"] += 1

        summary["processed"] += 1

    crm_log("drip.tick.done", **summary, correlation_id=_cid)
    return summary


def _process_enrollment(
    db: Session,
    enrollment_id: int,
    sequence_id: int,
    lead_id: Optional[int],
    user_location_id: Optional[int],
    current_step: int,
    now: datetime,
    summary: Dict[str, Any],
) -> None:
    """Process one enrollment — inner logic separated for clarity."""
    # Load the step at current_step
    step_row = db.execute(
        text("""
            SELECT id, step_index, template_id, delay_days, delay_hours, skip_filter
            FROM crm_drip_steps
            WHERE sequence_id = :seq_id AND step_index = :idx
        """),
        {"seq_id": sequence_id, "idx": current_step},
    ).fetchone()

    if not step_row:
        # No step at this index — sequence completed
        db.execute(
            text("""
                UPDATE crm_drip_enrollments
                SET status = 'completed', completed_at = :now
                WHERE id = :id
            """),
            {"id": enrollment_id, "now": now},
        )
        db.commit()
        summary["completed"] += 1
        return

    template_id  = step_row[2]
    skip_filter  = step_row[5]

    # Check skip_filter against lead/user properties
    if skip_filter:
        props = _load_recipient_props(db, lead_id, user_location_id)
        if _prop_matches(props, skip_filter):
            logger.debug(
                "drip.tick: enrollment=%s step=%s skipped by skip_filter",
                enrollment_id, current_step,
            )
            # Skip this step but advance
            _advance_enrollment(db, enrollment_id, sequence_id, current_step, now, summary, skipped=True)
            return

    # Resolve recipient email
    recipient_email = _resolve_email(db, lead_id, user_location_id)
    if not recipient_email:
        logger.warning(
            "drip.tick: enrollment=%s step=%s — no email, advancing",
            enrollment_id, current_step,
        )
        _advance_enrollment(db, enrollment_id, sequence_id, current_step, now, summary, skipped=True)
        return

    # Build a minimal campaign dict for delivery_sender
    seq_row = db.execute(
        text("""
            SELECT id, organization_id, name FROM crm_drip_sequences WHERE id = :id
        """),
        {"id": sequence_id},
    ).fetchone()

    campaign_like = {
        "id":               seq_row[0],
        "organization_id":  seq_row[1],
        "name":             seq_row[2],
        "campaign_type":    "drip",
        "trigger_event":    None,
        "trigger_config":   {},
        "segment_id":       None,
        "template_id":      template_id,
        "status":           "running",
        "started_at":       None,
        "last_trigger_eval_at": None,
        "send_from_name":   None,
        "send_from_email":  None,
        "reply_to":         None,
    }

    delivery_sender.enqueue_delivery(
        db,
        campaign_like,
        user_location_id=user_location_id,
        lead_id=lead_id,
        recipient_email=recipient_email,
        render_context={"drip_step": current_step, "sequence_id": sequence_id},
    )

    _advance_enrollment(db, enrollment_id, sequence_id, current_step, now, summary, skipped=False)


def _advance_enrollment(
    db: Session,
    enrollment_id: int,
    sequence_id: int,
    current_step: int,
    now: datetime,
    summary: Dict[str, Any],
    skipped: bool = False,
) -> None:
    """Advance to next step or mark completed."""
    next_step_index = current_step + 1

    next_step_row = db.execute(
        text("""
            SELECT delay_days, delay_hours FROM crm_drip_steps
            WHERE sequence_id = :seq_id AND step_index = :idx
        """),
        {"seq_id": sequence_id, "idx": next_step_index},
    ).fetchone()

    if next_step_row:
        delay = timedelta(
            days=int(next_step_row[0] or 0),
            hours=int(next_step_row[1] or 0),
        )
        next_step_at = now + delay
        db.execute(
            text("""
                UPDATE crm_drip_enrollments
                SET current_step = :next_step, next_step_at = :next_step_at
                WHERE id = :id
            """),
            {"id": enrollment_id, "next_step": next_step_index, "next_step_at": next_step_at},
        )
        db.commit()
        summary["advanced"] += 1
    else:
        # Last step — completed
        db.execute(
            text("""
                UPDATE crm_drip_enrollments
                SET status = 'completed', completed_at = :now,
                    current_step = :next_step
                WHERE id = :id
            """),
            {"id": enrollment_id, "now": now, "next_step": next_step_index},
        )
        db.commit()
        summary["completed"] += 1


def _load_recipient_props(
    db: Session,
    lead_id: Optional[int],
    user_location_id: Optional[int],
) -> Dict[str, Any]:
    """Load lead/user fields as a flat property dict for skip_filter evaluation."""
    if lead_id:
        row = db.execute(
            text("""
                SELECT status, company, country, language, lead_score, tags
                FROM crm_leads WHERE id = :id
            """),
            {"id": lead_id},
        ).fetchone()
        if row:
            return {
                "status": row[0], "company": row[1], "country": row[2],
                "language": row[3], "lead_score": row[4], "tags": row[5] or [],
            }
    if user_location_id:
        row = db.execute(
            text("SELECT email FROM user_locations WHERE id = :id AND deleted_date IS NULL"),
            {"id": user_location_id},
        ).fetchone()
        if row:
            return {"email": row[0]}
    return {}


def _resolve_email(
    db: Session,
    lead_id: Optional[int],
    user_location_id: Optional[int],
) -> Optional[str]:
    if lead_id:
        row = db.execute(
            text("SELECT email FROM crm_leads WHERE id = :id AND deleted_date IS NULL"),
            {"id": lead_id},
        ).fetchone()
        return row[0] if row else None
    if user_location_id:
        row = db.execute(
            text("SELECT email FROM user_locations WHERE id = :id AND deleted_date IS NULL"),
            {"id": user_location_id},
        ).fetchone()
        return row[0] if row else None
    return None


# ─── Auto-enrollment ──────────────────────────────────────────────────────────

def _auto_enroll_on_event(
    db: Session,
    event: str,
    lead=None,
    user_location_id: Optional[int] = None,
    org_id: Optional[int] = None,
) -> None:
    """
    Called by lead_service after lead_created / lead_status_changed.
    Queries active sequences matching the trigger_event and enrolls.
    Idempotent — enroll() handles duplicates.

    For 'lead_status_changed' with a trigger_config.targetStatus, only
    enrolls if the lead's current status matches.
    """
    if lead is None and user_location_id is None:
        return

    _org_id = org_id
    _lead_status = None
    _lead_id = None

    if lead is not None:
        _lead_id = lead.get("id") if isinstance(lead, dict) else getattr(lead, "id", None)
        _org_id = _org_id or (lead.get("organization_id") if isinstance(lead, dict) else getattr(lead, "organization_id", None))
        _lead_status = lead.get("status") if isinstance(lead, dict) else getattr(lead, "status", None)

    if not _org_id:
        return

    try:
        sequences = db.execute(
            text("""
                SELECT id, trigger_config FROM crm_drip_sequences
                WHERE organization_id = :org_id
                  AND status = 'active'
                  AND trigger_event = :event
                  AND deleted_date IS NULL
            """),
            {"org_id": _org_id, "event": event},
        ).fetchall()

        for seq_row in sequences:
            seq_id = seq_row[0]
            config = seq_row[1] or {}

            # For status_changed: only enroll if lead status matches targetStatus
            if event == 'lead_status_changed' and config.get('targetStatus'):
                if _lead_status != config['targetStatus']:
                    continue

            try:
                enroll(db, seq_id, lead_id=_lead_id, user_location_id=user_location_id)
            except Exception as exc:
                logger.warning(
                    "drip._auto_enroll_on_event: failed to enroll lead=%s in seq=%s: %s",
                    _lead_id, seq_id, exc,
                )

    except Exception as exc:
        logger.warning("drip._auto_enroll_on_event: non-fatal error: %s", exc)
