"""HMAC-signed, self-expiring token for the public daily scale report.

Token format
------------
    urlsafe_b64encode(payload_bytes + sig_bytes).rstrip('=')

    payload = "<origin_id>|<org_id>|<YYYY-MM-DD>|<exp_epoch>"
    sig     = HMAC-SHA256(SECRET, payload_bytes).digest()   # always 32 bytes

Stateless on purpose: no migration, no table, no DB round-trip to verify, and
the link stops working on its own. The trade-off is that an individual link
cannot be revoked before it expires — acceptable for an aggregate daily figure.
If per-link revocation is ever needed, this becomes a table keyed by hash (the
shape `user_input_channels.hash` already uses).

Splitting payload from signature
--------------------------------
`services/admin/crm/unsubscribe_token.py` is the precedent for this module, but
it splits on the *last* occurrence of a separator byte. A raw SHA-256 digest is
32 arbitrary bytes and can legitimately contain that separator, so that split
can land in the wrong place. Here the digest length is fixed and known, so the
split is positional — `raw[:-32]` / `raw[-32:]` — which cannot be confused.

Secret precedence (dev-friendly, same idea as the CRM helper)
    1. SCALE_REPORT_SECRET
    2. JWT_SECRET_KEY        — so local dev works with no extra env
    3. 'dev-fallback'        — local only, never in a deployed environment
"""

import hashlib
import hmac
import logging
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Tuple

from GEPPPlatform.libs.exceptions import (
    APIException,
    UnauthorizedException,
    ValidationException,
)

from .bkk_time import DAY_FORMAT

logger = logging.getLogger(__name__)

#: How long a QR stays scannable. A customer usually scans immediately, but the
#: report is date-locked so a couple of days of slack costs nothing.
TTL_HOURS_DEFAULT = 48

#: Raw SHA-256 digest length. The payload/signature split depends on this.
_SIG_LEN = 32

_WEB_BASE_URL_DEFAULT = 'https://geppdata.com'


def _get_secret() -> bytes:
    secret = (
        os.environ.get('SCALE_REPORT_SECRET')
        or os.environ.get('JWT_SECRET_KEY')
        or 'dev-fallback'
    )
    return secret.encode('utf-8')


def _sign(payload: bytes) -> bytes:
    return hmac.new(_get_secret(), payload, hashlib.sha256).digest()


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_report_token(
    origin_id: int,
    org_id: int,
    day: date,
    ttl_hours: int = TTL_HOURS_DEFAULT,
) -> Tuple[str, datetime]:
    """Issue a token for (*origin_id*, *org_id*, *day*).

    Returns:
        (token, expires_at) — `expires_at` is naive UTC, matching how every
        other timestamp in this feature is represented.
    """
    expires_at = _utc_now_naive() + timedelta(hours=ttl_hours)
    exp_epoch = int(expires_at.replace(tzinfo=timezone.utc).timestamp())

    payload = '{0}|{1}|{2}|{3}'.format(
        int(origin_id), int(org_id), day.strftime(DAY_FORMAT), exp_epoch
    ).encode('utf-8')

    token = urlsafe_b64encode(payload + _sign(payload)).decode('ascii').rstrip('=')
    return token, expires_at


def verify_report_token(token: str) -> Dict[str, Any]:
    """Verify and decode a token issued by :func:`make_report_token`.

    Returns:
        `{'origin_id': int, 'org_id': int, 'day': date, 'exp': datetime}`

    Raises:
        UnauthorizedException: 401 — malformed, or the signature does not match.
        APIException: 410 — well-formed and authentic, but past its expiry.

    The distinction matters for the UI: 401 means "this link is not real", 410
    means "ask for a new QR at the station", and those are different messages.
    """
    if not token:
        raise UnauthorizedException('Invalid report token', 'INVALID_REPORT_TOKEN')

    try:
        # Restore the padding stripped at issue time. '==' is always enough:
        # b64 needs at most 2 pad chars and a decoder ignores extras.
        raw = urlsafe_b64decode(token + '==')
    except Exception:
        logger.debug('verify_report_token: base64 decode failed')
        raise UnauthorizedException('Invalid report token', 'INVALID_REPORT_TOKEN')

    if len(raw) <= _SIG_LEN:
        raise UnauthorizedException('Invalid report token', 'INVALID_REPORT_TOKEN')

    payload, sig = raw[:-_SIG_LEN], raw[-_SIG_LEN:]

    # Constant-time compare — a plain == leaks the digest one byte at a time.
    if not hmac.compare_digest(_sign(payload), sig):
        logger.debug('verify_report_token: HMAC mismatch')
        raise UnauthorizedException('Invalid report token', 'INVALID_REPORT_TOKEN')

    # Signature is good, so the payload is ours; a parse failure here means a
    # format change, not tampering. Still refuse rather than guess.
    try:
        origin_s, org_s, day_s, exp_s = payload.decode('utf-8').split('|')
        claims = {
            'origin_id': int(origin_s),
            'org_id': int(org_s),
            'day': datetime.strptime(day_s, DAY_FORMAT).date(),
            'exp': datetime.fromtimestamp(int(exp_s), tz=timezone.utc).replace(tzinfo=None),
        }
    except (ValueError, UnicodeDecodeError):
        logger.warning('verify_report_token: signed payload did not parse')
        raise UnauthorizedException('Invalid report token', 'INVALID_REPORT_TOKEN')

    if _utc_now_naive() >= claims['exp']:
        raise APIException(
            'This report link has expired',
            status_code=410,
            error_code='REPORT_TOKEN_EXPIRED',
        )

    return claims


#: หน้า public เลื่อนดูย้อนหลังได้กี่วันจากวันที่ฝังใน token
#:
#: 1 = ดูได้ 2 วัน (วันที่สร้าง QR กับวันก่อนหน้า) เจตนาคือให้ลูกค้าเทียบ
#: "เมื่อวานกับวันนี้" ได้ โดยไม่เปิดประวัติทั้งเดือนให้คนที่ถือ QR ใบเดียว
#: ยิ่งกว้างยิ่งบอกแนวโน้มปริมาณรับเข้าของจุดนั้นให้คนนอกรู้มากขึ้น
PUBLIC_DAY_WINDOW_DAYS = 1


def resolve_requested_day(claims: Dict[str, Any], requested):
    """หาว่าจะให้ดูวันไหน จากวันที่ผู้ใช้ขอมา — ภายในกรอบที่ token อนุญาต

    ไม่ส่ง `requested` มา = วันที่ฝังใน token

    Raises:
        ValidationException: 422 — รูปแบบวันที่ผิด
        APIException: 403 — วันที่ถูกต้องแต่อยู่นอกกรอบที่ token นี้เปิดให้
            (แยกจาก 422 เพราะคนละเรื่อง: อันหนึ่งพิมพ์ผิด อีกอันคือขอดู
            สิ่งที่ไม่ได้รับอนุญาต)
    """
    token_day: date = claims['day']
    if requested is None or requested == '':
        return token_day

    try:
        day = datetime.strptime(str(requested), DAY_FORMAT).date()
    except ValueError:
        raise ValidationException('date must be YYYY-MM-DD')

    earliest = token_day - timedelta(days=PUBLIC_DAY_WINDOW_DAYS)
    # ห้ามเลยวันใน token ไปข้างหน้า — QR ที่ออกเมื่อวานต้องไม่กลายเป็น
    # ช่องทางดูยอดของวันนี้ไปเรื่อย ๆ
    if day > token_day or day < earliest:
        raise APIException(
            'This link only covers {0} to {1}'.format(
                earliest.strftime(DAY_FORMAT), token_day.strftime(DAY_FORMAT)
            ),
            status_code=403,
            error_code='DATE_OUT_OF_RANGE',
        )
    return day


def build_report_url(token: str) -> str:
    """Full public URL a customer's phone opens after scanning the QR.

    Points at the **web** host (gepp-business SPA), not the API host. Read from
    env so the tablet never has to be rebuilt if the domain moves — the app
    renders whatever URL the API hands back.

        DEV  → https://dev.geppdata.com
        PROD → https://geppdata.com
    """
    base = (os.environ.get('WEB_BASE_URL') or _WEB_BASE_URL_DEFAULT).rstrip('/')
    return '{0}/scale-report/{1}'.format(base, token)
