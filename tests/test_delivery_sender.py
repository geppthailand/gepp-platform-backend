"""
Unit tests for GEPPPlatform/services/admin/crm/delivery_sender.py

Run from v3/backend/:
    python -m pytest tests/test_delivery_sender.py -v

Or standalone:
    python -m unittest tests.test_delivery_sender

NOTE: Modules are loaded in isolation (importlib.util) to avoid the heavy
package __init__ chain that pulls in boto3/geoalchemy2/etc.  All cross-module
imports in delivery_sender.py are patched before the function runs.
"""

import sys
import os
import importlib.util as _ilu
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Isolated module loader — avoids the package __init__ chain
# ---------------------------------------------------------------------------

def _load_module(rel_path, name):
    """Load a Python file directly by path, registering it in sys.modules."""
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Stub out the full model/package chain before any GEPP imports
# ---------------------------------------------------------------------------

class _FakeDelivery:
    """Lightweight stand-in for CrmCampaignDelivery ORM model."""
    def __init__(self, **kw):
        self.id = None
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


# Stub the entire package hierarchy so module-level imports don't trigger
# geoalchemy2 / bcrypt / etc.  We snapshot the originals first so we can
# restore them at the bottom of this module, preventing pollution of any
# tests that run after this file is collected.
_ORIGINAL_MODULES_DELIVERY = {}

def _stub(name):
    if name in sys.modules and name not in _ORIGINAL_MODULES_DELIVERY:
        _ORIGINAL_MODULES_DELIVERY[name] = sys.modules[name]
    m = MagicMock()
    m.__spec__ = None  # mark as non-real so isinstance checks pass
    sys.modules[name] = m
    return m

for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.models.crm.events",
    "GEPPPlatform.models.crm.campaigns",
    "GEPPPlatform.exceptions",
]:
    _stub(_pkg)

# Wire concrete classes into the stubs
sys.modules["GEPPPlatform.models.crm"].CrmEvent = _FakeCrmEvent
sys.modules["GEPPPlatform.models.crm"].CrmCampaignDelivery = _FakeDelivery
sys.modules["GEPPPlatform.models.crm.events"].CrmEvent = _FakeCrmEvent
sys.modules["GEPPPlatform.models.crm.campaigns"].CrmCampaignDelivery = _FakeDelivery

# Load crm_service in isolation (it imports CrmEvent at module level)
_crm_service_mod = _load_module(
    "GEPPPlatform/services/admin/crm/crm_service.py",
    "GEPPPlatform.services.admin.crm.crm_service",
)

# Load unsubscribe_token in isolation
_token_mod = _load_module(
    "GEPPPlatform/services/admin/crm/unsubscribe_token.py",
    "GEPPPlatform.services.admin.crm.unsubscribe_token",
)

# Load email_renderer in isolation
_renderer_mod = _load_module(
    "GEPPPlatform/services/admin/crm/email_renderer.py",
    "GEPPPlatform.services.admin.crm.email_renderer",
)

# Load cooldown in isolation (delivery_sender now imports from it)
_cooldown_mod = _load_module(
    "GEPPPlatform/services/admin/crm/cooldown.py",
    "GEPPPlatform.services.admin.crm.cooldown",
)

# Load logger in isolation (delivery_sender now imports crm_log + new_correlation_id from it)
_logger_mod = _load_module(
    "GEPPPlatform/services/admin/crm/logger.py",
    "GEPPPlatform.services.admin.crm.logger",
)

# Register a stub crm package init so delivery_sender's `from . import crm_service` works
_crm_pkg = _stub("GEPPPlatform.services.admin.crm")
_crm_pkg.crm_service = _crm_service_mod
_crm_pkg.logger = _logger_mod

# Now load delivery_sender
_sender_mod = _load_module(
    "GEPPPlatform/services/admin/crm/delivery_sender.py",
    "GEPPPlatform.services.admin.crm.delivery_sender",
)
enqueue_delivery = _sender_mod.enqueue_delivery


# ---------------------------------------------------------------------------
# RESTORE the original modules so we don't pollute later test files.
# All bindings captured above (`enqueue_delivery`, `_FakeDelivery`, etc.) keep
# pointing to the isolated modules we loaded — those are still in memory because
# we have direct refs.  But sys.modules now points back to the real packages so
# that test_segment_evaluator and friends can do their normal imports.
# ---------------------------------------------------------------------------

for _name, _real_mod in _ORIGINAL_MODULES_DELIVERY.items():
    sys.modules[_name] = _real_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(
    *,
    is_unsubscribed=False,
    last_sent=None,
    delivery_id=101,
):
    """
    Return a mock db session wired for delivery_sender queries.
    execute() dispatches based on SQL snippet.
    """
    db = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.rollback = MagicMock()

    added_objects = []

    def _add(obj):
        added_objects.append(obj)
        obj.id = delivery_id  # simulate flush assigning id

    db.add = MagicMock(side_effect=_add)
    db._added = added_objects

    template_row = MagicMock()
    template_row.__getitem__ = lambda self, k: {
        0: 77, 1: "Hello!", 2: "<p>body</p>", 3: "body"
    }[k]

    user_row = MagicMock()
    user_row.__getitem__ = lambda self, k: {
        0: 5, 1: "user@example.com", 2: "Alice", 3: "Smith", 4: 42, 5: "Acme"
    }[k]

    def _execute(sql_obj, params=None):
        sql = str(sql_obj)
        result = MagicMock()

        if "crm_unsubscribes" in sql and "SELECT 1" in sql:
            result.fetchone.return_value = MagicMock() if is_unsubscribed else None

        elif "MAX(sent_at)" in sql:
            row = MagicMock()
            row.__getitem__ = lambda self, k: last_sent
            result.fetchone.return_value = row

        elif "crm_email_templates" in sql:
            result.fetchone.return_value = template_row

        elif "user_locations" in sql and "LEFT JOIN" in sql:
            result.fetchone.return_value = user_row

        else:
            result.fetchone.return_value = None

        return result

    db.execute = MagicMock(side_effect=_execute)
    return db


def _make_campaign(campaign_id=7, template_id=77, org_id=42, trigger_config=None):
    campaign = MagicMock()
    campaign.id = campaign_id
    campaign.template_id = template_id
    campaign.organization_id = org_id
    campaign.trigger_config = trigger_config or {}
    campaign.send_from_name = None
    campaign.send_from_email = None
    campaign.reply_to = None
    return campaign


# Stub send_via_email_lambda and emit_event on the loaded module
def _patch_send(return_value=None, side_effect=None):
    if side_effect:
        return patch.object(_sender_mod.crm_service, "send_via_email_lambda", side_effect=side_effect)
    return patch.object(_sender_mod.crm_service, "send_via_email_lambda", return_value=return_value)


def _patch_emit():
    return patch.object(_sender_mod.crm_service, "emit_event")


# ---------------------------------------------------------------------------
# Test: unsubscribed email skip path
# ---------------------------------------------------------------------------

class TestUnsubscribedSkip(unittest.TestCase):

    def test_unsubscribed_email_inserts_row_with_status_unsubscribed(self):
        db = _make_db(is_unsubscribed=True, delivery_id=200)
        campaign = _make_campaign()

        result = enqueue_delivery(db, campaign, user_location_id=5, recipient_email="opt@out.com")

        db.add.assert_called_once()
        inserted = db._added[0]
        self.assertEqual(inserted.status, "unsubscribed")
        self.assertEqual(inserted.recipient_email, "opt@out.com")
        db.commit.assert_called_once()
        self.assertEqual(result["status"], "unsubscribed")

    def test_unsubscribed_email_does_not_call_mandrill(self):
        db = _make_db(is_unsubscribed=True, delivery_id=201)
        campaign = _make_campaign()

        with _patch_send(return_value={}) as mock_send:
            enqueue_delivery(db, campaign, user_location_id=5, recipient_email="opt@out.com")

        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Test: happy path
# ---------------------------------------------------------------------------

class TestHappyPath(unittest.TestCase):

    def test_happy_path_flow(self):
        db = _make_db(is_unsubscribed=False, last_sent=None, delivery_id=102)
        campaign = _make_campaign()

        mandrill_response = {
            "success": True,
            "mandrill_message_id": "abc_mandrill_id",
            "raw_response": {},
        }

        with _patch_send(return_value=mandrill_response) as mock_send, _patch_emit() as mock_emit:
            result = enqueue_delivery(db, campaign, user_location_id=5, recipient_email="user@example.com")

        # Mandrill invoked
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs["to_email"], "user@example.com")
        self.assertIn("delivery_id", call_kwargs["metadata"])

        # Delivery row added + updated to sent
        db.add.assert_called_once()
        inserted = db._added[0]
        self.assertEqual(inserted.status, "sent")
        self.assertEqual(inserted.mandrill_message_id, "abc_mandrill_id")
        self.assertIsNotNone(inserted.sent_at)

        # email_sent event emitted
        mock_emit.assert_called_once()
        emit_kwargs = mock_emit.call_args.kwargs
        self.assertEqual(emit_kwargs["event_type"], "email_sent")
        self.assertEqual(emit_kwargs["event_category"], "email")

        # Result dict
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["mandrill_message_id"], "abc_mandrill_id")


# ---------------------------------------------------------------------------
# Test: Mandrill failure
# ---------------------------------------------------------------------------

class TestMandrillFailure(unittest.TestCase):

    def test_lambda_raises_leaves_status_failed(self):
        db = _make_db(is_unsubscribed=False, last_sent=None, delivery_id=103)
        campaign = _make_campaign()

        with _patch_send(side_effect=Exception("Lambda timeout")):
            result = enqueue_delivery(db, campaign, user_location_id=5, recipient_email="user@example.com")

        inserted = db._added[0]
        self.assertEqual(inserted.status, "failed")
        self.assertIn("Lambda timeout", inserted.error_message)
        self.assertGreater(inserted.retry_count, 0)

    def test_lambda_no_mandrill_id_leaves_status_failed(self):
        db = _make_db(is_unsubscribed=False, last_sent=None, delivery_id=104)
        campaign = _make_campaign()

        no_id_response = {
            "success": False,
            "mandrill_message_id": None,
            "raw_response": {},
            "error": "no _id",
        }

        with _patch_send(return_value=no_id_response):
            result = enqueue_delivery(db, campaign, user_location_id=5, recipient_email="user@example.com")

        inserted = db._added[0]
        self.assertEqual(inserted.status, "failed")


# ---------------------------------------------------------------------------
# Test: cooldown
# ---------------------------------------------------------------------------

class TestCooldown(unittest.TestCase):

    def test_cooldown_blocks_second_send(self):
        recent = datetime.now(timezone.utc) - timedelta(days=3)  # 3d ago < 7d cooldown
        db = _make_db(is_unsubscribed=False, last_sent=recent, delivery_id=105)
        campaign = _make_campaign(trigger_config={"cooldown_days": 7})

        result = enqueue_delivery(db, campaign, user_location_id=5, recipient_email="user@example.com")

        self.assertTrue(result.get("skipped"))
        self.assertEqual(result["reason"], "cooldown")
        db.add.assert_not_called()

    def test_outside_cooldown_proceeds(self):
        old = datetime.now(timezone.utc) - timedelta(days=10)  # 10d ago > 7d cooldown
        db = _make_db(is_unsubscribed=False, last_sent=old, delivery_id=106)
        campaign = _make_campaign(trigger_config={"cooldown_days": 7})

        mandrill_response = {"success": True, "mandrill_message_id": "ok_id", "raw_response": {}}

        with _patch_send(return_value=mandrill_response), _patch_emit():
            result = enqueue_delivery(db, campaign, user_location_id=5, recipient_email="user@example.com")

        self.assertNotIn("skipped", result)
        self.assertEqual(result["status"], "sent")


if __name__ == "__main__":
    unittest.main()
