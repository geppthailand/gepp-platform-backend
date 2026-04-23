"""
Unit tests for GEPPPlatform/services/webhooks/mailchimp_handler.py

Run from v3/backend/:
    python -m pytest tests/test_mailchimp_webhook.py -v

Or standalone:
    python -m unittest tests.test_mailchimp_webhook
"""

import sys
import os
import hmac
import base64
import hashlib
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, quote_plus

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.webhooks.mailchimp_handler import (
    verify_signature,
    parse_events,
    handle_mailchimp_webhook,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WEBHOOK_KEY = "test_secret_key_12345"
_WEBHOOK_URL = "https://api.gepp.me/api/webhooks/mailchimp"


def _make_signature(url: str, form_body: str, key: str = _WEBHOOK_KEY) -> str:
    """
    Generate a Mailchimp-spec HMAC-SHA1 signature for the given URL + form body.

    Mailchimp Transactional spec:
        signed_string = url + sorted(key1) + sorted(val1) + sorted(key2) + ...
        signature     = base64(HMAC-SHA1(webhook_key, signed_string))

    parse_qs returns {'key': ['value', ...]} — this helper replicates the logic
    in verify_signature so we can generate valid test signatures.
    """
    from urllib.parse import parse_qs as _parse_qs
    form_params = _parse_qs(form_body)

    signed = url
    for key_name in sorted(form_params.keys()):
        for value in form_params[key_name]:
            signed += key_name + value

    mac = hmac.new(key.encode("utf-8"), signed.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


def _make_form_body(events: list) -> str:
    """Encode a list of Mandrill event dicts as an application/x-www-form-urlencoded body."""
    return urlencode({"mandrill_events": json.dumps(events)})


# A realistic Mailchimp 'open' event payload (simplified).
_SAMPLE_OPEN_EVENT = {
    "event": "open",
    "ts": 1713600000,
    "_id": "abc123def456",
    "msg": {
        "_id": "abc123def456",
        "ts": 1713600000,
        "email": "user@example.com",
        "subject": "Win back offer",
        "metadata": {
            "delivery_id": "42",
            "campaign_id": "7",
            "organization_id": "12",
        },
    },
}

_SAMPLE_HARD_BOUNCE_EVENT = {
    "event": "hard_bounce",
    "ts": 1713610000,
    "_id": "bounce789",
    "msg": {
        "_id": "bounce789",
        "ts": 1713610000,
        "email": "invalid@nowhere.com",
        "subject": "Test campaign",
        "bounce_description": "bad_mailbox",
        "metadata": {
            "delivery_id": "99",
            "campaign_id": "7",
            "organization_id": "12",
        },
    },
}


# ---------------------------------------------------------------------------
# Signature verification tests
# ---------------------------------------------------------------------------

class TestSignatureVerification(unittest.TestCase):
    """HMAC-SHA1 signature verification matches Mailchimp Transactional spec."""

    def test_valid_signature_passes(self):
        """A correctly generated signature must verify as True."""
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        sig = _make_signature(_WEBHOOK_URL, form_body)

        from urllib.parse import parse_qs
        form_params = parse_qs(form_body)

        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}):
            result = verify_signature(_WEBHOOK_URL, form_params, sig)

        self.assertTrue(result)

    def test_flipped_byte_in_signature_fails(self):
        """Tampering with a single byte in the signature must cause verification to fail."""
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        sig = _make_signature(_WEBHOOK_URL, form_body)

        # Decode, flip a byte, re-encode
        raw = bytearray(base64.b64decode(sig))
        raw[0] ^= 0xFF  # flip all bits in first byte
        tampered_sig = base64.b64encode(bytes(raw)).decode("utf-8")

        self.assertNotEqual(tampered_sig, sig)

        from urllib.parse import parse_qs
        form_params = parse_qs(form_body)

        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}):
            result = verify_signature(_WEBHOOK_URL, form_params, tampered_sig)

        self.assertFalse(result)

    def test_wrong_key_fails(self):
        """Signature generated with a different key must fail verification."""
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        sig = _make_signature(_WEBHOOK_URL, form_body, key="wrong_key")

        from urllib.parse import parse_qs
        form_params = parse_qs(form_body)

        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}):
            result = verify_signature(_WEBHOOK_URL, form_params, sig)

        self.assertFalse(result)

    def test_missing_env_key_fails(self):
        """Missing MAILCHIMP_WEBHOOK_KEY must cause verification to fail (not crash)."""
        from urllib.parse import parse_qs
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        form_params = parse_qs(form_body)
        sig = _make_signature(_WEBHOOK_URL, form_body)

        # Ensure env var is absent
        env = {k: v for k, v in os.environ.items() if k != "MAILCHIMP_WEBHOOK_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = verify_signature(_WEBHOOK_URL, form_params, sig)

        self.assertFalse(result)

    def test_empty_signature_fails(self):
        """Empty signature header must fail immediately."""
        from urllib.parse import parse_qs
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        form_params = parse_qs(form_body)

        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}):
            result = verify_signature(_WEBHOOK_URL, form_params, "")

        self.assertFalse(result)


# ---------------------------------------------------------------------------
# parse_events tests
# ---------------------------------------------------------------------------

class TestParseEvents(unittest.TestCase):
    """parse_events correctly deserializes the form-encoded mandrill_events param."""

    def test_parses_single_open_event(self):
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        events = parse_events(form_body)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "open")
        self.assertEqual(events[0]["msg"]["metadata"]["delivery_id"], "42")

    def test_parses_multiple_events(self):
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT, _SAMPLE_HARD_BOUNCE_EVENT])
        events = parse_events(form_body)
        self.assertEqual(len(events), 2)
        event_types = {e["event"] for e in events}
        self.assertIn("open", event_types)
        self.assertIn("hard_bounce", event_types)

    def test_empty_body_returns_empty_list(self):
        events = parse_events("")
        self.assertEqual(events, [])

    def test_none_body_returns_empty_list(self):
        events = parse_events(None)
        self.assertEqual(events, [])

    def test_invalid_json_returns_empty_list(self):
        form_body = urlencode({"mandrill_events": "not_valid_json["})
        events = parse_events(form_body)
        self.assertEqual(events, [])

    def test_missing_mandrill_events_param(self):
        form_body = urlencode({"other_param": "value"})
        events = parse_events(form_body)
        self.assertEqual(events, [])


# ---------------------------------------------------------------------------
# Integration-level: handle_mailchimp_webhook with mocked DB session
# ---------------------------------------------------------------------------

class TestHandleWebhook(unittest.TestCase):
    """handle_mailchimp_webhook returns correct HTTP responses."""

    def _make_event_dict(self, events: list) -> dict:
        """Build a mock API Gateway event dict with a signed body."""
        form_body = _make_form_body(events)
        sig = _make_signature(_WEBHOOK_URL, form_body)
        return {
            "body": form_body,
            "headers": {
                "x-mandrill-signature": sig,
                "host": "api.gepp.me",
            },
            "rawPath": "/api/webhooks/mailchimp",
        }

    def test_valid_signature_returns_200(self):
        event_dict = self._make_event_dict([_SAMPLE_OPEN_EVENT])
        db_mock = None  # stub — handle_mailchimp_webhook doesn't use DB in the stub body

        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}):
            response = handle_mailchimp_webhook(event_dict, db_mock)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["processed"], 1)

    def test_invalid_signature_returns_401(self):
        form_body = _make_form_body([_SAMPLE_OPEN_EVENT])
        event_dict = {
            "body": form_body,
            "headers": {
                "x-mandrill-signature": "invalidsig==",
                "host": "api.gepp.me",
            },
            "rawPath": "/api/webhooks/mailchimp",
        }

        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}):
            response = handle_mailchimp_webhook(event_dict, None)

        self.assertEqual(response["statusCode"], 401)


if __name__ == "__main__":
    unittest.main()
