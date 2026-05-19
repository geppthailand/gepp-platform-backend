"""
HMAC-signed unsubscribe token utility.

Token format:  urlsafe_b64encode(email_bytes + b"|" + sig_bytes)
where sig = HMAC-SHA256(SECRET, email_bytes).digest()

The token is stateless — no DB lookup needed at issue time.
Verification requires only the shared SECRET.

Secret precedence (dev-friendly):
  1. CRM_UNSUB_SECRET env var
  2. JWT_SECRET_KEY env var  (so dev works without extra env)
  3. hard-coded 'dev-fallback' (local-only, never in prod)
"""

import os
import hmac
import hashlib
import logging
from base64 import urlsafe_b64encode, urlsafe_b64decode
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_URL_DEFAULT = "https://api.gepp.me"


def _get_secret() -> bytes:
    secret = (
        os.environ.get("CRM_UNSUB_SECRET")
        or os.environ.get("JWT_SECRET_KEY")
        or "dev-fallback"
    )
    return secret.encode("utf-8")


def _sign(email: str) -> bytes:
    """Return raw HMAC-SHA256 digest for email."""
    return hmac.new(_get_secret(), email.encode("utf-8"), hashlib.sha256).digest()


def make_unsub_url(email: str, base_url: Optional[str] = None) -> str:
    """
    Issue a signed unsubscribe URL for *email*.

    Returns:
        Full URL string, e.g.
        'https://api.gepp.me/api/crm/unsubscribe/<token>'

    The token embeds the email so no DB roundtrip is needed to verify.
    """
    if not base_url:
        base_url = os.environ.get("API_BASE_URL", _BASE_URL_DEFAULT).rstrip("/")

    email_bytes = email.encode("utf-8")
    sig = _sign(email)
    raw = email_bytes + b"|" + sig
    token = urlsafe_b64encode(raw).decode("ascii")
    return f"{base_url}/api/crm/unsubscribe/{token}"


def verify_unsub_token(token: str) -> Optional[str]:
    """
    Verify a token produced by :func:`make_unsub_url`.

    Returns:
        The email address if the token is valid and unmodified.
        None if the token is malformed, expired (tokens don't expire —
        use crm_unsubscribes for idempotency), or the HMAC is invalid.
    """
    try:
        raw = urlsafe_b64decode(token + "==")  # pad defensively
    except Exception:
        logger.debug("verify_unsub_token: base64 decode failed")
        return None

    # Split on the *last* occurrence of b"|" so emails with "|" can't spoof
    sep = raw.rfind(b"|")
    if sep == -1:
        logger.debug("verify_unsub_token: no separator found")
        return None

    email_bytes = raw[:sep]
    sig_bytes = raw[sep + 1:]

    if len(sig_bytes) != 32:  # SHA-256 digest is always 32 bytes
        logger.debug("verify_unsub_token: wrong sig length")
        return None

    email = email_bytes.decode("utf-8", errors="replace")
    expected = _sign(email)

    if not hmac.compare_digest(expected, sig_bytes):
        logger.debug("verify_unsub_token: HMAC mismatch")
        return None

    return email
