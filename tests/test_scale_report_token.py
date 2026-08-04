"""Tests for the HMAC-signed public report token.

Covers the three things that must never regress: a token round-trips exactly,
a tampered token is rejected, and an expired token is distinguishable from a
forged one (410 vs 401 drive different messages on the customer's phone).
"""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import date, datetime, timezone

import pytest

from GEPPPlatform.libs.exceptions import APIException, UnauthorizedException
from GEPPPlatform.services.cores.scale_reports import scale_report_token as tok


@pytest.fixture(autouse=True)
def _pin_real_exceptions(real_api_exceptions):
    """Immunise this module from the shim mutation done by
    tests/crm_features/test_deliveries_csv.py — see the fixture's docstring."""


@pytest.fixture(autouse=True)
def fixed_secret(monkeypatch):
    """Pin the secret so tests don't depend on the developer's environment."""
    monkeypatch.setenv('SCALE_REPORT_SECRET', 'unit-test-secret')
    monkeypatch.delenv('WEB_BASE_URL', raising=False)


# ── round trip ───────────────────────────────────────────────────────────────

def test_round_trip_preserves_every_claim():
    token, expires_at = tok.make_report_token(123, 45, date(2026, 7, 26))
    claims = tok.verify_report_token(token)

    assert claims['origin_id'] == 123
    assert claims['org_id'] == 45
    assert claims['day'] == date(2026, 7, 26)
    # stored to whole seconds, so compare with that tolerance
    assert abs((claims['exp'] - expires_at).total_seconds()) < 1


def test_token_is_url_safe_and_unpadded():
    token, _ = tok.make_report_token(1, 1, date(2026, 7, 26))
    assert '=' not in token
    assert '+' not in token
    assert '/' not in token


def test_expires_at_is_naive_utc():
    _, expires_at = tok.make_report_token(1, 1, date(2026, 7, 26))
    assert expires_at.tzinfo is None


def test_default_ttl_is_48_hours():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    _, expires_at = tok.make_report_token(1, 1, date(2026, 7, 26))
    hours = (expires_at - before).total_seconds() / 3600
    assert 47.9 < hours < 48.1


# ── tampering ────────────────────────────────────────────────────────────────

def _mutate_last_byte(token: str) -> str:
    raw = bytearray(urlsafe_b64decode(token + '=='))
    raw[-1] ^= 0x01  # flip one bit of the signature
    return urlsafe_b64encode(bytes(raw)).decode('ascii').rstrip('=')


def _mutate_payload(token: str) -> str:
    """Rewrite origin_id in the payload but keep the original signature."""
    raw = urlsafe_b64decode(token + '==')
    payload, sig = raw[:-32], raw[-32:]
    fields = payload.decode().split('|')
    fields[0] = '999'
    forged = '|'.join(fields).encode()
    return urlsafe_b64encode(forged + sig).decode('ascii').rstrip('=')


def test_flipped_signature_bit_is_rejected():
    token, _ = tok.make_report_token(123, 45, date(2026, 7, 26))
    with pytest.raises(UnauthorizedException) as exc:
        tok.verify_report_token(_mutate_last_byte(token))
    assert exc.value.error_code == 'INVALID_REPORT_TOKEN'
    assert exc.value.status_code == 401


def test_rewritten_origin_id_is_rejected():
    """The whole point: a scanner must not be able to point the token
    at a location it was not issued for."""
    token, _ = tok.make_report_token(123, 45, date(2026, 7, 26))
    with pytest.raises(UnauthorizedException):
        tok.verify_report_token(_mutate_payload(token))


def test_token_signed_with_another_secret_is_rejected(monkeypatch):
    token, _ = tok.make_report_token(123, 45, date(2026, 7, 26))
    monkeypatch.setenv('SCALE_REPORT_SECRET', 'a-different-secret')
    with pytest.raises(UnauthorizedException):
        tok.verify_report_token(token)


@pytest.mark.parametrize(
    'bad',
    [
        '',
        'not-base64-!!!',
        'c2hvcnQ',                    # decodes, but shorter than a signature
        'a' * 43,                     # right-ish length, wrong content
    ],
)
def test_malformed_tokens_are_rejected(bad):
    with pytest.raises(UnauthorizedException):
        tok.verify_report_token(bad)


def test_payload_only_without_signature_is_rejected():
    payload = b'123|45|2026-07-26|9999999999'
    forged = urlsafe_b64encode(payload).decode('ascii').rstrip('=')
    with pytest.raises(UnauthorizedException):
        tok.verify_report_token(forged)


# ── expiry ───────────────────────────────────────────────────────────────────

def test_expired_token_raises_410_not_401():
    """410 tells the page to say "ask for a new QR"; 401 says "not a real
    link". Collapsing them would show customers the wrong message."""
    token, _ = tok.make_report_token(123, 45, date(2026, 7, 26), ttl_hours=-1)
    with pytest.raises(APIException) as exc:
        tok.verify_report_token(token)
    assert exc.value.status_code == 410
    assert exc.value.error_code == 'REPORT_TOKEN_EXPIRED'


def test_expired_token_is_still_signature_checked_first():
    """A tampered *and* expired token must report tampering, not expiry —
    otherwise the 410 branch becomes an oracle for unsigned payloads."""
    token, _ = tok.make_report_token(123, 45, date(2026, 7, 26), ttl_hours=-1)
    with pytest.raises(UnauthorizedException):
        tok.verify_report_token(_mutate_payload(token))


def test_token_valid_just_before_expiry():
    token, _ = tok.make_report_token(123, 45, date(2026, 7, 26), ttl_hours=1)
    assert tok.verify_report_token(token)['origin_id'] == 123


# ── URL building ─────────────────────────────────────────────────────────────

def test_build_report_url_uses_web_host_env(monkeypatch):
    monkeypatch.setenv('WEB_BASE_URL', 'https://dev.geppdata.com')
    assert tok.build_report_url('abc') == 'https://dev.geppdata.com/scale-report/abc'


def test_build_report_url_tolerates_trailing_slash(monkeypatch):
    monkeypatch.setenv('WEB_BASE_URL', 'https://dev.geppdata.com/')
    assert tok.build_report_url('abc') == 'https://dev.geppdata.com/scale-report/abc'


def test_build_report_url_defaults_to_prod_web_host():
    assert tok.build_report_url('abc') == 'https://geppdata.com/scale-report/abc'


def test_build_report_url_points_at_web_not_api():
    """Regression guard: pointing this at the API host would hand customers
    raw JSON instead of the report page."""
    url = tok.build_report_url('abc')
    assert 'api.' not in url
    assert '/scale-report/' in url
