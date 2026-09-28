"""
Cookie-consent admin handlers — the READ side of the PDPA consent audit log.

The write side lives in services/public/cookie_consent_handler.py (the gepp.me banner
POSTs there). `cookie_consent_log` is append-only, so "history" is simply every row for
a given `consent_id` ordered by time — a visitor who accepts, later rejects, then edits
their preferences produces three rows, and all three must stay visible.

Routes:
  GET /admin/crm-cookie-consent           → list_crm_cookie_consents
  GET /admin/crm-cookie-consent/summary   → get_cookie_consent_summary
  GET /admin/crm-cookie-consent/{id}      → get_crm_cookie_consent

PDPA note: `cookie_consent_log` never stored a raw IP — only a salted sha256. Nothing
here can reverse that, and no join to a real identity is attempted.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import NotFoundException

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"accept_all", "reject_all", "custom"}

# Guardrail for the summary timeseries: a visitor-facing banner can log a lot of rows,
# and an unbounded window would scan the whole table on every page load.
_MAX_SUMMARY_DAYS = 365
_DEFAULT_SUMMARY_DAYS = 30


def _int_param(qp: dict, key: str, default: int, *, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(qp.get(key) or default)))
    except (TypeError, ValueError):
        return default


def _serialize(row) -> Dict[str, Any]:
    d = dict(row._mapping)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return {
        "id": d.get("id"),
        "consentId": str(d.get("consent_id")) if d.get("consent_id") else None,
        "necessary": d.get("necessary"),
        "analytics": d.get("analytics"),
        "preferences": d.get("preferences"),
        "marketing": d.get("marketing"),
        "policyVersion": d.get("policy_version"),
        "action": d.get("action"),
        "pageUrl": d.get("page_url"),
        "referrer": d.get("referrer"),
        "userAgent": d.get("user_agent"),
        "origin": d.get("origin"),
        "country": d.get("country"),
        "ipHash": d.get("ip_hash"),
        "consentedAt": d.get("consented_at"),
        "createdDate": d.get("created_date"),
    }


_SELECT_COLS = """
    id, consent_id, necessary, analytics, preferences, marketing,
    policy_version, action, page_url, referrer, user_agent, origin,
    country, ip_hash, consented_at, created_date
"""


def _build_filters(query_params: dict) -> tuple:
    """Return (where_sql, params). All values bound — never interpolated."""
    clauses: List[str] = ["1=1"]
    params: Dict[str, Any] = {}

    action = (query_params.get("action") or "").strip()
    if action in VALID_ACTIONS:
        clauses.append("action = :action")
        params["action"] = action

    consent_id = (query_params.get("consentId") or query_params.get("consent_id") or "").strip()
    if consent_id:
        # Cast the column, not the input: a malformed uuid string must filter to zero
        # rows rather than raise a Postgres cast error on the whole request.
        clauses.append("consent_id::text = :consent_id")
        params["consent_id"] = consent_id

    country = (query_params.get("country") or "").strip()
    if country:
        clauses.append("country = :country")
        params["country"] = country

    for key, col in (("dateFrom", "created_date >= :date_from"), ("dateTo", "created_date <= :date_to")):
        value = (query_params.get(key) or "").strip()
        if value:
            clauses.append(col)
            params["date_from" if key == "dateFrom" else "date_to"] = value

    q = (query_params.get("q") or "").strip()
    if q:
        clauses.append(
            "(consent_id::text ILIKE :q OR page_url ILIKE :q OR referrer ILIKE :q"
            " OR country ILIKE :q OR origin ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    return " AND ".join(clauses), params


def list_crm_cookie_consents(db: Session, query_params: dict) -> Dict[str, Any]:
    """Paginated consent log, newest first. Filter by consentId to get one visitor's history."""
    query_params = query_params or {}
    page = _int_param(query_params, "page", 1, lo=1, hi=10_000_000)
    page_size = _int_param(query_params, "pageSize", 25, lo=1, hi=200)

    where_sql, params = _build_filters(query_params)

    total = db.execute(
        text(f"SELECT COUNT(*) FROM cookie_consent_log WHERE {where_sql}"), params
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT {_SELECT_COLS}
            FROM cookie_consent_log
            WHERE {where_sql}
            ORDER BY created_date DESC, id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).fetchall()

    return {
        "items": [_serialize(r) for r in rows],
        "total": int(total or 0),
        "page": page,
        "pageSize": page_size,
    }


def get_crm_cookie_consent(db: Session, resource_id: int) -> Dict[str, Any]:
    row = db.execute(
        text(f"SELECT {_SELECT_COLS} FROM cookie_consent_log WHERE id = :id"),
        {"id": resource_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Cookie consent record {resource_id} not found")
    return _serialize(row)


def get_cookie_consent_summary(db: Session, query_params: dict) -> Dict[str, Any]:
    """
    Headline counters + a daily timeseries for the Cookie History page.

    `visitors` counts DISTINCT consent_id, not rows: one person changing their mind
    three times is one visitor, and conflating the two would overstate reach.
    """
    query_params = query_params or {}
    days = _int_param(query_params, "days", _DEFAULT_SUMMARY_DAYS, lo=1, hi=_MAX_SUMMARY_DAYS)
    where_sql, params = _build_filters(query_params)

    totals = db.execute(
        text(f"""
            SELECT
                COUNT(*)                                             AS events,
                COUNT(DISTINCT consent_id)                           AS visitors,
                COUNT(*) FILTER (WHERE action = 'accept_all')        AS accept_all,
                COUNT(*) FILTER (WHERE action = 'reject_all')        AS reject_all,
                COUNT(*) FILTER (WHERE action = 'custom')            AS custom,
                COUNT(*) FILTER (WHERE analytics)                    AS analytics_granted,
                COUNT(*) FILTER (WHERE preferences)                  AS preferences_granted,
                COUNT(*) FILTER (WHERE marketing)                    AS marketing_granted
            FROM cookie_consent_log
            WHERE {where_sql}
        """),
        params,
    ).fetchone()

    t = dict(totals._mapping) if totals else {}
    events = int(t.get("events") or 0)

    series = db.execute(
        text(f"""
            SELECT
                (created_date AT TIME ZONE 'UTC')::date              AS day,
                COUNT(*)                                             AS events,
                COUNT(*) FILTER (WHERE action = 'accept_all')        AS accept_all,
                COUNT(*) FILTER (WHERE action = 'reject_all')        AS reject_all,
                COUNT(*) FILTER (WHERE action = 'custom')            AS custom
            FROM cookie_consent_log
            WHERE {where_sql}
              AND created_date >= NOW() - (:days * INTERVAL '1 day')
            GROUP BY 1
            ORDER BY 1
        """),
        {**params, "days": days},
    ).fetchall()

    def _pct(n: Any) -> float:
        return round((int(n or 0) / events) * 100, 1) if events else 0.0

    return {
        "events": events,
        "visitors": int(t.get("visitors") or 0),
        "byAction": {
            "accept_all": int(t.get("accept_all") or 0),
            "reject_all": int(t.get("reject_all") or 0),
            "custom": int(t.get("custom") or 0),
        },
        "granted": {
            "analytics": int(t.get("analytics_granted") or 0),
            "preferences": int(t.get("preferences_granted") or 0),
            "marketing": int(t.get("marketing_granted") or 0),
        },
        "grantedPct": {
            "analytics": _pct(t.get("analytics_granted")),
            "preferences": _pct(t.get("preferences_granted")),
            "marketing": _pct(t.get("marketing_granted")),
        },
        "days": days,
        "series": [
            {
                "day": r._mapping["day"].isoformat() if r._mapping["day"] else None,
                "events": int(r._mapping["events"] or 0),
                "acceptAll": int(r._mapping["accept_all"] or 0),
                "rejectAll": int(r._mapping["reject_all"] or 0),
                "custom": int(r._mapping["custom"] or 0),
            }
            for r in series
        ],
    }


def dispatch_cookie_consent_subroute(
    resource_id: Optional[int],
    sub_path: str,
    method: str,
    db: Session,
    query_params: dict,
) -> Dict[str, Any]:
    """Called from crm/__init__.py when resource == 'crm-cookie-consent'."""
    parts = [p for p in (sub_path or "").strip("/").split("/") if p]

    if method == "GET" and parts == ["summary"]:
        return get_cookie_consent_summary(db, query_params)

    raise NotFoundException(
        f"crm-cookie-consent sub-route not found: {method} /{sub_path}"
    )
