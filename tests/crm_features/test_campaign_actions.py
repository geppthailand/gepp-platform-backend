"""
Unit tests for campaign action endpoints:
  POST /admin/crm-campaigns/{id}/start
  POST /admin/crm-campaigns/{id}/pause
  POST /admin/crm-campaigns/{id}/resume
  POST /admin/crm-campaigns/{id}/archive
  POST /admin/crm-campaigns/{id}/test

Run:
    python -m pytest tests/crm/test_campaign_actions.py -v
"""

import sys
import os
import importlib.util as _ilu
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Isolated loader
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


for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.models.crm.events",
    "GEPPPlatform.models.crm.campaigns",
]:
    _stub(_pkg)


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


# Stub exceptions module with real exception classes so isinstance checks work
class _APIExc(Exception):
    def __init__(self, msg, status_code=400):
        self.message = msg
        self.status_code = status_code
        super().__init__(msg)

class _NotFoundExc(_APIExc):
    pass

class _BadReqExc(_APIExc):
    pass

_exc_mod = _stub("GEPPPlatform.exceptions")
_exc_mod.APIException = _APIExc
_exc_mod.NotFoundException = _NotFoundExc
_exc_mod.BadRequestException = _BadReqExc


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

# Load __init__ — the dispatcher module
_init_mod = _load(
    "GEPPPlatform/services/admin/crm/__init__.py",
    "GEPPPlatform.services.admin.crm.__init__",
)
# Re-wire exceptions used inside __init__
_init_mod.APIException = _APIExc
_init_mod.NotFoundException = _NotFoundExc
_init_mod.BadRequestException = _BadReqExc
_init_mod.crm_service = _crm_service_mod

_start_campaign  = _init_mod._start_campaign
_pause_campaign  = _init_mod._pause_campaign
_resume_campaign = _init_mod._resume_campaign
_archive_campaign= _init_mod._archive_campaign
_test_campaign   = _init_mod._test_campaign


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


def _row(*v):
    return tuple(v)


def _campaign_row(
    camp_id=1, org_id=10, name="Test", camp_type="blast",
    trigger_event=None, trigger_config=None, segment_id=None,
    recipient_list_id=5, template_id=3, status="draft",
    started_at=None, from_name=None, from_email=None, reply_to=None,
):
    return _row(
        camp_id, org_id, name, camp_type,
        trigger_event, trigger_config or {}, segment_id,
        recipient_list_id, template_id, status,
        started_at, from_name, from_email, reply_to,
    )


def _make_db(
    camp_row=None, list_emails=None, segment_members=None,
    cooldown_blocked=False, list_match_test=True,
):
    """
    Build a mock db session.

    camp_row        : tuple returned for campaign SELECT
    list_emails     : list of {email, name} entries in crm_email_lists
    segment_members : list of (id, email) tuples for segment query
    cooldown_blocked: whether max(sent_at) returns recent timestamp
    list_match_test : whether crm_email_lists @> jsonb check returns a row
    """
    db = MagicMock()

    def _execute(sql_obj, params=None):
        sql_text = str(sql_obj).lower() if hasattr(sql_obj, 'text') else str(sql_obj).lower()
        res = MagicMock()

        if ("from crm_campaigns" in sql_text and
                ("where id" in sql_text or "where id=" in sql_text)):
            res.fetchone.return_value = camp_row
        elif "from crm_email_lists" in sql_text and "select emails" in sql_text:
            emails = list_emails if list_emails is not None else [
                {"email": "a@ex.com"}, {"email": "b@ex.com"}
            ]
            res.fetchone.return_value = _row(emails)
        elif "from crm_segment_members" in sql_text and ("join user_locations" in sql_text):
            rows = segment_members or [
                _row(101, "seg1@ex.com"), _row(102, "seg2@ex.com"),
            ]
            res.fetchall.return_value = rows
        elif "max(sent_at)" in sql_text:
            if cooldown_blocked:
                res.fetchone.return_value = _row(_NOW)
            else:
                res.fetchone.return_value = _row(None)
        elif "from crm_unsubscribes" in sql_text:
            res.fetchone.return_value = None  # not unsubscribed
        elif "from crm_email_templates" in sql_text:
            res.fetchone.return_value = _row(3, "Hello Subject", "<p>Hi {{firstname}}</p>", "Hi")
        elif "crm_email_lists" in sql_text and "@>" in sql_text:
            res.fetchone.return_value = _row(1) if list_match_test else None
        elif "update crm_campaigns" in sql_text:
            res.fetchone.return_value = None
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


def _patch_send(mock_result=None):
    if mock_result is None:
        mock_result = {"success": True, "mandrill_message_id": "mid_test", "raw_response": {}}
    return patch.object(_crm_service_mod, "send_via_email_lambda", return_value=mock_result)


# ---------------------------------------------------------------------------
# Tests: start
# ---------------------------------------------------------------------------

class TestStartCampaign(unittest.TestCase):

    def test_blast_with_email_list_50_recipients(self):
        """Blast campaign with 50-address email list → 50 delivery rows + status=completed."""
        emails = [{"email": f"user{i}@ex.com"} for i in range(50)]
        camp = _campaign_row(camp_type="blast", recipient_list_id=5, status="draft")
        db = _make_db(camp_row=camp, list_emails=emails)

        with _patch_send():
            result = _start_campaign(db, 1)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["recipientCount"], 50)
        self.assertIn("enqueuedAt", result)

    def test_trigger_start_returns_running_no_deliveries(self):
        """Trigger campaign start → status=running, recipientCount=0."""
        camp = _campaign_row(
            camp_type="trigger", trigger_event="user_login",
            recipient_list_id=None, status="draft",
        )
        db = _make_db(camp_row=camp)

        with _patch_send():
            result = _start_campaign(db, 1)

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["recipientCount"], 0)

    def test_start_already_running_raises_409(self):
        """Starting a running campaign → 409."""
        camp = _campaign_row(status="running")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_APIExc) as ctx:
            _start_campaign(db, 1)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_start_no_template_raises_400(self):
        """Campaign without template_id → 400."""
        camp = _campaign_row(template_id=None, status="draft")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_BadReqExc):
            _start_campaign(db, 1)

    def test_blast_no_list_no_segment_raises_400(self):
        """Blast with neither recipient_list_id nor segment_id → 400."""
        camp = _campaign_row(
            camp_type="blast", recipient_list_id=None, segment_id=None, status="draft"
        )
        db = _make_db(camp_row=camp)
        with self.assertRaises(_BadReqExc):
            _start_campaign(db, 1)

    def test_blast_with_segment(self):
        """Blast resolved from segment → deliveries for segment members."""
        camp = _campaign_row(
            camp_type="blast", recipient_list_id=None, segment_id=7, status="draft"
        )
        members = [_row(101, "seg1@ex.com"), _row(102, "seg2@ex.com")]
        db = _make_db(camp_row=camp, segment_members=members)

        with _patch_send():
            result = _start_campaign(db, 1)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["recipientCount"], 2)

    def test_paused_campaign_can_be_started(self):
        """A paused campaign can be re-started (starts = resume for blasts)."""
        camp = _campaign_row(status="paused")
        db = _make_db(camp_row=camp)
        with _patch_send():
            result = _start_campaign(db, 1)
        # paused blast → should complete with recipients
        self.assertIn(result["status"], ("completed", "running"))


# ---------------------------------------------------------------------------
# Tests: pause
# ---------------------------------------------------------------------------

class TestPauseCampaign(unittest.TestCase):

    def test_pause_running(self):
        camp = _campaign_row(status="running")
        db = _make_db(camp_row=camp)
        result = _pause_campaign(db, 1)
        self.assertEqual(result["status"], "paused")
        self.assertIn("pausedAt", result)

    def test_pause_draft_raises_409(self):
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_APIExc) as ctx:
            _pause_campaign(db, 1)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_pause_already_paused_raises_409(self):
        camp = _campaign_row(status="paused")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_APIExc) as ctx:
            _pause_campaign(db, 1)
        self.assertEqual(ctx.exception.status_code, 409)


# ---------------------------------------------------------------------------
# Tests: resume
# ---------------------------------------------------------------------------

class TestResumeCampaign(unittest.TestCase):

    def test_resume_paused(self):
        camp = _campaign_row(status="paused")
        db = _make_db(camp_row=camp)
        result = _resume_campaign(db, 1)
        self.assertEqual(result["status"], "running")

    def test_resume_running_raises_409(self):
        camp = _campaign_row(status="running")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_APIExc) as ctx:
            _resume_campaign(db, 1)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_resume_draft_raises_409(self):
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_APIExc) as ctx:
            _resume_campaign(db, 1)
        self.assertEqual(ctx.exception.status_code, 409)


# ---------------------------------------------------------------------------
# Tests: archive
# ---------------------------------------------------------------------------

class TestArchiveCampaign(unittest.TestCase):

    def test_archive_draft(self):
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp)
        result = _archive_campaign(db, 1)
        self.assertEqual(result["status"], "archived")
        self.assertIn("archivedAt", result)

    def test_archive_running(self):
        camp = _campaign_row(status="running")
        db = _make_db(camp_row=camp)
        result = _archive_campaign(db, 1)
        self.assertEqual(result["status"], "archived")

    def test_archive_already_archived_raises_409(self):
        camp = _campaign_row(status="archived")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_APIExc) as ctx:
            _archive_campaign(db, 1)
        self.assertEqual(ctx.exception.status_code, 409)


# ---------------------------------------------------------------------------
# Tests: test send
# ---------------------------------------------------------------------------

class TestTestCampaign(unittest.TestCase):

    def test_send_to_admin_own_email_succeeds(self):
        """Test send to admin's own email → 200, no delivery row inserted."""
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp)
        current_user = {"email": "admin@gepp.me", "id": 1}

        with _patch_send() as mock_send:
            result = _test_campaign(db, 1, {"recipientEmail": "admin@gepp.me"}, current_user)

        self.assertTrue(result["sent"])
        self.assertEqual(result["mandrillMessageId"], "mid_test")
        # No delivery row — db.add should NOT have been called
        db.add.assert_not_called()

    def test_send_to_org_list_email_succeeds(self):
        """Test send to email in org's email list → allowed."""
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp, list_match_test=True)
        current_user = {"email": "admin@gepp.me", "id": 1}

        with _patch_send():
            result = _test_campaign(
                db, 1, {"recipientEmail": "listed@org.com"}, current_user
            )

        self.assertTrue(result["sent"])

    def test_send_to_arbitrary_email_raises_400(self):
        """Test send to email not in org's lists → 400."""
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp, list_match_test=False)
        current_user = {"email": "admin@gepp.me", "id": 1}

        with self.assertRaises(_BadReqExc) as ctx:
            _test_campaign(db, 1, {"recipientEmail": "hacker@evil.com"}, current_user)

        self.assertIn("restricted", str(ctx.exception).lower())

    def test_missing_recipient_email_raises_400(self):
        camp = _campaign_row(status="draft")
        db = _make_db(camp_row=camp)
        with self.assertRaises(_BadReqExc):
            _test_campaign(db, 1, {}, {"email": "admin@gepp.me"})

    def test_test_send_does_not_insert_delivery_row(self):
        """Verify no CrmCampaignDelivery row is inserted during test send."""
        camp = _campaign_row(status="running")
        db = _make_db(camp_row=camp)
        current_user = {"email": "admin@gepp.me"}

        with _patch_send():
            _test_campaign(db, 1, {"recipientEmail": "admin@gepp.me"}, current_user)

        # db.add should never be called for a test send
        db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
