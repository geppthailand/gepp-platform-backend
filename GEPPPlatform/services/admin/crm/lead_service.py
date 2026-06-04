"""
Lead service — all business logic for crm_leads + crm_lead_activities.

Non-negotiables enforced here:
  - All SQL via text() + bind params.  No string interpolation.
  - email always stored/searched lowercased.
  - create_lead is idempotent on (org_id, lower(email)).
  - Activity row written on every status change, assign, convert, import.
  - emit_event() called for crm_events after status changes.
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import BadRequestException, NotFoundException
from . import crm_service

logger = logging.getLogger(__name__)

# ─── Valid value sets ─────────────────────────────────────────────────────────

VALID_STATUSES = {'new', 'contacted', 'qualified', 'negotiating', 'customer', 'lost'}
VALID_SOURCES  = {'web_form', 'csv_import', 'api', 'manual', 'event', 'referral'}

# Status-to-score weight table (used by score_lead).
STATUS_SCORE = {
    'new':         0,
    'contacted':   10,
    'qualified':   25,
    'negotiating': 40,
    'customer':    60,
    'lost':       -10,
}

# CSV column name → model field mapping (exact name match, lowercase).
CSV_COLUMN_MAP = {
    'email':      'email',
    'first_name': 'first_name',
    'last_name':  'last_name',
    'company':    'company',
    'job_title':  'job_title',
    'phone':      'phone',
    'country':    'country',
    'language':   'language',
    'source':     'source',
    'notes':      'notes',
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a SQLAlchemy Row (from fetchone) to a dict using _mapping."""
    return dict(row._mapping)


def _serialize_lead(row) -> Dict[str, Any]:
    d = _row_to_dict(row)
    # Convert datetime fields to ISO strings for JSON serialization.
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    d.update({
        'organizationId': d.get('organization_id'),
        'firstName': d.get('first_name'),
        'lastName': d.get('last_name'),
        'jobTitle': d.get('job_title'),
        'sourceMetadata': d.get('source_metadata'),
        'statusChangedAt': d.get('status_changed_at'),
        'leadScore': d.get('lead_score'),
        'ownerUserId': d.get('owner_user_id'),
        'convertedUserId': d.get('converted_user_id'),
        'convertedAt': d.get('converted_at'),
        'lastActivityAt': d.get('last_activity_at'),
        'createdDate': d.get('created_date'),
        'updatedDate': d.get('updated_date'),
    })
    return d


def _pick(data: Dict[str, Any], snake_key: str, camel_key: str):
    if snake_key in data:
        return data.get(snake_key)
    return data.get(camel_key)


# ─── List / Get ──────────────────────────────────────────────────────────────

def list_leads(
    db: Session,
    org_id: Optional[int],
    filters: Dict[str, Any],
    page: int = 1,
    page_size: int = 25,
) -> Dict[str, Any]:
    """
    Paginated lead list with multi-dimensional filtering.

    org_id=None bypasses the per-organization filter (super-admin only —
    enforcement happens in the handler).

    Supported filter keys:
      status, owner_user_id, source, country, tag (single tag from JSONB array),
      min_score, max_score, q (ilike on email/first_name/last_name/company),
      created_after (ISO timestamp), last_activity_after (ISO timestamp).
    """
    page     = max(1, page)
    page_size = max(1, min(200, page_size))
    offset   = (page - 1) * page_size

    where_clauses: List[str] = ["deleted_date IS NULL"]
    params: Dict[str, Any] = {}
    if org_id is not None:
        where_clauses.append("organization_id = :org_id")
        params['org_id'] = org_id

    if filters.get('status') and filters['status'] in VALID_STATUSES:
        where_clauses.append("status = :status")
        params['status'] = filters['status']

    if filters.get('owner_user_id'):
        try:
            params['owner_user_id'] = int(filters['owner_user_id'])
            where_clauses.append("owner_user_id = :owner_user_id")
        except (TypeError, ValueError):
            pass

    if filters.get('source') and filters['source'] in VALID_SOURCES:
        where_clauses.append("source = :source")
        params['source'] = filters['source']

    if filters.get('country'):
        where_clauses.append("country ILIKE :country")
        params['country'] = f"%{filters['country']}%"

    if filters.get('tag'):
        # JSONB array containment: tags @> '["some_tag"]'
        where_clauses.append("tags @> jsonb_build_array(:tag::text)")
        params['tag'] = str(filters['tag'])

    if filters.get('min_score') is not None:
        try:
            params['min_score'] = int(filters['min_score'])
            where_clauses.append("lead_score >= :min_score")
        except (TypeError, ValueError):
            pass

    if filters.get('max_score') is not None:
        try:
            params['max_score'] = int(filters['max_score'])
            where_clauses.append("lead_score <= :max_score")
        except (TypeError, ValueError):
            pass

    if filters.get('q'):
        q = f"%{filters['q'].strip()}%"
        where_clauses.append(
            "(email ILIKE :q OR first_name ILIKE :q OR last_name ILIKE :q OR company ILIKE :q)"
        )
        params['q'] = q

    if filters.get('created_after'):
        where_clauses.append("created_date >= :created_after")
        params['created_after'] = filters['created_after']

    if filters.get('last_activity_after'):
        where_clauses.append("last_activity_at >= :last_activity_after")
        params['last_activity_after'] = filters['last_activity_after']

    where_sql = " AND ".join(where_clauses)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM crm_leads WHERE {where_sql}"), params
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT id, organization_id, email, first_name, last_name, company,
                   job_title, phone, country, language, source, source_metadata,
                   status, status_changed_at, lead_score, owner_user_id,
                   tags, notes, converted_user_id, converted_at,
                   last_activity_at, created_date, updated_date
            FROM crm_leads
            WHERE {where_sql}
            ORDER BY last_activity_at DESC NULLS LAST, id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, 'limit': page_size, 'offset': offset},
    ).fetchall()

    return {
        "items": [_serialize_lead(r) for r in rows],
        "total": int(total or 0),
        "page": page,
        "pageSize": page_size,
    }


def get_lead(db: Session, lead_id: int, org_id: Optional[int]) -> Dict[str, Any]:
    """Fetch one lead by id + org_id, or raise NotFoundException."""
    org_sql = _org_match_sql(org_id)
    params = _with_org_param({'id': lead_id}, org_id)
    row = db.execute(
        text(f"""
            SELECT id, organization_id, email, first_name, last_name, company,
                   job_title, phone, country, language, source, source_metadata,
                   status, status_changed_at, lead_score, owner_user_id,
                   tags, notes, converted_user_id, converted_at,
                   last_activity_at, created_date, updated_date
            FROM crm_leads
            WHERE id = :id AND {org_sql} AND deleted_date IS NULL
        """),
        params,
    ).fetchone()
    if not row:
        raise NotFoundException(f"Lead {lead_id} not found")
    return _serialize_lead(row)


# ─── Create / Update / Delete ────────────────────────────────────────────────

def create_lead(
    db: Session,
    org_id: Optional[int],
    data: Dict[str, Any],
    source: str = 'manual',
    source_metadata: Optional[Dict[str, Any]] = None,
    owner_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a new lead.  Idempotent on (org_id, lower(email)):
    if the lead already exists (including soft-deleted), returns the existing row
    without modification.

    Returns the lead dict.
    """
    email_raw = (data.get('email') or '').strip()
    if not email_raw:
        raise BadRequestException("email is required")
    email = email_raw.lower()

    if source not in VALID_SOURCES:
        source = 'manual'

    # Idempotency check — include soft-deleted rows (don't re-create over deleted data).
    org_sql = _org_match_sql(org_id)
    existing_params = _with_org_param({'email': email}, org_id)
    existing = db.execute(
        text(f"SELECT id FROM crm_leads WHERE {org_sql} AND email = :email LIMIT 1"),
        existing_params,
    ).fetchone()
    if existing:
        return get_lead(db, existing[0], org_id) if not _is_soft_deleted(db, existing[0]) \
            else _get_lead_any(db, existing[0])

    now = _now()
    result = db.execute(
        text("""
            INSERT INTO crm_leads (
                organization_id, email, first_name, last_name, company, job_title,
                phone, country, language, source, source_metadata, status,
                lead_score, owner_user_id, tags, notes,
                last_activity_at, created_date, updated_date
            ) VALUES (
                :org_id, :email, :first_name, :last_name, :company, :job_title,
                :phone, :country, :language, :source, :source_metadata::jsonb, 'new',
                0, :owner_user_id, :tags::jsonb, :notes,
                :now, :now, :now
            )
            RETURNING id
        """),
        {
            'org_id':           org_id,
            'email':            email,
            'first_name':       _pick(data, 'first_name', 'firstName') or None,
            'last_name':        _pick(data, 'last_name', 'lastName') or None,
            'company':          data.get('company') or None,
            'job_title':        _pick(data, 'job_title', 'jobTitle') or None,
            'phone':            data.get('phone') or None,
            'country':          data.get('country') or None,
            'language':         data.get('language') or None,
            'source':           source,
            'source_metadata':  _to_json(source_metadata),
            'owner_user_id':    owner_user_id or data.get('owner_user_id') or None,
            'tags':             _to_json(data.get('tags')),
            'notes':            data.get('notes') or None,
            'now':              now,
        },
    ).fetchone()
    db.commit()

    lead_id = result[0]
    add_activity(
        db, lead_id,
        activity_type='note_added',
        properties={'source': source, 'source_metadata': source_metadata},
        user_id=owner_user_id,
    )
    db.commit()

    created_lead = get_lead(db, lead_id, org_id)
    # Auto-enroll in any active drip sequences triggered on lead_created.
    try:
        from . import drip_service as _drip
        if org_id is not None:
            _drip._auto_enroll_on_event(db, event='lead_created', lead=created_lead, org_id=org_id)
    except Exception as exc:
        logger.warning("lead_service.create_lead: auto-enroll non-fatal: %s", exc)

    return created_lead


def update_lead(
    db: Session,
    lead_id: int,
    org_id: Optional[int],
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Update mutable lead fields (does NOT touch status — use change_status for that)."""
    # Verify it exists first.
    get_lead(db, lead_id, org_id)

    updatable = {
        'first_name': 'firstName',
        'last_name': 'lastName',
        'company': 'company',
        'job_title': 'jobTitle',
        'phone': 'phone',
        'country': 'country',
        'language': 'language',
        'tags': 'tags',
        'notes': 'notes',
    }
    set_clauses: List[str] = ["updated_date = :now"]
    params: Dict[str, Any] = _with_org_param({'id': lead_id, 'now': _now()}, org_id)

    for field, camel_field in updatable.items():
        if field in data or camel_field in data:
            value = _pick(data, field, camel_field)
            if field == 'tags':
                set_clauses.append(f"{field} = :{field}::jsonb")
                params[field] = _to_json(value)
            else:
                set_clauses.append(f"{field} = :{field}")
                params[field] = value or None

    if len(set_clauses) == 1:
        return get_lead(db, lead_id, org_id)  # nothing to update

    org_sql = _org_match_sql(org_id)
    db.execute(
        text(f"""
            UPDATE crm_leads
               SET {', '.join(set_clauses)}
             WHERE id = :id AND {org_sql} AND deleted_date IS NULL
        """),
        params,
    )
    db.commit()
    return get_lead(db, lead_id, org_id)


def delete_lead(db: Session, lead_id: int, org_id: Optional[int]) -> Dict[str, Any]:
    """Soft-delete by setting deleted_date."""
    get_lead(db, lead_id, org_id)
    org_sql = _org_match_sql(org_id)
    db.execute(
        text(f"""
            UPDATE crm_leads
               SET deleted_date = :now, updated_date = :now
             WHERE id = :id AND {org_sql} AND deleted_date IS NULL
        """),
        _with_org_param({'id': lead_id, 'now': _now()}, org_id),
    )
    db.commit()
    return {"deleted": True, "id": lead_id}


# ─── Status / Assignment / Conversion ────────────────────────────────────────

def change_status(
    db: Session,
    lead_id: int,
    org_id: Optional[int],
    new_status: str,
    by_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Change lead status.  Writes activity row + emits crm_event lead_status_changed.
    """
    if new_status not in VALID_STATUSES:
        raise BadRequestException(
            f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )
    lead = get_lead(db, lead_id, org_id)
    old_status = lead['status']
    if old_status == new_status:
        return lead

    now = _now()
    org_sql = _org_match_sql(org_id)
    db.execute(
        text(f"""
            UPDATE crm_leads
               SET status = :status, status_changed_at = :now,
                   last_activity_at = :now, updated_date = :now
             WHERE id = :id AND {org_sql} AND deleted_date IS NULL
        """),
        _with_org_param({'id': lead_id, 'status': new_status, 'now': now}, org_id),
    )

    add_activity(
        db, lead_id,
        activity_type='status_changed',
        properties={'from': old_status, 'to': new_status},
        user_id=by_user_id,
        occurred_at=now,
    )
    db.commit()

    # Non-fatal crm_event emission.
    try:
        crm_service.emit_event(
            db,
            event_type='lead_status_changed',
            event_category='crm',
            organization_id=org_id,
            user_location_id=by_user_id,
            properties={'lead_id': lead_id, 'from': old_status, 'to': new_status},
            commit=True,
        )
    except Exception as exc:
        logger.warning("lead_service.change_status emit_event failed (non-fatal): %s", exc)

    updated_lead = get_lead(db, lead_id, org_id)

    # Auto-enroll in any active drip sequences triggered on lead_status_changed.
    try:
        from . import drip_service as _drip
        if org_id is not None:
            _drip._auto_enroll_on_event(
                db, event='lead_status_changed', lead=updated_lead, org_id=org_id
            )
    except Exception as exc:
        logger.warning("lead_service.change_status: auto-enroll non-fatal: %s", exc)

    return updated_lead


def assign_owner(
    db: Session,
    lead_id: int,
    org_id: Optional[int],
    owner_user_id: int,
    by_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Assign a lead owner.  Writes activity row."""
    lead = get_lead(db, lead_id, org_id)
    old_owner = lead.get('owner_user_id')
    now = _now()
    org_sql = _org_match_sql(org_id)

    db.execute(
        text(f"""
            UPDATE crm_leads
               SET owner_user_id = :owner, last_activity_at = :now, updated_date = :now
             WHERE id = :id AND {org_sql} AND deleted_date IS NULL
        """),
        _with_org_param({'id': lead_id, 'owner': owner_user_id, 'now': now}, org_id),
    )
    add_activity(
        db, lead_id,
        activity_type='owner_assigned',
        properties={'from': old_owner, 'to': owner_user_id},
        user_id=by_user_id,
        occurred_at=now,
    )
    db.commit()
    return get_lead(db, lead_id, org_id)


def convert_lead(
    db: Session,
    lead_id: int,
    org_id: Optional[int],
    user_location_id: int,
) -> Dict[str, Any]:
    """
    Mark a lead as converted.

    Sets converted_user_id + converted_at on the lead and back-fills
    user_locations.from_lead_id.  Idempotent — calling again with the same
    user_location_id is a no-op.
    """
    lead = get_lead(db, lead_id, org_id)
    now = _now()

    # Idempotency guard.
    if lead.get('converted_user_id') == user_location_id:
        return lead

    org_sql = _org_match_sql(org_id)
    db.execute(
        text(f"""
            UPDATE crm_leads
               SET converted_user_id = :uid, converted_at = :now,
                   status = 'customer', status_changed_at = :now,
                   last_activity_at = :now, updated_date = :now
             WHERE id = :id AND {org_sql} AND deleted_date IS NULL
        """),
        _with_org_param({'id': lead_id, 'uid': user_location_id, 'now': now}, org_id),
    )

    # Back-fill user_locations.from_lead_id (IF NOT ALREADY SET — don't overwrite
    # if the column already points somewhere).
    db.execute(
        text("""
            UPDATE user_locations
               SET from_lead_id = :lead_id
             WHERE id = :uid AND (from_lead_id IS NULL OR from_lead_id = :lead_id)
        """),
        {'uid': user_location_id, 'lead_id': lead_id},
    )

    add_activity(
        db, lead_id,
        activity_type='converted',
        properties={'user_location_id': user_location_id},
        occurred_at=now,
    )
    db.commit()
    return get_lead(db, lead_id, org_id)


# ─── Activity log ─────────────────────────────────────────────────────────────

def add_activity(
    db: Session,
    lead_id: int,
    activity_type: str,
    properties: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
) -> int:
    """Append one row to crm_lead_activities.  Returns the new row id."""
    now = occurred_at or _now()
    result = db.execute(
        text("""
            INSERT INTO crm_lead_activities
                (lead_id, activity_type, properties, performed_by, occurred_at)
            VALUES
                (:lead_id, :activity_type, :properties::jsonb, :performed_by, :occurred_at)
            RETURNING id
        """),
        {
            'lead_id':       lead_id,
            'activity_type': activity_type,
            'properties':    _to_json(properties or {}),
            'performed_by':  user_id,
            'occurred_at':   now,
        },
    ).fetchone()
    # Touch last_activity_at on the parent lead (best-effort, no raise).
    try:
        db.execute(
            text("""
                UPDATE crm_leads
                   SET last_activity_at = :now, updated_date = :now
                 WHERE id = :id
            """),
            {'id': lead_id, 'now': now},
        )
    except Exception as exc:
        logger.warning("add_activity: could not touch last_activity_at: %s", exc)
    return result[0]


def list_activities(
    db: Session,
    lead_id: int,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    page     = max(1, page)
    page_size = max(1, min(200, page_size))
    offset   = (page - 1) * page_size

    total = db.execute(
        text("SELECT COUNT(*) FROM crm_lead_activities WHERE lead_id = :id"),
        {'id': lead_id},
    ).scalar()

    rows = db.execute(
        text("""
            SELECT id, lead_id, activity_type, properties, performed_by, occurred_at
            FROM crm_lead_activities
            WHERE lead_id = :id
            ORDER BY occurred_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {'id': lead_id, 'limit': page_size, 'offset': offset},
    ).fetchall()

    items = [
        {
            'id':           r[0],
            'leadId':       r[1],
            'activityType': r[2],
            'properties':   r[3] or {},
            'performedBy':  r[4],
            'occurredAt':   r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": int(total or 0),
        "page": page,
        "pageSize": page_size,
    }


# ─── Lead scoring ────────────────────────────────────────────────────────────

def score_lead(db: Session, lead_id: int) -> Dict[str, Any]:
    """
    Rule-based lead scoring.  Recalculates and persists lead_score.

    Scoring components:
      1. Status weight (STATUS_SCORE dict above).
      2. Recency bonus: +5 if last_activity within 7 days; 0 if > 30 days since created.
      3. Email engagement: +3 per email_opened activity (capped at +15).
      4. Data completeness: +2 per filled optional field (max +10).
      5. Tags bonus: +1 per tag (max +5).
    Returns the updated lead dict.
    """
    row = db.execute(
        text("""
            SELECT id, organization_id, status, lead_score, tags,
                   first_name, last_name, company, job_title, phone, country,
                   last_activity_at, created_date, deleted_date
            FROM crm_leads
            WHERE id = :id
        """),
        {'id': lead_id},
    ).fetchone()
    if not row or row[13]:
        raise NotFoundException(f"Lead {lead_id} not found")

    (_, org_id, status, _, tags,
     first_name, last_name, company, job_title, phone, country,
     last_activity_at, created_date, _deleted) = row

    now = _now()
    score = STATUS_SCORE.get(status, 0)

    # Recency.
    if last_activity_at:
        days_inactive = (now - last_activity_at.replace(tzinfo=timezone.utc)).days \
            if last_activity_at.tzinfo is None \
            else (now - last_activity_at).days
        if days_inactive <= 7:
            score += 5
        elif days_inactive > 30:
            score -= 5

    # Email engagement.
    eng_count = db.execute(
        text("""
            SELECT COUNT(*) FROM crm_lead_activities
             WHERE lead_id = :id AND activity_type = 'email_opened'
        """),
        {'id': lead_id},
    ).scalar() or 0
    score += min(int(eng_count) * 3, 15)

    # Data completeness.
    optional_fields = [first_name, last_name, company, job_title, phone, country]
    filled = sum(1 for f in optional_fields if f)
    score += min(filled * 2, 10)

    # Tags bonus.
    tag_list = tags if isinstance(tags, list) else []
    score += min(len(tag_list), 5)

    score = max(0, score)  # floor at 0

    db.execute(
        text("""
            UPDATE crm_leads
               SET lead_score = :score, updated_date = :now
             WHERE id = :id
        """),
        {'id': lead_id, 'score': score, 'now': now},
    )
    add_activity(
        db, lead_id,
        activity_type='score_updated',
        properties={'score': score},
    )
    db.commit()
    return get_lead(db, lead_id, org_id)


# ─── Bulk CSV import ─────────────────────────────────────────────────────────

def bulk_import_csv(
    db: Session,
    org_id: int,
    csv_text: str,
    owner_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Parse and import leads from CSV text.

    - Header row must include an 'email' column.
    - Columns mapped by exact name match (see CSV_COLUMN_MAP).
    - Duplicate (org_id, lower(email)) rows are silently skipped.
    - Returns {imported: int, skipped: int, errors: list[str]}.
    """
    imported = 0
    skipped  = 0
    errors:  List[str] = []

    try:
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
    except Exception as exc:
        raise BadRequestException(f"Could not parse CSV: {exc}")

    if reader.fieldnames is None:
        raise BadRequestException("CSV appears empty or has no header row")

    # Normalise header names (strip whitespace, lowercase).
    header_map = {h.strip().lower(): h for h in (reader.fieldnames or [])}
    if 'email' not in header_map:
        raise BadRequestException("CSV must include an 'email' column header")

    for i, raw_row in enumerate(reader, start=2):  # row 1 = header
        # Re-key by lowercased + stripped header.
        row = {k.strip().lower(): (v or '').strip() for k, v in raw_row.items()}

        email_raw = row.get('email', '')
        if not email_raw:
            errors.append(f"Row {i}: missing email — skipped")
            skipped += 1
            continue

        email = email_raw.lower()

        # Check for existing (org_id, email) — dedup without crashing.
        existing = db.execute(
            text("SELECT id FROM crm_leads WHERE organization_id = :org_id AND email = :email LIMIT 1"),
            {'org_id': org_id, 'email': email},
        ).fetchone()
        if existing:
            skipped += 1
            continue

        # Map CSV columns to lead fields.
        lead_data: Dict[str, Any] = {'email': email}
        for csv_col, model_field in CSV_COLUMN_MAP.items():
            if csv_col in row and row[csv_col]:
                lead_data[model_field] = row[csv_col]

        try:
            now = _now()
            result = db.execute(
                text("""
                    INSERT INTO crm_leads (
                        organization_id, email, first_name, last_name, company,
                        job_title, phone, country, language, source, notes,
                        status, lead_score, owner_user_id,
                        last_activity_at, created_date, updated_date
                    ) VALUES (
                        :org_id, :email, :first_name, :last_name, :company,
                        :job_title, :phone, :country, :language, 'csv_import', :notes,
                        'new', 0, :owner_user_id,
                        :now, :now, :now
                    )
                    RETURNING id
                """),
                {
                    'org_id':         org_id,
                    'email':          email,
                    'first_name':     lead_data.get('first_name'),
                    'last_name':      lead_data.get('last_name'),
                    'company':        lead_data.get('company'),
                    'job_title':      lead_data.get('job_title'),
                    'phone':          lead_data.get('phone'),
                    'country':        lead_data.get('country'),
                    'language':       lead_data.get('language'),
                    'notes':          lead_data.get('notes'),
                    'owner_user_id':  owner_user_id,
                    'now':            now,
                },
            ).fetchone()
            new_id = result[0]

            # Activity row per imported lead.
            db.execute(
                text("""
                    INSERT INTO crm_lead_activities
                        (lead_id, activity_type, properties, performed_by, occurred_at)
                    VALUES
                        (:lead_id, 'csv_imported', :props::jsonb, :by, :now)
                """),
                {
                    'lead_id': new_id,
                    'props':   _to_json({'imported_by_user_id': owner_user_id}),
                    'by':      owner_user_id,
                    'now':     now,
                },
            )
            imported += 1

            # Commit every 50 rows to avoid long transactions.
            if imported % 50 == 0:
                db.commit()

        except Exception as exc:
            errors.append(f"Row {i} ({email}): {exc}")
            db.rollback()

    try:
        db.commit()
    except Exception as exc:
        logger.warning("bulk_import_csv: final commit failed: %s", exc)

    return {
        "imported": imported,
        "skipped":  skipped,
        "errors":   errors,
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _to_json(value) -> Optional[str]:
    """Serialize a Python value to a JSON string, or return None."""
    if value is None:
        return None
    import json
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return None


def _org_match_sql(org_id: Optional[int]) -> str:
    return "organization_id IS NULL" if org_id is None else "organization_id = :org_id"


def _with_org_param(params: Dict[str, Any], org_id: Optional[int]) -> Dict[str, Any]:
    if org_id is not None:
        params["org_id"] = org_id
    return params


def _is_soft_deleted(db: Session, lead_id: int) -> bool:
    row = db.execute(
        text("SELECT deleted_date FROM crm_leads WHERE id = :id"), {'id': lead_id}
    ).fetchone()
    return bool(row and row[0])


def _get_lead_any(db: Session, lead_id: int) -> Dict[str, Any]:
    """Return a lead dict regardless of deleted_date (used after idempotency hit on soft-deleted row)."""
    row = db.execute(
        text("""
            SELECT id, organization_id, email, first_name, last_name, company,
                   job_title, phone, country, language, source, source_metadata,
                   status, status_changed_at, lead_score, owner_user_id,
                   tags, notes, converted_user_id, converted_at,
                   last_activity_at, created_date, updated_date
            FROM crm_leads WHERE id = :id
        """),
        {'id': lead_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Lead {lead_id} not found")
    return _serialize_lead(row)
