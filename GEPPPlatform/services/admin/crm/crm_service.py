"""
CRM service — shared helpers used by BE1 (event emission, analytics) and BE2 (segments, delivery).

This is a SKELETON. Sprint-1 devs fill in method bodies per their briefs.

Key non-negotiables:
  - emit_event() is the ONLY entry point for writing to crm_events
  - send_via_email_lambda() is the ONLY email path; it wraps lambda.invoke('PROD-GEPPEmailNotification')
  - All SQL uses parameterized queries (no string interpolation)
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta

import boto3
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ....models.crm import CrmEvent

logger = logging.getLogger(__name__)

MARKETING_EVENT_TYPES = [
    "user_login",
    "transaction_created",
    "transaction_qr_input",
    "reward_claimed",
    "gri_data_submitted",
    "traceability_created",
    "email_sent",
    "email_opened",
    "email_clicked",
]


# ───────────────────────────────────────────────────────────────
# Event emission
# ───────────────────────────────────────────────────────────────

def emit_event(
    db_session: Session,
    *,
    event_type: str,
    event_category: str,
    organization_id: Optional[int] = None,
    user_location_id: Optional[int] = None,
    properties: Optional[Dict[str, Any]] = None,
    event_source: str = 'server',
    session_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    commit: bool = False,
) -> Optional[CrmEvent]:
    """
    Insert a row into crm_events.

    Owner: BE Dev 1. Called from instrumented handlers (auth, transaction, traceability,
    gri, reward, iot) and from the public POST /api/crm/events ingest endpoint.

    Never raises on insert failure — CRM event logging must not break the calling handler.
    """
    try:
        evt = CrmEvent(
            organization_id=organization_id,
            user_location_id=user_location_id,
            event_type=event_type,
            event_category=event_category,
            event_source=event_source,
            properties=properties or {},
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db_session.add(evt)
        if commit:
            db_session.commit()
        return evt
    except Exception as e:
        logger.warning("crm_service.emit_event failed (non-fatal): %s", e)
        return None


# ───────────────────────────────────────────────────────────────
# Email delivery — single path through PROD-GEPPEmailNotification Lambda (Mailchimp wrapper)
# ───────────────────────────────────────────────────────────────

def send_via_email_lambda(
    *,
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc_emails: Optional[List[Dict[str, str]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    track_opens: bool = True,
    track_clicks: bool = True,
) -> Dict[str, Any]:
    """
    Invoke PROD-GEPPEmailNotification Lambda which wraps Mailchimp Transactional (Mandrill).

    Owner: BE Dev 2 (campaign sender, trigger evaluator, test-send).
    Also consumed by: BE Dev 1 (if analytics endpoints need to send reports).

    Pattern copied from:
      - v3/backend/GEPPPlatform/services/auth/auth_handlers.py:59 (_send_email_via_lambda)
      - v3/backend/GEPPPlatform/services/cores/reports/schedule_report.py:299

    Returns:
      {
        "success": bool,
        "mandrill_message_id": str | None,  # Mailchimp _id for webhook correlation
        "raw_response": dict,
        "error": str | None,
      }
    """
    lambda_function_name = os.environ.get('EMAIL_LAMBDA_FUNCTION', 'PROD-GEPPEmailNotification')

    message: Dict[str, Any] = {
        "from_email": from_email or os.environ.get('EMAIL_FROM', 'noreply@gepp.me'),
        "from_name": from_name or os.environ.get('EMAIL_FROM_NAME', 'GEPP Platform'),
        "to": [{"email": to_email, "type": "to"}],
        "subject": subject,
        "html": html_content,
        "track_opens": track_opens,
        "track_clicks": track_clicks,
    }
    if text_content:
        message["text"] = text_content
    if reply_to:
        message["headers"] = {"Reply-To": reply_to}
    if cc_emails:
        message["to"].extend([{"email": c["email"], "name": c.get("name"), "type": "cc"} for c in cc_emails])
    if metadata:
        message["metadata"] = metadata
    if tags:
        message["tags"] = tags

    try:
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps({"data": {"message": message}}).encode("utf-8"),
        )
        payload = response.get('Payload').read()
        parsed = json.loads(payload) if payload else {}

        # Mailchimp's response is an array: [{"_id": "...", "status": "sent"/"queued", ...}]
        mandrill_id = None
        if isinstance(parsed, list) and parsed:
            mandrill_id = parsed[0].get('_id')
        elif isinstance(parsed, dict):
            # Lambda may wrap response — try common shapes
            body = parsed.get('body')
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except Exception:
                    body = None
            if isinstance(body, list) and body:
                mandrill_id = body[0].get('_id')

        return {
            "success": bool(mandrill_id),
            "mandrill_message_id": mandrill_id,
            "raw_response": parsed,
            "error": None if mandrill_id else "Missing _id in Mailchimp response",
        }
    except Exception as e:
        logger.error("crm_service.send_via_email_lambda failed: %s", e)
        return {
            "success": False,
            "mandrill_message_id": None,
            "raw_response": None,
            "error": str(e),
        }


# ───────────────────────────────────────────────────────────────
# Analytics (BE Dev 1 fills in)
# ───────────────────────────────────────────────────────────────

def get_analytics_overview(
    db_session: Session,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Platform-wide KPIs for Marketing tab overview page.

    Returns:
      totalOrganizations, activeUsers30d, campaignsRunning,
      emailsSent7d, topOrgsByEngagement (top-5), atRiskOrgCount
    """
    now = datetime.now(timezone.utc)
    range_from, range_to_exclusive, range_to_display = _parse_analytics_range(date_from, date_to, now)
    org_filter_sql = " AND organization_id = :org_id" if organization_id is not None else ""
    org_params = {"org_id": organization_id} if organization_id is not None else {}

    # --- totalOrganizations ---
    total_orgs_row = db_session.execute(
        text("SELECT COUNT(*) FROM organizations WHERE deleted_date IS NULL"),
    ).scalar()
    total_organizations = int(total_orgs_row or 0)

    # --- activeUsers30d (distinct users who logged in in last 30d) ---
    active_users_row = db_session.execute(
        text(f"""
            SELECT COUNT(DISTINCT user_location_id)
            FROM crm_events
            WHERE event_type = 'user_login'
              AND occurred_at >= :range_from
              AND occurred_at < :range_to
              {org_filter_sql}
        """),
        {"range_from": range_from, "range_to": range_to_exclusive, **org_params},
    ).scalar()
    active_users_30d = int(active_users_row or 0)

    # --- campaignsRunning (status in ('active','running')) ---
    campaigns_running_row = db_session.execute(
        text(f"""
            SELECT COUNT(*) FROM crm_campaigns
            WHERE status IN ('active', 'running')
              AND deleted_date IS NULL
              {org_filter_sql}
        """),
        org_params,
    ).scalar()
    campaigns_running = int(campaigns_running_row or 0)

    # --- emailsSent7d (email events with category='email' in last 7d) ---
    emails_sent_row = db_session.execute(
        text(f"""
            SELECT COUNT(*) FROM crm_events
            WHERE event_category = 'email'
              AND event_type = 'email_sent'
              AND occurred_at >= :range_from
              AND occurred_at < :range_to
              {org_filter_sql}
        """),
        {"range_from": range_from, "range_to": range_to_exclusive, **org_params},
    ).scalar()
    emails_sent_7d = int(emails_sent_row or 0)

    # --- topOrgsByEngagement (top 5 from crm_org_profiles) ---
    top_orgs_rows = db_session.execute(
        text(f"""
            SELECT
                e.organization_id,
                o.name,
                COUNT(*)::INT AS engagement_score,
                COALESCE(op.activity_tier, 'active') AS activity_tier
            FROM crm_events e
            JOIN organizations o ON o.id = e.organization_id
            LEFT JOIN crm_org_profiles op ON op.organization_id = e.organization_id
            WHERE o.deleted_date IS NULL
              AND e.organization_id IS NOT NULL
              AND e.occurred_at >= :range_from
              AND e.occurred_at < :range_to
              {org_filter_sql.replace("organization_id", "e.organization_id")}
            GROUP BY e.organization_id, o.name, op.activity_tier
            ORDER BY engagement_score DESC
            LIMIT 5
        """),
        {"range_from": range_from, "range_to": range_to_exclusive, **org_params},
    ).fetchall()

    if not top_orgs_rows:
        top_orgs_rows = db_session.execute(
            text("""
                SELECT
                    op.organization_id,
                    o.name,
                    COALESCE(AVG(up.engagement_score), 0) AS engagement_score,
                    op.activity_tier
                FROM crm_org_profiles op
                JOIN organizations o ON o.id = op.organization_id
                LEFT JOIN crm_user_profiles up ON up.organization_id = op.organization_id
                WHERE o.deleted_date IS NULL
                GROUP BY op.organization_id, o.name, op.activity_tier
                ORDER BY engagement_score DESC
                LIMIT 5
            """),
        ).fetchall()

    top_orgs = [
        {
            "organizationId": row[0],
            "name": row[1] or "",
            "engagementScore": float(row[2] or 0),
            "activityTier": row[3] or "dormant",
        }
        for row in top_orgs_rows
    ]

    # --- atRiskOrgCount ---
    at_risk_row = db_session.execute(
        text("""
            SELECT COUNT(*) FROM crm_org_profiles
            WHERE activity_tier = 'at_risk'
        """),
    ).scalar()
    at_risk_org_count = int(at_risk_row or 0)

    return {
        "totalOrganizations": total_organizations,
        "activeUsers30d": active_users_30d,
        "campaignsRunning": campaigns_running,
        "emailsSent7d": emails_sent_7d,
        "activeUsersInRange": active_users_30d,
        "emailsSentInRange": emails_sent_7d,
        "topOrgsByEngagement": top_orgs,
        "atRiskOrgCount": at_risk_org_count,
        "from": range_from.isoformat(),
        "to": range_to_display.isoformat(),
        "organizationId": organization_id,
    }


def get_analytics_org_comparison(
    db_session: Session,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    organization_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    range_from, range_to_exclusive, range_to_display = _parse_analytics_range(date_from, date_to, now)
    event_types = _parse_event_types(event_type) or MARKETING_EVENT_TYPES
    limit = max(1, min(20, int(limit or 8)))
    org_filter_sql = " AND e.organization_id = :org_id" if organization_id is not None else ""
    params: Dict[str, Any] = {
        "range_from": range_from,
        "range_to": range_to_exclusive,
        "event_types": event_types,
        "limit": limit,
    }
    if organization_id is not None:
        params["org_id"] = organization_id

    rows = db_session.execute(
        text(f"""
            WITH event_counts AS (
                SELECT
                    e.organization_id,
                    o.name AS organization_name,
                    e.event_type,
                    COUNT(*)::INT AS event_count
                FROM crm_events e
                JOIN organizations o ON o.id = e.organization_id
                WHERE e.organization_id IS NOT NULL
                  AND o.deleted_date IS NULL
                  AND e.occurred_at >= :range_from
                  AND e.occurred_at < :range_to
                  AND e.event_type IN :event_types
                  {org_filter_sql}
                GROUP BY e.organization_id, o.name, e.event_type
            ),
            ranked_orgs AS (
                SELECT
                    organization_id,
                    organization_name,
                    SUM(event_count)::INT AS total_activity
                FROM event_counts
                GROUP BY organization_id, organization_name
                ORDER BY total_activity DESC, organization_name ASC
                LIMIT :limit
            )
            SELECT
                r.organization_id,
                r.organization_name,
                r.total_activity,
                c.event_type,
                c.event_count
            FROM ranked_orgs r
            JOIN event_counts c ON c.organization_id = r.organization_id
            ORDER BY r.total_activity DESC, r.organization_name ASC, c.event_type ASC
        """).bindparams(bindparam("event_types", expanding=True)),
        params,
    ).fetchall()

    org_map: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        org_id = int(row[0])
        if org_id not in org_map:
            org_map[org_id] = {
                "organizationId": org_id,
                "name": row[1] or f"Org {org_id}",
                "totalActivity": int(row[2] or 0),
                "events": {event: 0 for event in event_types},
            }
        org_map[org_id]["events"][row[3]] = int(row[4] or 0)

    return {
        "from": range_from.isoformat(),
        "to": range_to_display.isoformat(),
        "organizationId": organization_id,
        "eventTypes": event_types,
        "organizations": list(org_map.values()),
    }


def get_analytics_org(db_session: Session, organization_id: int) -> Dict[str, Any]:
    """
    Per-org dashboard data.

    Returns:
      organization info, metrics (activeUsers30d, totalUsers, transactionCount30d,
      lastActivityAt), eventBreakdown30d (top event types)
    """
    from ....exceptions import NotFoundException

    now = datetime.now(timezone.utc)
    window_30d = now - timedelta(days=30)

    # Fetch org basic info
    org_row = db_session.execute(
        text("""
            SELECT
                o.id,
                o.name,
                ul.email        AS owner_email,
                sp.display_name AS subscription_plan
            FROM organizations o
            LEFT JOIN user_locations ul ON ul.id = o.owner_id
            LEFT JOIN subscriptions s
                ON s.organization_id = o.id AND s.status = 'active' AND s.is_active = TRUE
            LEFT JOIN subscription_plans sp ON sp.id = s.plan_id
            WHERE o.id = :org_id
              AND o.deleted_date IS NULL
            ORDER BY s.created_date DESC
            LIMIT 1
        """),
        {"org_id": organization_id},
    ).fetchone()

    if not org_row:
        raise NotFoundException(f"Organization {organization_id} not found")

    # Fetch org profile from crm_org_profiles
    profile_row = db_session.execute(
        text("""
            SELECT activity_tier, last_activity_at
            FROM crm_org_profiles
            WHERE organization_id = :org_id
        """),
        {"org_id": organization_id},
    ).fetchone()

    activity_tier = (profile_row[0] if profile_row else None) or "dormant"
    last_activity_at = profile_row[1] if profile_row else None

    # Metrics
    metrics_row = db_session.execute(
        text("""
            SELECT
                COUNT(DISTINCT e.user_location_id) FILTER (
                    WHERE e.event_type = 'user_login' AND e.occurred_at >= :window_30d
                )                                               AS active_users_30d,
                COUNT(*) FILTER (
                    WHERE e.event_type = 'transaction_created' AND e.occurred_at >= :window_30d
                )                                               AS transaction_count_30d,
                (
                    SELECT COUNT(*)
                    FROM user_locations ul2
                    WHERE ul2.organization_id = :org_id
                      AND ul2.is_user = TRUE
                      AND ul2.is_active = TRUE
                      AND ul2.deleted_date IS NULL
                )                                               AS total_users
            FROM crm_events e
            WHERE e.organization_id = :org_id
        """),
        {"org_id": organization_id, "window_30d": window_30d},
    ).fetchone()

    # Event breakdown — top 10 event types in last 30d
    event_rows = db_session.execute(
        text("""
            SELECT event_type, COUNT(*) AS cnt
            FROM crm_events
            WHERE organization_id = :org_id
              AND occurred_at >= :window_30d
            GROUP BY event_type
            ORDER BY cnt DESC
            LIMIT 10
        """),
        {"org_id": organization_id, "window_30d": window_30d},
    ).fetchall()

    event_breakdown = {row[0]: int(row[1]) for row in event_rows}

    return {
        "organization": {
            "id": org_row[0],
            "name": org_row[1] or "",
            "ownerEmail": org_row[2] or "",
            "subscriptionPlan": org_row[3] or "",
            "activityTier": activity_tier,
        },
        "metrics": {
            "activeUsers30d": int((metrics_row[0] if metrics_row else None) or 0),
            "totalUsers": int((metrics_row[2] if metrics_row else None) or 0),
            "transactionCount30d": int((metrics_row[1] if metrics_row else None) or 0),
            "lastActivityAt": last_activity_at.isoformat() if last_activity_at else None,
        },
        "eventBreakdown30d": event_breakdown,
    }


def get_analytics_org_users(
    db_session: Session, organization_id: int, page: int = 1, page_size: int = 25
) -> Dict[str, Any]:
    """
    Per-user table for an org — paginated list from crm_user_profiles joined
    to user_locations for display fields.
    """
    offset = (max(page, 1) - 1) * page_size

    # Total count
    total_row = db_session.execute(
        text("""
            SELECT COUNT(*)
            FROM crm_user_profiles up
            JOIN user_locations ul ON ul.id = up.user_location_id
            WHERE up.organization_id = :org_id
              AND ul.is_active = TRUE
        """),
        {"org_id": organization_id},
    ).scalar()
    total = int(total_row or 0)

    # Paginated rows
    rows = db_session.execute(
        text("""
            SELECT
                ul.id                           AS user_id,
                ul.email,
                ul.display_name,
                ul.name_en,
                up.last_login_at,
                up.days_since_last_login,
                up.login_count_30d,
                up.transaction_count_30d,
                up.reward_claim_count_30d,
                up.engagement_score,
                up.activity_tier,
                up.onboarded
            FROM crm_user_profiles up
            JOIN user_locations ul ON ul.id = up.user_location_id
            WHERE up.organization_id = :org_id
              AND ul.is_active = TRUE
            ORDER BY up.engagement_score DESC, up.last_login_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """),
        {"org_id": organization_id, "limit": page_size, "offset": offset},
    ).fetchall()

    items = [
        {
            "userId": row[0],
            "email": row[1] or "",
            "displayName": row[2] or row[3] or "",
            "lastLoginAt": row[4].isoformat() if row[4] else None,
            "daysSinceLastLogin": row[5],
            "loginCount30d": int(row[6] or 0),
            "transactionCount30d": int(row[7] or 0),
            "rewardClaimCount30d": int(row[8] or 0),
            "engagementScore": float(row[9] or 0),
            "activityTier": row[10] or "dormant",
            "onboarded": bool(row[11]),
        }
        for row in rows
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def get_analytics_timeseries(
    db_session: Session,
    organization_id: Optional[int] = None,
    event_type: Optional[str] = None,
    granularity: str = 'day',
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Time-series chart data.

    granularity: 'hour' | 'day' | 'week' | 'month'
    Returns named event series with zero-filled buckets across the selected range.
    """
    # Whitelist granularity to prevent injection via date_trunc arg
    _VALID_GRANULARITY = {'hour', 'day', 'week', 'month'}
    if granularity not in _VALID_GRANULARITY:
        granularity = 'day'

    now = datetime.now(timezone.utc)
    dt_from, dt_to_exclusive, dt_to_display = _parse_analytics_range(date_from, date_to, now)
    requested_event_types = _parse_event_types(event_type)
    query_event_types = requested_event_types or MARKETING_EVENT_TYPES

    # Build parameterized WHERE clauses (no string interpolation for data)
    where_clauses = [
        "occurred_at >= :date_from",
        "occurred_at < :date_to",
    ]
    params: Dict[str, Any] = {
        "date_from": dt_from,
        "date_to": dt_to_exclusive,
        # granularity is whitelisted above — safe to embed as SQL identifier
    }

    if organization_id is not None:
        where_clauses.append("organization_id = :org_id")
        params["org_id"] = organization_id

    where_clauses.append("event_type IN :event_types")
    params["event_types"] = query_event_types

    where_sql = " AND ".join(where_clauses)

    # date_trunc arg is from the whitelisted set — not a user-controlled string
    sql = text(f"""
        SELECT
            DATE_TRUNC('{granularity}', occurred_at AT TIME ZONE 'UTC') AS bucket,
            event_type,
            COUNT(*)::INT                                                  AS cnt
        FROM crm_events
        WHERE {where_sql}
        GROUP BY bucket, event_type
        ORDER BY bucket ASC, event_type ASC
    """).bindparams(bindparam("event_types", expanding=True))

    rows = db_session.execute(sql, params).fetchall()

    buckets = _bucket_range(dt_from, dt_to_display, granularity)
    bucket_keys = [_bucket_key(b, granularity) for b in buckets]
    event_types = requested_event_types or MARKETING_EVENT_TYPES
    counts: Dict[str, Dict[str, int]] = {et: {key: 0 for key in bucket_keys} for et in event_types}

    for row in rows:
        bucket = row[0]
        row_event_type = row[1]
        if not row_event_type:
            continue
        key = _bucket_key(bucket, granularity)
        if row_event_type in counts and key in counts[row_event_type]:
            counts[row_event_type][key] = int(row[2] or 0)

    ordered_event_types = requested_event_types or MARKETING_EVENT_TYPES
    series = [
        {
            "eventType": et,
            "label": et.replace("_", " "),
            "data": [
                {"date": key, "count": counts.get(et, {}).get(key, 0)}
                for key in bucket_keys
            ],
        }
        for et in ordered_event_types
    ]

    return {
        "granularity": granularity,
        "organizationId": organization_id,
        "eventType": event_type,
        "from": dt_from.isoformat(),
        "to": dt_to_display.isoformat(),
        "series": series,
    }


def _parse_analytics_range(
    date_from: Optional[str],
    date_to: Optional[str],
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime, datetime]:
    current = now or datetime.now(timezone.utc)

    def _parse_start(value: Optional[str], fallback: datetime) -> datetime:
        if not value:
            return fallback
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _parse_end(value: Optional[str], fallback: datetime) -> tuple[datetime, datetime]:
        if not value:
            return fallback, fallback
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback, fallback
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        is_date_only = len(value.strip()) == 10
        exclusive = parsed + timedelta(days=1) if is_date_only else parsed
        return exclusive, parsed

    fallback_from = current - timedelta(days=30)
    start = _parse_start(date_from, fallback_from)
    end_exclusive, end_display = _parse_end(date_to, current)
    if end_exclusive <= start:
        end_exclusive = start + timedelta(days=1)
        end_display = end_exclusive - timedelta(seconds=1)
    return start, end_exclusive, end_display


def _parse_event_types(event_type: Optional[str]) -> List[str]:
    if not event_type:
        return []
    seen = set()
    result: List[str] = []
    for raw in str(event_type).split(","):
        candidate = raw.strip()
        if not candidate or candidate in seen:
            continue
        if candidate.replace("_", "").isalnum():
            seen.add(candidate)
            result.append(candidate)
    return result


def _bucket_range(start: datetime, end_display: datetime, granularity: str) -> List[datetime]:
    if granularity == "month":
        cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    elif granularity == "week":
        base = start.astimezone(timezone.utc)
        cur = datetime(base.year, base.month, base.day, tzinfo=timezone.utc) - timedelta(days=base.weekday())
    elif granularity == "hour":
        base = start.astimezone(timezone.utc)
        cur = datetime(base.year, base.month, base.day, base.hour, tzinfo=timezone.utc)
    else:
        base = start.astimezone(timezone.utc)
        cur = datetime(base.year, base.month, base.day, tzinfo=timezone.utc)

    end_key = _bucket_key(end_display, granularity)
    buckets: List[datetime] = []
    for _ in range(500):
        buckets.append(cur)
        if _bucket_key(cur, granularity) == end_key:
            break
        if granularity == "month":
            year = cur.year + (1 if cur.month == 12 else 0)
            month = 1 if cur.month == 12 else cur.month + 1
            cur = datetime(year, month, 1, tzinfo=timezone.utc)
        elif granularity == "week":
            cur = cur + timedelta(weeks=1)
        elif granularity == "hour":
            cur = cur + timedelta(hours=1)
        else:
            cur = cur + timedelta(days=1)
    return buckets


def _bucket_key(value: datetime, granularity: str) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    if granularity == "month":
        return value.strftime("%Y-%m-01")
    if granularity == "week":
        week_start = value - timedelta(days=value.weekday())
        return week_start.strftime("%Y-%m-%d")
    if granularity == "hour":
        return value.strftime("%Y-%m-%dT%H:00:00+00:00")
    return value.strftime("%Y-%m-%d")


def get_analytics_funnel(
    db_session: Session, organization_id: int, steps: List[str]
) -> Dict[str, Any]:
    """
    Funnel conversion for a sequence of event types.

    For each step, counts the distinct users who performed that event
    (within the last 30 days by default, scoped to the org).
    Conversion % is relative to the previous step.
    """
    if not steps:
        return {"steps": []}

    now = datetime.now(timezone.utc)
    window_30d = now - timedelta(days=30)

    # Whitelist allowed event_type characters to prevent SQL injection in the CASE block.
    # Event types are alphanumeric + underscore only.
    import re as _re
    _SAFE_EVENT_TYPE = _re.compile(r'^[a-z][a-z0-9_]{0,63}$')
    safe_steps = [s for s in steps if _SAFE_EVENT_TYPE.match(s)]
    if not safe_steps:
        return {"steps": []}

    # Build a single query: count distinct users per event_type for this org
    # We use a VALUES list for the step order, then LEFT JOIN counts.
    # Steps are embedded as string literals inside the VALUES — safe because
    # we have already validated each string against a strict regex whitelist.
    values_clause = ", ".join(f"('{s}', {i + 1})" for i, s in enumerate(safe_steps))

    sql = text(f"""
        WITH step_order(event_type, step_rank) AS (
            VALUES {values_clause}
        ),
        counts AS (
            SELECT
                event_type,
                COUNT(DISTINCT user_location_id) AS user_count
            FROM crm_events
            WHERE organization_id = :org_id
              AND occurred_at >= :window_30d
              AND event_type IN ({', '.join(f"'{s}'" for s in safe_steps)})
            GROUP BY event_type
        )
        SELECT
            so.step_rank,
            so.event_type,
            COALESCE(c.user_count, 0)::INT AS user_count
        FROM step_order so
        LEFT JOIN counts c ON c.event_type = so.event_type
        ORDER BY so.step_rank
    """)

    rows = db_session.execute(
        sql, {"org_id": organization_id, "window_30d": window_30d}
    ).fetchall()

    result_steps = []
    prev_count: Optional[int] = None
    for row in rows:
        count = int(row[2])
        conversion_pct = None
        if prev_count is not None:
            conversion_pct = round((count / prev_count * 100) if prev_count > 0 else 0, 2)
        result_steps.append(
            {
                "step": int(row[0]),
                "eventType": row[1],
                "userCount": count,
                "conversionPct": conversion_pct,
            }
        )
        prev_count = count

    return {
        "organizationId": organization_id,
        "from": window_30d.isoformat(),
        "to": now.isoformat(),
        "steps": result_steps,
    }
