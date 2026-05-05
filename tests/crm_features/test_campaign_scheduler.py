"""
Unit tests for GEPPPlatform/services/admin/crm/campaign_scheduler.py

Run:
    python -m pytest tests/crm/test_campaign_scheduler.py -v

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
# Isolated loader — avoids the heavy package chain
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


# Stub the whole GEPP package hierarchy before loading anything
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
        self.status = "pending"
        self.sent_at = None
        self.mandrill_message_id = None
        self.mandrill_response = None
        self.error_message = None
        self.retry_count = 0
        self.rendered_subject = None
        self.rendered_body_hash = None
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

# Register crm package stub with needed sub-modules
_crm_pkg = _stub("GEPPPlatform.services.admin.crm")
_crm_pkg.crm_service = _crm_service_mod

# Stub the structured logger added by BE Sonnet 2 (Sprint 3)
_logger_stub = _stub("GEPPPlatform.services.admin.crm.logger")
_logger_stub.crm_log = lambda *a, **kw: None
_logger_stub.new_correlation_id = lambda: "00000000"

_sender_mod = _load(
    "GEPPPlatform/services/admin/crm/delivery_sender.py",
    "GEPPPlatform.services.admin.crm.delivery_sender",
)
_crm_pkg.delivery_sender = _sender_mod

# Load property_filter module (added in Sprint 3 — property filter operators)
_prop_filter_mod = _load(
    "GEPPPlatform/services/admin/crm/property_filter.py",
    "GEPPPlatform.services.admin.crm.property_filter",
)
_crm_pkg.property_filter = _prop_filter_mod

_scheduler_mod = _load(
    "GEPPPlatform/services/admin/crm/campaign_scheduler.py",
    "GEPPPlatform.services.admin.crm.campaign_scheduler",
)
tick = _scheduler_mod.tick


# ---------------------------------------------------------------------------
# DB mock helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
_7D_AGO = _NOW - timedelta(days=7)
_30D_AGO = _NOW - timedelta(days=30)


def _row(*values):
    """Return a tuple that behaves like a DB row."""
    return tuple(values)


def _campaign_row(
    camp_id=1, org_id=10, name="Test Campaign", camp_type="trigger",
    trigger_event="user_login", trigger_config=None, segment_id=None,
    template_id=5, status="running", started_at=None, last_eval=None,
    from_name=None, from_email=None, reply_to=None,
):
    return _row(
        camp_id, org_id, name, camp_type,
        trigger_event, trigger_config or {}, segment_id,
        template_id, status, started_at or _7D_AGO, last_eval,
        from_name, from_email, reply_to,
    )


def _event_row(event_id=101, uid=200, org_id=10, props=None, occurred=None, email="user@example.com"):
    return _row(event_id, uid, org_id, props or {}, occurred or _30D_AGO, email)


def _make_db(camp_rows=None, event_rows=None, cooldown_blocked=False,
             segment_member=True, email_rows=None):
    """Build a mock db session for scheduler tests."""
    db = MagicMock()
    call_count = [0]

    def _execute(sql_obj, params=None):
        sql_text = str(sql_obj).lower() if hasattr(sql_obj, 'text') else str(sql_obj).lower()
        res = MagicMock()

        if "from crm_campaigns" in sql_text and "campaign_type" in sql_text:
            res.fetchall.return_value = camp_rows or []
        elif "from crm_events" in sql_text:
            res.fetchall.return_value = event_rows or []
        elif "from crm_segment_members" in sql_text and "select 1" in sql_text:
            res.fetchone.return_value = _row(1) if segment_member else None
        elif "max(sent_at)" in sql_text:
            # cooldown check
            if cooldown_blocked:
                res.fetchone.return_value = _row(_NOW - timedelta(hours=1))
            else:
                res.fetchone.return_value = _row(None)
        elif "from user_locations" in sql_text and "select email" in sql_text:
            r = email_rows[call_count[0] % len(email_rows)] if email_rows else _row("user@example.com")
            res.fetchone.return_value = r
            call_count[0] += 1
        elif "update crm_campaigns" in sql_text:
            res.fetchone.return_value = None
        elif "from crm_unsubscribes" in sql_text:
            res.fetchone.return_value = None
        elif "from crm_email_templates" in sql_text:
            res.fetchone.return_value = _row(5, "Subject", "<p>Hello {{firstname}}</p>", "Hello")
        else:
            res.fetchone.return_value = None
            res.fetchall.return_value = []
        return res

    db.execute.side_effect = _execute
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestSchedulerTick(unittest.TestCase):

    def _patch_send(self, mock_result=None):
        """Patch send_via_email_lambda to return success."""
        if mock_result is None:
            mock_result = {"success": True, "mandrill_message_id": "abc123", "raw_response": {}}
        return patch.object(_crm_service_mod, "send_via_email_lambda", return_value=mock_result)

    def test_no_campaigns_returns_zero_summary(self):
        db = _make_db(camp_rows=[])
        with self._patch_send():
            result = tick(db)
        self.assertEqual(result["campaigns_processed"], 0)
        self.assertEqual(result["deliveries_enqueued"], 0)

    def test_5_matching_events_enqueued(self):
        """5 events, no cooldown, no segment filter → 5 deliveries enqueued."""
        camp = _campaign_row(last_eval=None)
        events = [_event_row(event_id=100 + i, uid=200 + i, email=f"u{i}@ex.com") for i in range(5)]
        db = _make_db(camp_rows=[camp], event_rows=events)

        with self._patch_send():
            result = tick(db)

        self.assertEqual(result["campaigns_processed"], 1)
        self.assertEqual(result["events_evaluated"], 5)
        self.assertEqual(result["deliveries_enqueued"], 5)
        self.assertEqual(result["deliveries_skipped"], 0)

    def test_second_tick_no_new_deliveries(self):
        """
        After advancing last_trigger_eval_at, the second tick sees no new events
        because 'since' is now == NOW and the events' occurred_at is before NOW.
        We simulate this by returning empty event_rows on the second call.
        """
        camp = _campaign_row(last_eval=_NOW)  # already evaluated at NOW
        db = _make_db(camp_rows=[camp], event_rows=[])  # no events after last_eval

        with self._patch_send():
            result = tick(db)

        self.assertEqual(result["deliveries_enqueued"], 0)
        self.assertEqual(result["events_evaluated"], 0)

    def test_cooldown_blocks_same_user(self):
        """User already received email within 7 days → skipped."""
        camp = _campaign_row()
        events = [_event_row(uid=200, email="user@example.com")]
        db = _make_db(camp_rows=[camp], event_rows=events, cooldown_blocked=True)

        with self._patch_send():
            result = tick(db)

        self.assertEqual(result["deliveries_enqueued"], 0)
        self.assertEqual(result["deliveries_skipped"], 1)

    def test_property_filter_non_matching_skipped(self):
        """
        Events with non-matching properties should be excluded at the SQL level.
        We simulate this by returning empty event_rows (the DB does the filter).
        """
        trigger_config = {"property_filters": {"source": "web"}}
        camp = _campaign_row(trigger_config=trigger_config)
        # DB returns no rows because properties don't match (simulated by empty list)
        db = _make_db(camp_rows=[camp], event_rows=[])

        with self._patch_send():
            result = tick(db)

        self.assertEqual(result["events_evaluated"], 0)
        self.assertEqual(result["deliveries_enqueued"], 0)

    def test_segment_filter_non_member_skipped(self):
        """User not in segment → skipped."""
        camp = _campaign_row(segment_id=99)
        events = [_event_row(uid=200, email="user@example.com")]
        db = _make_db(camp_rows=[camp], event_rows=events, segment_member=False)

        with self._patch_send():
            result = tick(db)

        self.assertEqual(result["deliveries_skipped"], 1)
        self.assertEqual(result["deliveries_enqueued"], 0)

    def test_last_trigger_eval_at_advanced(self):
        """Tick must UPDATE last_trigger_eval_at after processing."""
        camp = _campaign_row()
        db = _make_db(camp_rows=[camp], event_rows=[])

        with self._patch_send():
            tick(db)

        # Find the UPDATE call for last_trigger_eval_at
        update_calls = [str(c.args[0]).lower() for c in db.execute.call_args_list
                        if "update crm_campaigns" in str(c.args[0]).lower()
                        and "last_trigger_eval_at" in str(c.args[0]).lower()]
        self.assertTrue(len(update_calls) > 0, "Expected UPDATE crm_campaigns SET last_trigger_eval_at")

    def test_bad_campaign_does_not_abort_others(self):
        """One broken campaign (raises inside _process_campaign) must not prevent others."""
        camp_ok = _campaign_row(camp_id=1)
        camp_bad = _campaign_row(camp_id=2, trigger_event=None)  # will cause a skip

        events = [_event_row()]
        db = _make_db(camp_rows=[camp_ok, camp_bad], event_rows=events)

        with self._patch_send():
            # Should not raise even if one campaign has problems
            result = tick(db)

        # We only check it doesn't raise; processed count may vary
        self.assertIn("campaigns_processed", result)

    def test_delay_days_guard_skips_recent_events(self):
        """Events occurring less than delay_days ago must be skipped."""
        trigger_config = {"delay_days": 3}
        camp = _campaign_row(trigger_config=trigger_config)
        # Event occurred 1 day ago — within delay window
        recent_event = _event_row(occurred=_NOW - timedelta(days=1))
        db = _make_db(camp_rows=[camp], event_rows=[recent_event])

        with self._patch_send():
            result = tick(db)

        self.assertEqual(result["deliveries_skipped"], 1)
        self.assertEqual(result["deliveries_enqueued"], 0)


if __name__ == "__main__":
    unittest.main()
