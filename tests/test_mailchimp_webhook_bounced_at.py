"""
Sprint 4 — Test: hard_bounce webhook sets bounced_at column.

This test asserts that after migration 044 adds the `bounced_at` column,
a hard_bounce Mailchimp webhook event writes `bounced_at = NOW()` to the
UPDATE statement sent to the database.

Prior to migration 044 the column didn't exist and the UPDATE silently
no-op'd (Postgres ignores SET clauses for missing columns only if the
prepared statement was built without them — the actual behaviour was that
the UPDATE raised OperationalError in SQLAlchemy, masked by the outer
try/except in _process_event).

Run from v3/backend/:
    python -m pytest tests/test_mailchimp_webhook_bounced_at.py -v
"""

import sys
import os
import json
import hmac
import base64
import hashlib
import importlib.util as _ilu
import types as _types
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlencode

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Module isolation helpers (mirror test_mailchimp_webhook.py pattern) ──────

def _stub(name):
    if name not in sys.modules:
        sys.modules[name] = _types.ModuleType(name)
        sys.modules[name].__path__ = []
    return sys.modules[name]


def _load_module(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_stub("GEPPPlatform")
_stub("GEPPPlatform.services")
_stub("GEPPPlatform.services.admin")
_crm_pkg = _stub("GEPPPlatform.services.admin.crm")
_logger_mod = _load_module(
    "GEPPPlatform/services/admin/crm/logger.py",
    "GEPPPlatform.services.admin.crm.logger",
)
_crm_pkg.logger = _logger_mod

_handler_mod = _load_module(
    "GEPPPlatform/services/webhooks/mailchimp_handler.py",
    "GEPPPlatform.services.webhooks.mailchimp_handler_bounced_at",  # unique alias
)
handle_mailchimp_webhook = _handler_mod.handle_mailchimp_webhook


# ── Helpers ──────────────────────────────────────────────────────────────────

_WEBHOOK_KEY = "sprint4_test_key"
_WEBHOOK_URL = "https://api.gepp.me/api/webhooks/mailchimp"


def _make_signature(url, form_body, key=_WEBHOOK_KEY):
    from urllib.parse import parse_qs as _pqs
    form_params = _pqs(form_body)
    signed = url
    for k in sorted(form_params.keys()):
        for v in form_params[k]:
            signed += k + v
    mac = hmac.new(key.encode(), signed.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


def _make_form_body(events):
    return urlencode({"mandrill_events": json.dumps(events)})


def _make_event_dict(events):
    form_body = _make_form_body(events)
    sig = _make_signature(_WEBHOOK_URL, form_body)
    return {
        "body": form_body,
        "headers": {"x-mandrill-signature": sig, "host": "api.gepp.me"},
        "rawPath": "/api/webhooks/mailchimp",
    }


def _make_delivery_row(
    row_id=99, status="sent", campaign_id=7, user_location_id=5,
    org_id=12, email="invalid@nowhere.com", open_count=0, click_count=0, retry_count=0
):
    row = MagicMock()
    row.__getitem__ = lambda self, k: [
        row_id, status, campaign_id, user_location_id, org_id,
        email, open_count, click_count, retry_count
    ][k]
    return row


def _make_db(delivery_row=None, existing_crm_event=None):
    db = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()

    def _execute(sql_obj, params=None):
        sql = str(sql_obj)
        result = MagicMock()
        if "crm_campaign_deliveries" in sql and "SELECT" in sql and "id, status" in sql:
            result.fetchone.return_value = delivery_row
        elif "crm_events" in sql and "SELECT 1" in sql:
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


# ── Hard bounce fixture event ─────────────────────────────────────────────────

_HARD_BOUNCE_EVENT = {
    "event": "hard_bounce",
    "ts": 1714100000,
    "_id": "sprint4_bounce_001",
    "msg": {
        "_id": "sprint4_bounce_001",
        "ts": 1714100000,
        "email": "invalid@nowhere.com",
        "subject": "Sprint 4 campaign",
        "bounce_description": "bad_mailbox",
        "metadata": {
            "delivery_id": "99",
            "campaign_id": "7",
            "organization_id": "12",
        },
    },
}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHardBounceSetsBounced_at(unittest.TestCase):
    """
    After migration 044 adds the bounced_at column, the hard_bounce webhook
    branch in mailchimp_handler.py must include 'bounced_at = NOW()' in the
    UPDATE statement sent to the database.
    """

    def test_hard_bounce_update_includes_bounced_at(self):
        """
        The UPDATE executed for a hard_bounce event must contain 'bounced_at'
        in the SQL string — which only works once the column actually exists
        in the DB (migration 044).
        """
        delivery_row = _make_delivery_row(row_id=99, status="sent")
        db = _make_db(delivery_row=delivery_row)
        event_dict = _make_event_dict([_HARD_BOUNCE_EVENT])

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
        self.assertTrue(len(update_calls) >= 1, "Expected at least one UPDATE call")

        update_sql = str(update_calls[0].args[0])
        self.assertIn(
            "bounced_at",
            update_sql,
            "hard_bounce UPDATE must set bounced_at (requires migration 044 column to exist)",
        )

    def test_hard_bounce_status_is_hard_bounced(self):
        """Status param in the UPDATE must be 'hard_bounced'."""
        delivery_row = _make_delivery_row(row_id=99, status="sent")
        db = _make_db(delivery_row=delivery_row)
        event_dict = _make_event_dict([_HARD_BOUNCE_EVENT])

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
            handle_mailchimp_webhook(event_dict, db)

        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE crm_campaign_deliveries" in str(c.args[0])
        ]
        self.assertTrue(len(update_calls) >= 1)
        params = update_calls[0].args[1]
        self.assertEqual(params.get("status"), "hard_bounced")

    def test_hard_bounce_inserts_unsubscribe(self):
        """hard_bounce must also insert into crm_unsubscribes."""
        delivery_row = _make_delivery_row(row_id=99, status="sent")
        db = _make_db(delivery_row=delivery_row)
        event_dict = _make_event_dict([_HARD_BOUNCE_EVENT])

        _crm_svc_mock = MagicMock()
        with patch.dict(os.environ, {"MAILCHIMP_WEBHOOK_KEY": _WEBHOOK_KEY}), \
             patch.dict("sys.modules", {
                 "GEPPPlatform.services.admin.crm.crm_service": _crm_svc_mock,
                 "GEPPPlatform.services.admin.crm": MagicMock(crm_service=_crm_svc_mock),
             }):
            handle_mailchimp_webhook(event_dict, db)

        unsub_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO crm_unsubscribes" in str(c.args[0])
        ]
        self.assertTrue(len(unsub_calls) >= 1, "hard_bounce must insert into crm_unsubscribes")


if __name__ == "__main__":
    unittest.main()
