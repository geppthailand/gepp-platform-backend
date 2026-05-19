"""
Sprint 9 — Unit tests for lead-scoped segments and lead-targeted campaigns.

Covers:
  - compile_rules for scope='lead' with nested AND/OR
  - SQL injection rejection for lead scope
  - get_field_registry includes 'leadFields'
  - delivery_sender with lead_id persisted
  - start_campaign lead path (mocked DB)

Run from v3/backend/:
    python -m pytest tests/crm_features/test_lead_segments_campaigns.py -v
"""

import sys
import os
import importlib.util as _ilu
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm.segment_evaluator import (
    compile_rules,
    get_field_registry,
    ALLOWED_FIELDS,
)
from GEPPPlatform.exceptions import BadRequestException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def condition(field, operator, value):
    return {"field": field, "operator": operator, "value": value}


def group(op, *conds):
    return {"op": op, "conditions": list(conds)}


# ---------------------------------------------------------------------------
# P1-a: compile_rules lead scope 3-level nesting
# ---------------------------------------------------------------------------

class TestCompileRulesLeadScope3Level(unittest.TestCase):
    """3-level nested AND/OR on lead fields compiles correctly."""

    def test_compile_rules_lead_scope_3level(self):
        """
        (lead_status IN ['new', 'contacted'])
        AND (
            (lead_score >= 50)
            OR (
                (days_since_created <= 30)
                AND (converted = False)
            )
        )
        """
        inner_and = group("AND",
            condition("days_since_created", "<=", 30),
            condition("converted", "=", False),
        )
        middle_or = group("OR",
            condition("lead_score", ">=", 50),
            inner_and,
        )
        root = group("AND",
            condition("lead_status", "IN", ["new", "contacted"]),
            middle_or,
        )
        where, params = compile_rules(root, "lead")

        # All field expressions appear
        self.assertIn("status", where)          # lead_status → status
        self.assertIn("lead_score", where)      # lead_score → lead_score
        self.assertIn("EXTRACT", where)         # days_since_created → expression
        self.assertIn("converted_user_id", where)  # converted → expression

        # Logical structure
        self.assertIn("AND", where)
        self.assertIn("OR", where)
        self.assertIn("IN", where)

        # Correct param count: IN(2) + 1 + 1 + 1 = 5
        self.assertEqual(len(params), 5)

        values = set(params.values())
        self.assertIn("new", values)
        self.assertIn("contacted", values)
        self.assertIn(50, values)
        self.assertIn(30, values)
        self.assertIn(False, values)

    def test_lead_score_between(self):
        """BETWEEN operator on lead_score produces two bind params."""
        node = condition("lead_score", "BETWEEN", [20, 80])
        where, params = compile_rules(node, "lead")
        self.assertIn("BETWEEN", where)
        self.assertIn("AND", where)
        vals = list(params.values())
        self.assertIn(20, vals)
        self.assertIn(80, vals)

    def test_owner_is_null(self):
        """IS NULL on lead_owner_user_id produces no value params."""
        node = condition("lead_owner_user_id", "IS NULL", None)
        where, params = compile_rules(node, "lead")
        self.assertIn("IS NULL", where)
        self.assertIn("owner_user_id", where)
        self.assertEqual(len(params), 0)

    def test_lead_company_ilike(self):
        """ILIKE on lead_company produces correct SQL fragment."""
        node = condition("lead_company", "ILIKE", "%acme%")
        where, params = compile_rules(node, "lead")
        self.assertIn("company", where)
        self.assertIn("ILIKE", where)
        self.assertEqual(list(params.values())[0], "%acme%")

    def test_days_since_last_activity_is_not_null(self):
        """IS NOT NULL on days_since_last_activity uses the EXTRACT expression."""
        node = condition("days_since_last_activity", "IS NOT NULL", None)
        where, params = compile_rules(node, "lead")
        self.assertIn("IS NOT NULL", where)
        self.assertIn("EXTRACT", where)
        self.assertIn("last_activity_at", where)
        self.assertEqual(len(params), 0)


# ---------------------------------------------------------------------------
# P1-b: SQL injection rejection for lead scope
# ---------------------------------------------------------------------------

class TestSQLInjectionRejectedLeadScope(unittest.TestCase):

    def test_hostile_field_name_raises(self):
        """'; DROP TABLE crm_leads; -- must be rejected as a field name."""
        node = condition("; DROP TABLE crm_leads; --", "=", 1)
        with self.assertRaises(BadRequestException) as ctx:
            compile_rules(node, "lead")
        self.assertIn("field", str(ctx.exception).lower())

    def test_union_injection_field_raises(self):
        node = condition("1 UNION SELECT email FROM crm_leads", "=", "x")
        with self.assertRaises(BadRequestException):
            compile_rules(node, "lead")

    def test_or_injection_as_operator_raises(self):
        node = condition("lead_score", "OR 1=1", 0)
        with self.assertRaises(BadRequestException) as ctx:
            compile_rules(node, "lead")
        self.assertIn("operator", str(ctx.exception).lower())

    def test_unknown_lead_field_raises(self):
        """A user-scope field must be rejected for lead scope."""
        node = condition("days_since_last_login", "=", 5)  # user field only
        with self.assertRaises(BadRequestException):
            compile_rules(node, "lead")

    def test_org_field_rejected_for_lead(self):
        """An org field must be rejected for lead scope."""
        node = condition("active_user_count_30d", ">", 0)  # org field
        with self.assertRaises(BadRequestException):
            compile_rules(node, "lead")


# ---------------------------------------------------------------------------
# P1-c: get_field_registry includes 'lead' key
# ---------------------------------------------------------------------------

class TestGetFieldRegistryIncludesLead(unittest.TestCase):

    def test_registry_has_lead_fields_key(self):
        registry = get_field_registry()
        self.assertIn("leadFields", registry, "Expected 'leadFields' key in registry")

    def test_lead_fields_is_non_empty_list(self):
        registry = get_field_registry()
        lead_fields = registry["leadFields"]
        self.assertIsInstance(lead_fields, list)
        self.assertGreater(len(lead_fields), 0)

    def test_each_lead_field_has_required_keys(self):
        registry = get_field_registry()
        for fdef in registry["leadFields"]:
            self.assertIn("name", fdef, f"Missing 'name' in {fdef}")
            self.assertIn("label", fdef, f"Missing 'label' in {fdef}")
            self.assertIn("type", fdef, f"Missing 'type' in {fdef}")
            self.assertIn("operators", fdef, f"Missing 'operators' in {fdef}")

    def test_expected_field_names_present(self):
        registry = get_field_registry()
        names = {f["name"] for f in registry["leadFields"]}
        for expected in ("lead_status", "lead_score", "lead_source",
                         "days_since_created", "converted"):
            self.assertIn(expected, names, f"Expected field '{expected}' missing from leadFields")


# ---------------------------------------------------------------------------
# Isolated loader (mirrors test_delivery_sender.py pattern)
# ---------------------------------------------------------------------------

class _FakeDelivery:
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
        self.user_location_id = None
        self.lead_id = None
        self.organization_id = None
        self.recipient_email = None
        self.campaign_id = None
        self.__dict__.update(kw)


_ORIG_MODS_LEAD: dict = {}


def _stub_lead(name):
    if name in sys.modules and name not in _ORIG_MODS_LEAD:
        _ORIG_MODS_LEAD[name] = sys.modules[name]
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
    "GEPPPlatform.exceptions",
]:
    _stub_lead(_pkg)

sys.modules["GEPPPlatform.models.crm"].CrmCampaignDelivery = _FakeDelivery
sys.modules["GEPPPlatform.models.crm.campaigns"].CrmCampaignDelivery = _FakeDelivery


def _load_mod(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_crm_service_mod_lead = _load_mod(
    "GEPPPlatform/services/admin/crm/crm_service.py",
    "GEPPPlatform.services.admin.crm.crm_service_lead",
)
_token_mod_lead = _load_mod(
    "GEPPPlatform/services/admin/crm/unsubscribe_token.py",
    "GEPPPlatform.services.admin.crm.unsubscribe_token_lead",
)
_renderer_mod_lead = _load_mod(
    "GEPPPlatform/services/admin/crm/email_renderer.py",
    "GEPPPlatform.services.admin.crm.email_renderer_lead",
)
_cooldown_mod_lead = _load_mod(
    "GEPPPlatform/services/admin/crm/cooldown.py",
    "GEPPPlatform.services.admin.crm.cooldown_lead",
)
_logger_mod_lead = _load_mod(
    "GEPPPlatform/services/admin/crm/logger.py",
    "GEPPPlatform.services.admin.crm.logger_lead",
)
_crm_pkg_lead = _stub_lead("GEPPPlatform.services.admin.crm_lead")
_crm_pkg_lead.crm_service = _crm_service_mod_lead
_crm_pkg_lead.logger = _logger_mod_lead

# Override the package stub so delivery_sender's `from . import crm_service` works
_existing_crm_pkg = sys.modules.get("GEPPPlatform.services.admin.crm", MagicMock())
_existing_crm_pkg.crm_service = _crm_service_mod_lead

_sender_mod_lead = _load_mod(
    "GEPPPlatform/services/admin/crm/delivery_sender.py",
    "GEPPPlatform.services.admin.crm.delivery_sender_lead",
)
_enqueue_delivery_lead = _sender_mod_lead.enqueue_delivery

# Restore real modules
for _name, _real in _ORIG_MODS_LEAD.items():
    sys.modules[_name] = _real


# ---------------------------------------------------------------------------
# P1-d: delivery_sender with lead_id
# ---------------------------------------------------------------------------

def _make_lead_db(*, delivery_id=201):
    db = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    added = []

    def _add(obj):
        added.append(obj)
        obj.id = delivery_id

    db.add = MagicMock(side_effect=_add)
    db._added = added

    template_row = MagicMock()
    template_row.__getitem__ = lambda self, k: {
        0: 99, 1: "Lead Subject!", 2: "<p>lead body</p>", 3: "lead body"
    }[k]

    lead_row = MagicMock()
    lead_row.__getitem__ = lambda self, k: {
        0: 42, 1: "lead@example.com", 2: "Jane", 3: "Doe"
    }[k]

    def _execute(sql_obj, params=None):
        sql = str(sql_obj)
        result = MagicMock()
        if "crm_unsubscribes" in sql and "SELECT 1" in sql:
            result.fetchone.return_value = None  # not unsubscribed
        elif "MAX(sent_at)" in sql:
            row = MagicMock()
            row.__getitem__ = lambda self, k: None
            result.fetchone.return_value = row
        elif "crm_email_templates" in sql:
            result.fetchone.return_value = template_row
        elif "crm_leads" in sql:
            result.fetchone.return_value = lead_row
        else:
            result.fetchone.return_value = None
        return result

    db.execute = MagicMock(side_effect=_execute)
    return db


def _make_lead_campaign(campaign_id=10, template_id=99, org_id=5):
    c = MagicMock()
    c.id = campaign_id
    c.template_id = template_id
    c.organization_id = org_id
    c.trigger_config = {}
    c.send_from_name = None
    c.send_from_email = None
    c.reply_to = None
    return c


class TestDeliverySenderWithLeadId(unittest.TestCase):

    def test_lead_id_persisted_in_delivery_row(self):
        """When lead_id is passed, the delivery row must have lead_id set."""
        db = _make_lead_db(delivery_id=201)
        campaign = _make_lead_campaign()

        mandrill_ok = {"success": True, "mandrill_message_id": "lead_mid_1", "raw_response": {}}

        with patch.object(_sender_mod_lead.crm_service, "send_via_email_lambda",
                          return_value=mandrill_ok):
            with patch.object(_sender_mod_lead.crm_service, "emit_event"):
                result = _enqueue_delivery_lead(
                    db, campaign,
                    lead_id=42,
                    recipient_email="lead@example.com",
                )

        db.add.assert_called_once()
        inserted = db._added[0]
        self.assertEqual(inserted.lead_id, 42)
        self.assertIsNone(inserted.user_location_id)
        self.assertEqual(inserted.status, "sent")
        self.assertEqual(result["lead_id"], 42)

    def test_lead_unsubscribe_check_runs_by_email(self):
        """Unsub check must run even for lead sends (keyed on email)."""
        db = MagicMock()
        db.commit = MagicMock()
        db.flush = MagicMock()
        added = []

        def _add(obj):
            added.append(obj)
            obj.id = 999
        db.add = MagicMock(side_effect=_add)
        db._added = added

        # Mark as unsubscribed
        def _execute(sql_obj, params=None):
            sql = str(sql_obj)
            result = MagicMock()
            if "crm_unsubscribes" in sql:
                result.fetchone.return_value = MagicMock()  # unsubscribed
            else:
                result.fetchone.return_value = None
            return result

        db.execute = MagicMock(side_effect=_execute)
        campaign = _make_lead_campaign()

        result = _enqueue_delivery_lead(
            db, campaign,
            lead_id=42,
            recipient_email="unsub@example.com",
        )
        self.assertEqual(result["status"], "unsubscribed")

    def test_lead_cooldown_skipped(self):
        """Cooldown check is bypassed for lead-targeted sends."""
        from datetime import datetime, timezone, timedelta

        # last_sent very recently — would block a user send
        recent = datetime.now(timezone.utc) - timedelta(days=1)

        db = _make_lead_db(delivery_id=202)
        # Make cooldown appear blocked if it were called
        orig_execute = db.execute.side_effect

        def _execute_with_cooldown(sql_obj, params=None):
            sql = str(sql_obj)
            if "MAX(sent_at)" in sql:
                row = MagicMock()
                row.__getitem__ = lambda self, k: recent
                result = MagicMock()
                result.fetchone.return_value = row
                return result
            return orig_execute(sql_obj, params)

        db.execute.side_effect = _execute_with_cooldown
        campaign = _make_lead_campaign(
            campaign_id=10
        )
        campaign.trigger_config = {"cooldown_days": 7}

        mandrill_ok = {"success": True, "mandrill_message_id": "lead_mid_2", "raw_response": {}}

        with patch.object(_sender_mod_lead.crm_service, "send_via_email_lambda",
                          return_value=mandrill_ok):
            with patch.object(_sender_mod_lead.crm_service, "emit_event"):
                result = _enqueue_delivery_lead(
                    db, campaign,
                    lead_id=42,
                    recipient_email="lead@example.com",
                )

        # Must NOT be skipped despite recent send
        self.assertNotEqual(result.get("reason"), "cooldown")
        self.assertEqual(result["status"], "sent")


# ---------------------------------------------------------------------------
# P1-e: start_campaign target_type=lead (mocked)
# ---------------------------------------------------------------------------

class TestStartCampaignTargetLead(unittest.TestCase):
    """_start_campaign routes to lead path when target_type='lead'."""

    def _make_db_for_start_campaign(self, lead_emails):
        """Return a mock db that simulates the queries in _start_campaign."""
        db = MagicMock()
        db.commit = MagicMock()
        db.flush = MagicMock()

        _camp_data = [
            1, 5, "Lead Campaign", "blast", None, {}, 99, None, 77,
            "draft", None, None, None, None, "lead"
        ]

        def _execute(sql_obj, params=None):
            sql = str(sql_obj)
            result = MagicMock()

            if "crm_campaigns" in sql:
                result.fetchone.return_value = _camp_data

            elif "crm_segments" in sql and "scope" in sql:
                result.fetchone.return_value = ["lead"]  # scope = 'lead'

            elif "crm_segment_members" in sql and "crm_leads" in sql:
                rows = [
                    [i + 10, email]
                    for i, email in enumerate(lead_emails)
                ]
                result.fetchall.return_value = rows

            elif "UPDATE crm_campaigns" in sql:
                result.rowcount = 1

            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []

            return result

        db.execute = MagicMock(side_effect=_execute)
        return db

    def test_start_campaign_enqueues_lead_deliveries(self):
        """_start_campaign with target_type='lead' calls enqueue_delivery with lead_id."""
        from GEPPPlatform.services.admin.crm import _start_campaign

        db = self._make_db_for_start_campaign(["a@ex.com", "b@ex.com"])

        enqueued_calls = []

        def _mock_enqueue(db_, campaign_obj, user_location_id=None,
                          recipient_email="", lead_id=None, **kw):
            enqueued_calls.append({
                "user_location_id": user_location_id,
                "lead_id": lead_id,
                "recipient_email": recipient_email,
            })
            return {"status": "sent"}

        with patch(
            "GEPPPlatform.services.admin.crm.delivery_sender.enqueue_delivery",
            side_effect=_mock_enqueue,
        ):
            result = _start_campaign(db, 1)

        # Two leads enqueued
        self.assertEqual(len(enqueued_calls), 2)
        for call in enqueued_calls:
            self.assertIsNone(call["user_location_id"])
            self.assertIsNotNone(call["lead_id"])

        self.assertEqual(result["recipientCount"], 2)

    def test_start_campaign_rejects_mismatched_segment(self):
        """Raises BadRequestException if segment scope != 'lead' for lead campaign."""
        from GEPPPlatform.services.admin.crm import _start_campaign
        from GEPPPlatform.exceptions import BadRequestException as _BE

        db = MagicMock()
        db.commit = MagicMock()

        _camp_row_data = [
            1, 5, "Camp", "blast", None, {}, 99, None, 77,
            "draft", None, None, None, None, "lead"
        ]

        def _execute(sql_obj, params=None):
            sql = str(sql_obj)
            result = MagicMock()
            if "crm_campaigns" in sql:
                row = _camp_row_data  # real list — supports unpacking
                result.fetchone.return_value = row
            elif "crm_segments" in sql and "scope" in sql:
                seg_row = ["user"]  # MISMATCH — list, index 0 = scope
                result.fetchone.return_value = seg_row
            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []
            return result

        db.execute = MagicMock(side_effect=_execute)

        with self.assertRaises(_BE):
            _start_campaign(db, 1)


if __name__ == "__main__":
    unittest.main()
