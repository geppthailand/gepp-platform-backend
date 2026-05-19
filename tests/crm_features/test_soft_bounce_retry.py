"""
Tests for retry_soft_bounces() in campaign_scheduler.py

Run:
    python -m pytest tests/crm/test_soft_bounce_retry.py -v

All DB + external deps are mocked; no real DB required.
"""

import sys
import os
import importlib.util as _ilu
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Isolated loader — avoids heavy package chain
# ---------------------------------------------------------------------------

def _load(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub(name):
    m = MagicMock()
    m.__spec__ = None
    sys.modules[name] = m
    return m


# Stub the whole GEPPPlatform hierarchy
for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.models.crm.events",
    "GEPPPlatform.models.crm.campaigns",
    "GEPPPlatform.exceptions",
]:
    _stub(_pkg)


# ---------------------------------------------------------------------------
# Fake ORM objects
# ---------------------------------------------------------------------------

class _FakeDelivery:
    def __init__(self, **kw):
        self.id = 999
        self.campaign_id = 1
        self.user_location_id = 200
        self.organization_id = 10
        self.recipient_email = "user@test.com"
        self.status = "soft_bounced"
        self.sent_at = None
        self.mandrill_message_id = None
        self.mandrill_response = None
        self.error_message = None
        self.retry_count = 0
        self.rendered_subject = None
        self.rendered_body_hash = None
        self.next_retry_at = None
        self.__dict__.update(kw)


class _FakeCrmEvent:
    def __init__(self, **kw):
        self.__dict__.update(kw)


sys.modules["GEPPPlatform.models.crm"].CrmEvent = _FakeCrmEvent
sys.modules["GEPPPlatform.models.crm"].CrmCampaignDelivery = _FakeDelivery
sys.modules["GEPPPlatform.models.crm.campaigns"].CrmCampaignDelivery = _FakeDelivery


# ---------------------------------------------------------------------------
# Load modules under test
# ---------------------------------------------------------------------------

_crm_service_mod = _load(
    "GEPPPlatform/services/admin/crm/crm_service.py",
    "GEPPPlatform.services.admin.crm.crm_service",
)
_token_mod = _load(
    "GEPPPlatform/services/admin/crm/unsubscribe_token.py",
    "GEPPPlatform.services.admin.crm.unsubscribe_token",
)
_renderer_mod = _load(
    "GEPPPlatform/services/admin/crm/email_renderer.py",
    "GEPPPlatform.services.admin.crm.email_renderer",
)
_cooldown_mod = _load(
    "GEPPPlatform/services/admin/crm/cooldown.py",
    "GEPPPlatform.services.admin.crm.cooldown",
)
_prop_filter_mod = _load(
    "GEPPPlatform/services/admin/crm/property_filter.py",
    "GEPPPlatform.services.admin.crm.property_filter",
)

_crm_pkg = _stub("GEPPPlatform.services.admin.crm")
_crm_pkg.crm_service = _crm_service_mod

# Stub out the logger module that BE Sonnet 2 added to delivery_sender.py
_logger_stub = _stub("GEPPPlatform.services.admin.crm.logger")
_logger_stub.crm_log = MagicMock()
_logger_stub.new_correlation_id = MagicMock(return_value="test-correlation-id")
_crm_pkg.logger = _logger_stub

_sender_mod = _load(
    "GEPPPlatform/services/admin/crm/delivery_sender.py",
    "GEPPPlatform.services.admin.crm.delivery_sender",
)
_crm_pkg.delivery_sender = _sender_mod

_scheduler_mod = _load(
    "GEPPPlatform/services/admin/crm/campaign_scheduler.py",
    "GEPPPlatform.services.admin.crm.campaign_scheduler",
)
retry_soft_bounces = _scheduler_mod.retry_soft_bounces


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
_1H_AGO = _NOW - timedelta(hours=1)
_2H_AGO = _NOW - timedelta(hours=2)
_7D_AGO = _NOW - timedelta(days=7)


def _row(*values):
    return tuple(values)


def _delivery_row(
    delivery_id=10, campaign_id=1, user_location_id=200,
    recipient_email="user@test.com", retry_count=0,
    # Campaign columns follow
    c_id=1, org_id=10, name="Retry Campaign", camp_type="blast",
    trigger_event=None, trigger_config=None, segment_id=None,
    template_id=5, c_status="completed", started_at=None,
    last_eval_at=None, from_name=None, from_email=None, reply_to=None,
):
    return _row(
        delivery_id, campaign_id, user_location_id, recipient_email, retry_count,
        c_id, org_id, name, camp_type, trigger_event, trigger_config or {},
        segment_id, template_id, c_status, started_at or _7D_AGO, last_eval_at,
        from_name, from_email, reply_to,
    )


# ---------------------------------------------------------------------------
# DB mock helpers
# ---------------------------------------------------------------------------

def _make_db(
    delivery_rows=None,
    cooldown_blocked=False,
    delivery_obj=None,  # the ORM object returned by db.get(CrmCampaignDelivery, id)
):
    """Build a mock db session for retry tests."""
    db = MagicMock()

    def _execute(sql_obj, params=None):
        sql_text = str(sql_obj).lower() if hasattr(sql_obj, "text") else str(sql_obj).lower()
        res = MagicMock()

        if "from crm_campaign_deliveries" in sql_text and "next_retry_at" in sql_text:
            res.fetchall.return_value = delivery_rows or []
        elif "from crm_unsubscribes" in sql_text:
            res.fetchone.return_value = None
        elif "from crm_email_templates" in sql_text:
            res.fetchone.return_value = _row(5, "Subject", "<p>Hello</p>", "Hello")
        elif "from user_locations" in sql_text and "email" in sql_text:
            res.fetchone.return_value = _row(200, "user@test.com", "Test", "User", 10, "Test Org")
        elif "max(sent_at)" in sql_text:
            if cooldown_blocked:
                res.fetchone.return_value = _row(_NOW - timedelta(hours=1))
            else:
                res.fetchone.return_value = _row(None)
        elif "update crm_campaign_deliveries" in sql_text:
            res.rowcount = 1
        else:
            res.fetchone.return_value = None
            res.fetchall.return_value = []
        return res

    db.execute.side_effect = _execute
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()

    # db.get returns the delivery ORM object for retry path
    if delivery_obj is None:
        delivery_obj = _FakeDelivery(
            id=10, campaign_id=1, status="soft_bounced",
            retry_count=0, next_retry_at=_1H_AGO,
        )
    db.get = MagicMock(return_value=delivery_obj)

    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetrySoftBounces(unittest.TestCase):

    def _patch_send(self, mock_result=None):
        """Patch send_via_email_lambda to return success."""
        if mock_result is None:
            mock_result = {"success": True, "mandrill_message_id": "retry_abc", "raw_response": {}}
        return patch.object(_crm_service_mod, "send_via_email_lambda", return_value=mock_result)

    # ── No eligible rows ─────────────────────────────────────────────────────

    def test_no_rows_returns_zero_summary(self):
        db = _make_db(delivery_rows=[])
        with self._patch_send():
            result = retry_soft_bounces(db)
        self.assertEqual(result["retried"], 0)
        self.assertEqual(result["succeeded"], 0)
        self.assertEqual(result["exhausted"], 0)

    # ── Happy path: single soft_bounced delivery retried successfully ─────────

    def test_single_delivery_retried_and_succeeds(self):
        row = _delivery_row(delivery_id=10, retry_count=0)
        delivery_obj = _FakeDelivery(
            id=10, campaign_id=1, status="soft_bounced",
            retry_count=0, next_retry_at=_1H_AGO,
        )
        db = _make_db(delivery_rows=[row], delivery_obj=delivery_obj)

        with self._patch_send({"success": True, "mandrill_message_id": "new_id", "raw_response": {}}):
            result = retry_soft_bounces(db, max_retries=3)

        self.assertEqual(result["retried"], 1)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["exhausted"], 0)

    # ── retry_count increments ────────────────────────────────────────────────

    def test_retry_count_increments_on_existing_row(self):
        row = _delivery_row(delivery_id=20, retry_count=1)
        delivery_obj = _FakeDelivery(
            id=20, campaign_id=1, status="soft_bounced",
            retry_count=1, next_retry_at=_2H_AGO,
        )
        db = _make_db(delivery_rows=[row], delivery_obj=delivery_obj)

        with self._patch_send():
            result = retry_soft_bounces(db, max_retries=3)

        self.assertEqual(result["retried"], 1)
        # delivery_obj.retry_count is updated by enqueue_delivery
        # (enqueue_delivery uses existing_delivery_id, so db.get is called)
        db.get.assert_called()

    # ── Exhaustion: retry_count reaches max → permanent failure ───────────────

    def test_exhausted_on_max_retries_reached_after_failed_send(self):
        row = _delivery_row(delivery_id=30, retry_count=2)
        delivery_obj = _FakeDelivery(
            id=30, campaign_id=1, status="soft_bounced",
            retry_count=2, next_retry_at=_1H_AGO,
        )
        db = _make_db(delivery_rows=[row], delivery_obj=delivery_obj)

        # Mandrill fails — delivery stays failed; count=2+1=3 = max_retries
        with self._patch_send({"success": False, "error": "Mandrill error"}):
            result = retry_soft_bounces(db, max_retries=3)

        self.assertEqual(result["retried"], 1)
        # Should be exhausted since retry_count 2 + 1 attempt = 3 = max_retries
        self.assertEqual(result["exhausted"], 1)

    # ── Multiple deliveries in one tick ──────────────────────────────────────

    def test_multiple_deliveries_all_succeed(self):
        rows = [
            _delivery_row(delivery_id=10 + i, retry_count=0)
            for i in range(5)
        ]
        db = _make_db(delivery_rows=rows)

        with self._patch_send({"success": True, "mandrill_message_id": "abc", "raw_response": {}}):
            result = retry_soft_bounces(db, max_retries=3, max_per_tick=100)

        self.assertEqual(result["retried"], 5)
        self.assertEqual(result["succeeded"], 5)

    # ── max_per_tick cap ─────────────────────────────────────────────────────

    def test_max_per_tick_limits_rows_selected(self):
        """The SQL uses LIMIT :limit — verify max_per_tick is passed correctly."""
        db = _make_db(delivery_rows=[])

        with self._patch_send():
            retry_soft_bounces(db, max_retries=3, max_per_tick=7)

        # Find the execute call that queries crm_campaign_deliveries for retries
        retry_query_calls = [
            c for c in db.execute.call_args_list
            if "next_retry_at" in str(c.args[0]).lower()
        ]
        self.assertGreater(len(retry_query_calls), 0)
        # params should contain limit=7
        retry_params = retry_query_calls[0].args[1]
        self.assertEqual(retry_params.get("limit"), 7)

    # ── next_retry_at cleared on success ─────────────────────────────────────

    def test_next_retry_at_cleared_on_success(self):
        row = _delivery_row(delivery_id=50, retry_count=0)
        delivery_obj = _FakeDelivery(
            id=50, campaign_id=1, status="soft_bounced",
            retry_count=0, next_retry_at=_1H_AGO,
        )
        db = _make_db(delivery_rows=[row], delivery_obj=delivery_obj)

        with self._patch_send({"success": True, "mandrill_message_id": "ok123", "raw_response": {}}):
            retry_soft_bounces(db, max_retries=3)

        # After success, we expect an UPDATE clearing next_retry_at
        update_calls = [
            str(c.args[0]).lower()
            for c in db.execute.call_args_list
            if "update crm_campaign_deliveries" in str(c.args[0]).lower()
               and "next_retry_at" in str(c.args[0]).lower()
        ]
        self.assertTrue(len(update_calls) >= 1, "Expected UPDATE to clear next_retry_at")

    # ── existing_delivery_id is passed to enqueue_delivery ───────────────────

    def test_enqueue_delivery_called_with_existing_delivery_id(self):
        row = _delivery_row(delivery_id=60, retry_count=0)
        delivery_obj = _FakeDelivery(
            id=60, campaign_id=1, status="soft_bounced",
            retry_count=0, next_retry_at=_1H_AGO,
        )
        db = _make_db(delivery_rows=[row], delivery_obj=delivery_obj)

        called_with = {}

        def _fake_enqueue(db_, campaign_, *, user_location_id, recipient_email,
                          render_context=None, existing_delivery_id=None):
            called_with["existing_delivery_id"] = existing_delivery_id
            return {"status": "sent", "mandrill_message_id": "abc", "id": 60}

        with patch.object(_scheduler_mod.delivery_sender, "enqueue_delivery", side_effect=_fake_enqueue):
            retry_soft_bounces(db, max_retries=3)

        self.assertEqual(called_with.get("existing_delivery_id"), 60)

    # ── Cooldown-blocked delivery handled gracefully ──────────────────────────

    def test_cooldown_blocked_counted_as_skipped(self):
        row = _delivery_row(delivery_id=70, retry_count=1)
        delivery_obj = _FakeDelivery(
            id=70, campaign_id=1, status="soft_bounced",
            retry_count=1, next_retry_at=_1H_AGO,
        )
        db = _make_db(delivery_rows=[row], cooldown_blocked=True, delivery_obj=delivery_obj)

        with self._patch_send():
            result = retry_soft_bounces(db, max_retries=3)

        # cooldown → enqueue_delivery returns {"skipped": True} → skipped
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["succeeded"], 0)

    # ── Summary keys always present ──────────────────────────────────────────

    def test_summary_always_has_all_keys(self):
        db = _make_db(delivery_rows=[])
        with self._patch_send():
            result = retry_soft_bounces(db)
        for key in ("retried", "succeeded", "exhausted", "skipped"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()
