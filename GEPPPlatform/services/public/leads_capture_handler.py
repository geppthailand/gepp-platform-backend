"""
POST /api/public/leads — public lead capture endpoint.

Accepts form submissions from embedded widgets.  No admin JWT required.
Server-side safeguards:
  1. reCAPTCHA v3 verification (RECAPTCHA_SECRET env var).
     If env var is unset → warn + accept (dev-mode).
  2. Per-IP rate limiting (10/min, 100/day) via crm_public_rate_limits table.
  3. Org resolved via organizations.public_form_key — never expose internal org ID in JS.
  4. Returns {ok: true, leadId} only.  No PII echoed back.
"""

import logging
import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...exceptions import BadRequestException, NotFoundException

logger = logging.getLogger(__name__)

# ─── Rate-limit constants ────────────────────────────────────────────────────
_MINUTE_LIMIT = 10
_DAY_LIMIT    = 100


# ─── Entry point ─────────────────────────────────────────────────────────────

def handle_public_lead_capture(
    data: dict,
    db: Session,
    request_meta: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Entry point from app.py for POST /api/public/leads.

    Body (all optional except orgPublicKey + email):
      orgPublicKey, email, firstName, lastName, company, phone, jobTitle,
      country, formId, utm: {source, medium, campaign}, pageUrl, recaptchaToken
    """
    if not isinstance(data, dict):
        raise BadRequestException("Body must be a JSON object")

    org_public_key = (data.get('orgPublicKey') or '').strip()
    if not org_public_key:
        raise BadRequestException("orgPublicKey is required")

    email_raw = (data.get('email') or '').strip()
    if not email_raw:
        raise BadRequestException("email is required")

    # ── 1. reCAPTCHA verification ────────────────────────────────────────────
    recaptcha_secret = os.environ.get('RECAPTCHA_SECRET', '').strip()
    recaptcha_token  = (data.get('recaptchaToken') or '').strip()

    if recaptcha_secret:
        if not recaptcha_token:
            raise BadRequestException("recaptchaToken is required")
        _verify_recaptcha(recaptcha_token, recaptcha_secret)
    else:
        logger.warning(
            "leads_capture_handler: RECAPTCHA_SECRET is not set — "
            "accepting request without reCAPTCHA verification (dev mode). "
            "Set RECAPTCHA_SECRET in production."
        )

    # ── 2. Per-IP rate limiting ───────────────────────────────────────────────
    ip_address = (request_meta or {}).get('ip_address') or 'unknown'
    _check_rate_limit(db, ip_address)

    # ── 3. Resolve org_id via public_form_key ─────────────────────────────────
    org_row = db.execute(
        text("SELECT id FROM organizations WHERE public_form_key = :key AND is_active = TRUE LIMIT 1"),
        {'key': org_public_key},
    ).fetchone()
    if not org_row:
        raise NotFoundException("Organization not found")
    org_id = org_row[0]

    # ── 4. Build lead data ────────────────────────────────────────────────────
    utm            = data.get('utm') or {}
    source_metadata = {
        'form_id':  data.get('formId'),
        'page_url': data.get('pageUrl'),
        'utm':      utm,
    }

    lead_data = {
        'email':      email_raw,
        'first_name': data.get('firstName') or data.get('first_name'),
        'last_name':  data.get('lastName') or data.get('last_name'),
        'company':    data.get('company'),
        'phone':      data.get('phone'),
        'job_title':  data.get('jobTitle') or data.get('job_title'),
        'country':    data.get('country'),
    }

    # ── 5. Create lead (idempotent) ───────────────────────────────────────────
    from ..admin.crm import lead_service
    lead = lead_service.create_lead(
        db,
        org_id=org_id,
        data=lead_data,
        source='web_form',
        source_metadata=source_metadata,
    )

    # ── 6. Response — never echo PII ─────────────────────────────────────────
    return {
        "ok":     True,
        "leadId": lead.get('id'),
    }


# ─── reCAPTCHA ───────────────────────────────────────────────────────────────

def _verify_recaptcha(token: str, secret: str) -> None:
    """
    Verify a reCAPTCHA v3 token against Google's siteverify endpoint.
    Raises BadRequestException on failure.
    """
    try:
        payload = urllib.parse.urlencode({
            'secret':   secret,
            'response': token,
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://www.google.com/recaptcha/api/siteverify',
            data=payload,
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        logger.error("reCAPTCHA verification request failed: %s", exc)
        raise BadRequestException("reCAPTCHA verification failed — please try again")

    if not result.get('success'):
        error_codes = result.get('error-codes') or []
        logger.warning("reCAPTCHA rejected: %s", error_codes)
        raise BadRequestException(
            f"reCAPTCHA verification failed: {', '.join(error_codes) or 'unknown error'}"
        )


# ─── Rate limiting ────────────────────────────────────────────────────────────

def _check_rate_limit(db: Session, ip: str) -> None:
    """
    Enforce per-IP limits using the crm_public_rate_limits table.
    Buckets: "minute" (10/min), "day" (100/day).
    Prunes stale windows on each call.
    """
    now = datetime.now(timezone.utc)
    _prune_old_windows(db, now)

    # Check / increment minute bucket.
    _enforce_bucket(db, ip, 'minute', window_duration=timedelta(minutes=1),
                    limit=_MINUTE_LIMIT, now=now)

    # Check / increment day bucket.
    _enforce_bucket(db, ip, 'day', window_duration=timedelta(days=1),
                    limit=_DAY_LIMIT, now=now)


def _enforce_bucket(
    db: Session,
    ip: str,
    bucket: str,
    window_duration: 'timedelta',
    limit: int,
    now: datetime,
) -> None:
    row = db.execute(
        text("""
            SELECT counter, window_start
              FROM crm_public_rate_limits
             WHERE ip = :ip AND bucket = :bucket
        """),
        {'ip': ip, 'bucket': bucket},
    ).fetchone()

    if row is None:
        # First request — insert.
        db.execute(
            text("""
                INSERT INTO crm_public_rate_limits (ip, bucket, counter, window_start)
                VALUES (:ip, :bucket, 1, :now)
                ON CONFLICT (ip, bucket) DO NOTHING
            """),
            {'ip': ip, 'bucket': bucket, 'now': now},
        )
        db.commit()
        return

    counter, window_start = row[0], row[1]

    # Normalise timezone.
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)

    # Window expired — reset.
    if now - window_start >= window_duration:
        db.execute(
            text("""
                UPDATE crm_public_rate_limits
                   SET counter = 1, window_start = :now
                 WHERE ip = :ip AND bucket = :bucket
            """),
            {'ip': ip, 'bucket': bucket, 'now': now},
        )
        db.commit()
        return

    # Window still active — check limit.
    if counter >= limit:
        from ...exceptions import APIException
        raise APIException(
            f"Rate limit exceeded ({bucket}). Please wait before submitting again.",
            status_code=429,
        )

    # Increment.
    db.execute(
        text("""
            UPDATE crm_public_rate_limits
               SET counter = counter + 1
             WHERE ip = :ip AND bucket = :bucket
        """),
        {'ip': ip, 'bucket': bucket},
    )
    db.commit()


def _prune_old_windows(db: Session, now: datetime) -> None:
    """Delete rate-limit rows older than 2 days (housekeeping)."""
    cutoff = now - timedelta(days=2)
    try:
        db.execute(
            text("DELETE FROM crm_public_rate_limits WHERE window_start < :cutoff"),
            {'cutoff': cutoff},
        )
        db.commit()
    except Exception as exc:
        logger.debug("rate limit prune failed (non-fatal): %s", exc)
