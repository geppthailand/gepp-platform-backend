"""
Unit tests for GEPPPlatform/services/webhooks/mailchimp_handler.py

Run from v3/backend/:
    python -m pytest tests/test_mailchimp_webhook.py -v

Or standalone:
    python -m unittest tests.test_mailchimp_webhook

NOTE: The handler module is loaded in isolation via importlib.util so that
running this file alongside test_delivery_sender.py (which stubs the GEPPPlatform
package) does not cause a ModuleNotFoundError.  The heavy geoalchemy2 chain is
never triggered because mailchimp_handler only imports crm_service lazily
(inside _process_event) and we patch sys.modules for that import in tests that
exercise the event-processing path.
"""

import sys
import os
import hmac
import base64
import hashlib
import json
import importlib.util as _ilu
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode, quote_plus

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load_module(rel_path, name):
    """Load a Python file directly by path, registering it in sys.modules."""
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load the crm logger module so the handler's `from ...logger import new_correlation_id`
# resolves under isolated module loading. (Sprint 3 BE2 added structured logging.)
import types as _types
def _stub(name):
    if name not in sys.modules:
        sys.modules[name] = _types.ModuleType(name)
        sys.modules[name].__path__ = []  # mark as package
    return sys.modules[name]

_stub("GEPPPlatform")
_stub("GEPPPlatform.services")
_stub("GEPPPlatform.services.admin")
_crm_pkg = _stub("GEPPPlatform.services.admin.crm")
_logger_mod = _load_module(
    "GEPPPlatform/services/admin/crm/logger.py",
    "GEPPPlatform.services.admin.crm.logger",
)
_crm_pkg.logger = _logger_mod

# Load the handler in isolation — avoids any GEPPPlatform package __init__ chain
_handler_mod = _load_module(
    "GEPPPlatform/services/webhooks/mailchimp_handler.py",
    "GEPPPlatform.services.webhooks.mailchimp_handler",
)
verify_signature = _handler_mod.verify_signature
parse_events = _handler_mod.parse_events
handle_mailchimp_webhook = _handler_mod.handle_mailchimp_webhook


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
        # Provide a minimal db mock; patch crm_service import to avoid geoalchemy2
        db_mock = MagicMock()
        db_mock.execute = MagicMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
        db_mock.commit = MagicMock()

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
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


# ---------------------------------------------------------------------------
# New behaviour tests — Sprint 1 BE Sonnet 1
# ---------------------------------------------------------------------------

def _make_db_for_webhook(
    *,
    delivery_row=None,
    existing_crm_event=None,
):
    """
    Mock db session wired up for the real handle_mailchimp_webhook implementation.

    execute() returns different mocks depending on SQL content.
    """
    db = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()

    def _execute(sql_obj, params=None):
        sql = str(sql_obj)
        result = MagicMock()

        if "crm_campaign_deliveries" in sql and "SELECT" in sql and "id, status" in sql:
            # fetch delivery row
            result.fetchone.return_value = delivery_row

        elif "crm_events" in sql and "SELECT 1" in sql:
            # idempotency check
            result.fetchone.return_value = existing_crm_event

        elif "UPDATE crm_campaign_deliveries" in sql:
            result.rowcount = 1

        elif "INSERT INTO crm_unsubscribes" in sql:
            result.rowcount = 1

        else:
            result.fetchone.return_value = None

        return result

    db.execute = MagicMock(side_effect=_execute)
    return db


def _make_delivery_row(
    row_id=42, status="sent", campaign_id=7, user_location_id=5,
    org_id=12, email="user@example.com", open_count=0, click_count=0, retry_count=0
):
    row = MagicMock()
    row.__getitem__ = lambda self, k: [
        row_id, status, campaign_id, user_location_id, org_id,
        email, open_count, click_count, retry_count
    ][k]
    return row


class TestWebhookUnsub(unittest.TestCase):
    """unsub event must insert into crm_unsubscribes."""

    _UNSUB_EVENT = {
        "event": "unsub",
        "ts": 1713620000,
        "_id": "unsub_msg_id_001",
        "msg": {
            "_id": "unsub_msg_id_001",
            "ts": 1713620000,
            "email": "gone@away.com",
            "subject": "Campaign",
            "metadata": {
                "delivery_id": "42",
                "campaign_id": "7",
                "organization_id": "12",
            },
        },
    }

    def _make_event_dict(self, events):
        form_body = _make_form_body(events)
        sig = _make_signature(_WEBHOOK_URL, form_body)
        return {
            "body": form_body,
            "headers": {"x-mandrill-signature": sig, "host": "api.gepp.me"},
            "rawPath": "/api/webhooks/mailchimp",
        }

    def test_unsub_event_inserts_crm_unsubscribes(self):
        """unsub event must result in an INSERT into crm_unsubscribes."""
        delivery_row = _make_delivery_row(email="gone@away.com")
        db = _make_db_for_webhook(delivery_row=delivery_row)
        event_dict = self._make_event_dict([self._UNSUB_EVENT])

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
            response = handle_mailchimp_webhook(event_dict, db)

        self.assertEqual(response["statusCode"], 200)

        # Find the INSERT INTO crm_unsubscribes call
        insert_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO crm_unsubscribes" in str(c.args[0])
        ]
        self.assertTrue(len(insert_calls) >= 1, "Expected INSERT INTO crm_unsubscribes")
        # Verify email param
        params = insert_calls[0].args[1]
        self.assertEqual(params.get("email"), "gone@away.com")


class TestWebhookOpenIdempotent(unittest.TestCase):
    """open event increments open_count; second identical event is a no-op."""

    _OPEN_EVENT = {
        "event": "open",
        "ts": 1713600000,
        "_id": "open_msg_id_002",
        "msg": {
            "_id": "open_msg_id_002",
            "ts": 1713600000,
            "email": "user@example.com",
            "subject": "Win back",
            "metadata": {
                "delivery_id": "42",
                "campaign_id": "7",
                "organization_id": "12",
            },
        },
    }

    def _make_event_dict(self, events):
        form_body = _make_form_body(events)
        sig = _make_signature(_WEBHOOK_URL, form_body)
        return {
            "body": form_body,
            "headers": {"x-mandrill-signature": sig, "host": "api.gepp.me"},
            "rawPath": "/api/webhooks/mailchimp",
        }

    def test_first_open_triggers_update(self):
        """First open event must result in an UPDATE to crm_campaign_deliveries."""
        delivery_row = _make_delivery_row(status="sent", open_count=0)
        db = _make_db_for_webhook(delivery_row=delivery_row, existing_crm_event=None)
        event_dict = self._make_event_dict([self._OPEN_EVENT])

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
            response = handle_mailchimp_webhook(event_dict, db)

        self.assertEqual(response["statusCode"], 200)
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE crm_campaign_deliveries" in str(c.args[0])
        ]
        self.assertTrue(len(update_calls) >= 1, "Expected UPDATE on open event")
        # open_count increment should be in the SQL
        self.assertIn("open_count", str(update_calls[0].args[0]))

    def test_duplicate_open_is_skipped(self):
        """Second identical open event (same event+msg_id) must not produce another UPDATE."""
        delivery_row = _make_delivery_row(status="opened", open_count=1)
        # Simulate crm_events row already exists → idempotency guard returns a row
        existing = MagicMock()
        db = _make_db_for_webhook(delivery_row=delivery_row, existing_crm_event=existing)
        event_dict = self._make_event_dict([self._OPEN_EVENT])

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
            response = handle_mailchimp_webhook(event_dict, db)

        self.assertEqual(response["statusCode"], 200)
        # emit_event must NOT be called again on the crm_service mock
        _crm_svc_mock.emit_event.assert_not_called()
        # No UPDATE executed
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE crm_campaign_deliveries" in str(c.args[0])
        ]
        self.assertEqual(len(update_calls), 0, "Duplicate open should not produce UPDATE")


class TestWebhookHardBounce(unittest.TestCase):
    """hard_bounce event must update status to hard_bounced AND insert unsubscribe."""

    _BOUNCE_EVENT = {
        "event": "hard_bounce",
        "ts": 1713610000,
        "_id": "bounce_msg_id_003",
        "msg": {
            "_id": "bounce_msg_id_003",
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

    def _make_event_dict(self, events):
        form_body = _make_form_body(events)
        sig = _make_signature(_WEBHOOK_URL, form_body)
        return {
            "body": form_body,
            "headers": {"x-mandrill-signature": sig, "host": "api.gepp.me"},
            "rawPath": "/api/webhooks/mailchimp",
        }

    def test_hard_bounce_updates_status_and_inserts_unsub(self):
        delivery_row = _make_delivery_row(row_id=99, status="sent", email="invalid@nowhere.com")
        db = _make_db_for_webhook(delivery_row=delivery_row)
        event_dict = self._make_event_dict([self._BOUNCE_EVENT])

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
            response = handle_mailchimp_webhook(event_dict, db)

        self.assertEqual(response["statusCode"], 200)

        # UPDATE called with 'hard_bounced'
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE crm_campaign_deliveries" in str(c.args[0])
        ]
        self.assertTrue(len(update_calls) >= 1)
        # Status in the params
        params = update_calls[0].args[1]
        self.assertEqual(params.get("status"), "hard_bounced")

        # INSERT INTO crm_unsubscribes called
        unsub_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO crm_unsubscribes" in str(c.args[0])
        ]
        self.assertTrue(len(unsub_calls) >= 1, "hard_bounce should insert unsubscribe")


if __name__ == "__main__":
    unittest.main()
