"""POST /api/public/cookie-consent — PDPA cookie-consent audit log for gepp.me.

Append-only: every accept / reject / custom-save from the marketing-site banner writes one row to
`cookie_consent_log`, so a visitor's consent history (incl. later changes / withdrawals) is auditable.

Origin-allowlisted (same list as customer-leads). PDPA data-minimization: the raw client IP is never
stored — only a salted sha256 (`ip_hash`) for correlation and the coarse CloudFront `country`. The
`consent_id` is an anonymous per-browser UUID, not tied to a real identity.
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...exceptions import BadRequestException
# Reuse the single marketing-origin allowlist so both public endpoints stay in lockstep.
from .customer_leads_handler import ALLOWED_ORIGINS, is_origin_allowed  # noqa: F401

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"accept_all", "reject_all", "custom"}
_MAX_URL_LEN = 2000
_MAX_UA_LEN = 1000


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _clip(v: Any, max_len: int) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s[:max_len] if s else None


def _coerce_consent_id(v: Any) -> str:
    """Accept the browser's UUID; if missing/malformed, mint one server-side so a log is never lost."""
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid4())


def _parse_ts(v: Any) -> Optional[datetime]:
    """Parse a client ISO-8601 timestamp (tolerating a trailing 'Z'); None if unparseable."""
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _hash_ip(ip: Optional[str]) -> Optional[str]:
    """Salted sha256 of the IP — lets us correlate repeat visits WITHOUT retaining the address."""
    if not ip:
        return None
    salt = os.environ.get("COOKIE_CONSENT_IP_SALT", "gepp-cookie-consent")
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def handle_cookie_consent_log(
    data: dict,
    db: Session,
    request_meta: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Validate + append a consent decision.

    Body:
      consent_id (UUID string; minted server-side if absent),
      categories: { analytics, preferences, marketing } (booleans; necessary is always true),
      policy_version (int), action ('accept_all'|'reject_all'|'custom'),
      page_url, referrer, timestamp (client ISO time the choice was made).
    """
    if not isinstance(data, dict):
        raise BadRequestException("Body must be a JSON object")

    meta = request_meta or {}
    cats = data.get("categories")
    cats = cats if isinstance(cats, dict) else {}

    consent_id = _coerce_consent_id(data.get("consent_id") or data.get("consentId"))

    try:
        policy_version = int(data.get("policy_version") or data.get("version") or 1)
    except (ValueError, TypeError):
        policy_version = 1

    action = _clip(data.get("action"), 32) or "custom"
    if action not in _VALID_ACTIONS:
        action = "custom"

    params = {
        "consent_id": consent_id,
        "analytics": _as_bool(cats.get("analytics")),
        "preferences": _as_bool(cats.get("preferences")),
        "marketing": _as_bool(cats.get("marketing")),
        "policy_version": policy_version,
        "action": action,
        "page_url": _clip(data.get("page_url") or data.get("pageUrl") or meta.get("referrer"), _MAX_URL_LEN),
        "referrer": _clip(data.get("referrer") or meta.get("referrer"), _MAX_URL_LEN),
        "user_agent": _clip(meta.get("user_agent"), _MAX_UA_LEN),
        "origin": _clip(meta.get("origin"), 200),
        "country": _clip(meta.get("country"), 8),
        "ip_hash": _hash_ip(meta.get("ip_address")),
        "consented_at": _parse_ts(data.get("timestamp") or data.get("consented_at")),
    }

    db.execute(
        text(
            """
            INSERT INTO cookie_consent_log
                (consent_id, necessary, analytics, preferences, marketing, policy_version, action,
                 page_url, referrer, user_agent, origin, country, ip_hash, consented_at)
            VALUES
                (:consent_id, TRUE, :analytics, :preferences, :marketing, :policy_version, :action,
                 :page_url, :referrer, :user_agent, :origin, :country, :ip_hash, :consented_at)
            """
        ),
        params,
    )
    db.commit()

    logger.info(
        "cookie_consent logged consent_id=%s action=%s a=%s p=%s m=%s v=%s origin=%s country=%s",
        consent_id, action, params["analytics"], params["preferences"], params["marketing"],
        policy_version, params["origin"], params["country"],
    )

    return {"ok": True, "consent_id": consent_id}
