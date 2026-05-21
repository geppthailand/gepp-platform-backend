"""
POST /api/public/customer-leads — public lead capture for the marketing site.

Strictly origin-allowlisted (gepp.me + www.gepp.me). Stores raw submission in
the `customer_leads` table, tagged with a `source` so we can attribute future
channels (events, partner referrals, etc.) without schema churn.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...exceptions import BadRequestException

logger = logging.getLogger(__name__)

# Origins permitted to call this endpoint. Add new ones here as needed.
ALLOWED_ORIGINS = frozenset({
    "https://gepp.me",
    "https://www.gepp.me",
})

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MAX_TEXT_LEN = 1000
_MAX_MESSAGE_LEN = 5000


def is_origin_allowed(origin: Optional[str]) -> bool:
    """True when the request Origin header matches our allowlist exactly."""
    return bool(origin) and origin in ALLOWED_ORIGINS


def _clean(value: Any, *, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if not value:
        return None
    return value[:max_len]


def handle_customer_lead_capture(
    data: dict,
    db: Session,
    request_meta: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Validates + persists a marketing-site lead submission.

    Body:
      name (required), email (required), company (required),
      type ('existing' | 'new'), message, source (default 'landing-page'),
      metadata (object — any extra context the form wants to attach)
    """
    if not isinstance(data, dict):
        raise BadRequestException("Body must be a JSON object")

    name    = _clean(data.get("name"),    max_len=_MAX_TEXT_LEN)
    email   = _clean(data.get("email"),   max_len=_MAX_TEXT_LEN)
    company = _clean(data.get("company"), max_len=_MAX_TEXT_LEN)

    if not name:
        raise BadRequestException("name is required")
    if not email:
        raise BadRequestException("email is required")
    if not _EMAIL_RE.match(email):
        raise BadRequestException("email is not a valid address")
    if not company:
        raise BadRequestException("company is required")

    lead_type = _clean(data.get("type") or data.get("lead_type"), max_len=64)
    message   = _clean(data.get("message"), max_len=_MAX_MESSAGE_LEN)
    source    = _clean(data.get("source"),  max_len=64) or "landing-page"

    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    meta = request_meta or {}
    row = db.execute(
        text(
            """
            INSERT INTO customer_leads (
                name, email, company, lead_type, message, source,
                origin, ip_address, user_agent, referrer, metadata
            ) VALUES (
                :name, :email, :company, :lead_type, :message, :source,
                :origin, :ip_address, :user_agent, :referrer, CAST(:metadata AS JSONB)
            )
            RETURNING id, created_at
            """
        ),
        {
            "name":       name,
            "email":      email,
            "company":    company,
            "lead_type":  lead_type,
            "message":    message,
            "source":     source,
            "origin":     meta.get("origin"),
            "ip_address": meta.get("ip_address"),
            "user_agent": meta.get("user_agent"),
            "referrer":   meta.get("referrer"),
            "metadata":   json.dumps(metadata),
        },
    ).fetchone()
    db.commit()

    logger.info(
        "customer_lead captured id=%s email=%s source=%s origin=%s",
        row[0], email, source, meta.get("origin"),
    )

    return {
        "ok": True,
        "id": row[0],
    }
