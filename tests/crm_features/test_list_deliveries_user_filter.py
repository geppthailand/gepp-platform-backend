"""
Sprint 4 — Tests for list_crm_deliveries: userLocationId filter + widened response shape.

Two assertions:
  a) userLocationId filter returns only rows for that user (WHERE clause populated).
  b) Widened response shape includes openCount, clickCount, bouncedAt.

Run from v3/backend/:
    python -m pytest tests/crm/test_list_deliveries_user_filter.py -v
"""

import sys
import os
import types
import importlib.util as _ilu
import datetime as _dt
import unittest
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # v3/backend/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Minimal stubs ─────────────────────────────────────────────────────────────

def _stub(name):
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.__path__ = []
        sys.modules[name] = m
    return sys.modules[name]


for _pkg in [
    "GEPPPlatform", "GEPPPlatform.database",
    "GEPPPlatform.services", "GEPPPlatform.services.admin",
    "GEPPPlatform.services.admin.crm",
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.sql",
]:
    _stub(_pkg)

_sqlalchemy = sys.modules["sqlalchemy"]
_sqlalchemy.text = lambda s: s
# Wire stub submodule attribute (sys.modules entry alone isn't enough).
_sqlalchemy.orm = sys.modules["sqlalchemy.orm"]
_sqlalchemy.orm.Session = object

# Stub GEPPPlatform.exceptions for the crm_handlers `from ....exceptions import ...`
_stub("GEPPPlatform.exceptions")
_exc = sys.modules["GEPPPlatform.exceptions"]
class _StubAPIException(Exception): pass
_exc.NotFoundException = type("NotFoundException", (_StubAPIException,), {})
_exc.BadRequestException = type("BadRequestException", (_StubAPIException,), {})
_exc.APIException = _StubAPIException


def _load_module(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_handlers = _load_module(
    "GEPPPlatform/services/admin/crm/crm_handlers.py",
    "GEPPPlatform.services.admin.crm.crm_handlers_list_filter_test",
)
list_crm_deliveries = _handlers.list_crm_deliveries


# ── Row factory for list_crm_deliveries ──────────────────────────────────────
# list_crm_deliveries SELECT returns 19 columns (indices 0-18 after Sprint 4 additions):
# 0:id 1:campaign_id 2:campaign_name 3:user_location_id 4:recipient_email
# 5:first_name 6:last_name 7:organization_id 8:organization_name
# 9:status 10:sent_at 11:opened_at 12:first_clicked_at 13:mandrill_message_id
# 14:error_message 15:retry_count 16:open_count 17:click_count 18:bounced_at

_SENT_AT = _dt.datetime(2026, 4, 10, 8, 0, 0, tzinfo=_dt.timezone.utc)
_BOUNCED_AT = _dt.datetime(2026, 4, 10, 9, 0, 0, tzinfo=_dt.timezone.utc)


def _fake_row(
    row_id=1, campaign_id=10, campaign_name="Campaign",
    user_location_id=5, email="user@example.com",
    first_name="Alice", last_name="Smith",
    org_id=3, org_name="Acme",
    status="opened", sent_at=_SENT_AT, opened_at=None, first_clicked_at=None,
    mandrill_message_id="msg001", error_message=None, retry_count=0,
    open_count=2, click_count=1, bounced_at=None,
):
    row = MagicMock()
    values = [
        row_id, campaign_id, campaign_name,
        user_location_id, email,
        first_name, last_name,
        org_id, org_name,
        status, sent_at, opened_at, first_clicked_at,
        mandrill_message_id, error_message, retry_count,
        open_count, click_count, bounced_at,
    ]
    row.__getitem__ = lambda self, k: values[k]
    return row


def _make_db(list_rows, total=None):
    db = MagicMock()
    total = total if total is not None else len(list_rows)

    def _execute(sql_obj, params=None):
        sql = str(sql_obj)
        result = MagicMock()
        if "COUNT(*)" in sql:
            result.scalar.return_value = total
        else:
            result.fetchall.return_value = list_rows
        return result

    db.execute = MagicMock(side_effect=_execute)
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserLocationIdFilter(unittest.TestCase):
    """(a) userLocationId filter returns only that user's rows."""

    def test_user_location_id_filter_adds_param(self):
        """
        Passing userLocationId=5 must include user_location_id=5 in the SQL
        params dict passed to db.execute().
        """
        captured_params: dict = {}

        def _execute(sql_obj, params=None):
            result = MagicMock()
            if params:
                captured_params.update(params)
            result.scalar.return_value = 1
            result.fetchall.return_value = [_fake_row(user_location_id=5)]
            return result

        db = MagicMock()
        db.execute = MagicMock(side_effect=_execute)

        list_crm_deliveries(db, {'userLocationId': '5'})

        self.assertIn('user_location_id', captured_params,
                      "userLocationId must add 'user_location_id' to SQL params")
        self.assertEqual(captured_params['user_location_id'], 5)

    def test_invalid_user_location_id_is_ignored(self):
        """Non-numeric userLocationId must be silently ignored (no crash, no filter added)."""
        captured_params: dict = {}

        def _execute(sql_obj, params=None):
            result = MagicMock()
            if params:
                captured_params.update(params)
            result.scalar.return_value = 0
            result.fetchall.return_value = []
            return result

        db = MagicMock()
        db.execute = MagicMock(side_effect=_execute)

        result = list_crm_deliveries(db, {'userLocationId': 'not_a_number'})

        self.assertNotIn('user_location_id', captured_params)
        self.assertEqual(result['total'], 0)

    def test_recipient_user_id_alias(self):
        """recipientUserId query param must work as an alias for userLocationId."""
        captured_params: dict = {}

        def _execute(sql_obj, params=None):
            result = MagicMock()
            if params:
                captured_params.update(params)
            result.scalar.return_value = 1
            result.fetchall.return_value = [_fake_row(user_location_id=99)]
            return result

        db = MagicMock()
        db.execute = MagicMock(side_effect=_execute)

        list_crm_deliveries(db, {'recipientUserId': '99'})

        self.assertIn('user_location_id', captured_params)
        self.assertEqual(captured_params['user_location_id'], 99)


class TestWidenedResponseShape(unittest.TestCase):
    """(b) Widened response shape includes openCount, clickCount, bouncedAt."""

    def _make_response(self, **kwargs):
        rows = [_fake_row(**kwargs)]
        db = _make_db(rows, total=1)
        return list_crm_deliveries(db, {})

    def test_open_count_in_response(self):
        """Response items must include openCount (integer)."""
        result = self._make_response(open_count=3)
        item = result['items'][0]
        self.assertIn('openCount', item)
        self.assertEqual(item['openCount'], 3)

    def test_click_count_in_response(self):
        """Response items must include clickCount (integer)."""
        result = self._make_response(click_count=2)
        item = result['items'][0]
        self.assertIn('clickCount', item)
        self.assertEqual(item['clickCount'], 2)

    def test_bounced_at_null_when_not_bounced(self):
        """bouncedAt must be None in response when the delivery has not bounced."""
        result = self._make_response(bounced_at=None)
        item = result['items'][0]
        self.assertIn('bouncedAt', item)
        self.assertIsNone(item['bouncedAt'])

    def test_bounced_at_iso_when_bounced(self):
        """bouncedAt must be an ISO-format string when bounced_at is set."""
        result = self._make_response(bounced_at=_BOUNCED_AT)
        item = result['items'][0]
        self.assertIn('bouncedAt', item)
        self.assertIsNotNone(item['bouncedAt'])
        # Should be parseable as ISO datetime
        _dt.datetime.fromisoformat(item['bouncedAt'])

    def test_first_clicked_at_in_response(self):
        """firstClickedAt must also be present (pre-existing field, confirmed still there)."""
        clicked = _dt.datetime(2026, 4, 11, 12, 0, 0, tzinfo=_dt.timezone.utc)
        result = self._make_response(first_clicked_at=clicked)
        item = result['items'][0]
        self.assertIn('firstClickedAt', item)
        self.assertIsNotNone(item['firstClickedAt'])

    def test_full_shape_keys_present(self):
        """All expected keys must be present in the response item dict."""
        result = self._make_response()
        item = result['items'][0]
        expected_keys = [
            'id', 'campaignId', 'campaignName', 'userLocationId',
            'recipientEmail', 'recipientName', 'organizationId', 'organizationName',
            'status', 'sentAt', 'openedAt', 'firstClickedAt', 'mandrillMessageId',
            'errorMessage', 'retryCount',
            'openCount', 'clickCount', 'bouncedAt',  # Sprint 4 additions
        ]
        for key in expected_keys:
            self.assertIn(key, item, f"Response item missing key: {key}")


if __name__ == "__main__":
    unittest.main()
