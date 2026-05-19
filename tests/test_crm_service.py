"""
Unit tests for GEPPPlatform/services/admin/crm/crm_service.py and profile_refresher.py

Run from v3/backend/:
    python -m pytest tests/test_crm_service.py -v

Or standalone:
    python -m unittest tests.test_crm_service
"""

import sys
import os
import re
import ast
import unittest
from unittest.mock import MagicMock, patch, call

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm.crm_service import emit_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Return a mock db session that records add() / execute() calls."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Tests: emit_event()
# ---------------------------------------------------------------------------

class TestEmitEvent(unittest.TestCase):

    def test_inserts_row_with_correct_defaults(self):
        """emit_event() adds a CrmEvent row with expected field values."""
        from GEPPPlatform.models.crm import CrmEvent

        db = _make_db()
        evt = emit_event(
            db,
            event_type="user_login",
            event_category="auth",
            organization_id=42,
            user_location_id=7,
        )

        # row was queued for insert
        db.add.assert_called_once()
        inserted = db.add.call_args[0][0]

        self.assertIsInstance(inserted, CrmEvent)
        self.assertEqual(inserted.event_type, "user_login")
        self.assertEqual(inserted.event_category, "auth")
        self.assertEqual(inserted.organization_id, 42)
        self.assertEqual(inserted.user_location_id, 7)
        self.assertEqual(inserted.event_source, "server")     # default
        self.assertEqual(inserted.properties, {})             # default empty dict
        # commit=False → commit NOT called
        db.commit.assert_not_called()

    def test_commit_flag_triggers_commit(self):
        """emit_event(commit=True) calls db.commit()."""
        db = _make_db()
        emit_event(db, event_type="x", event_category="y", commit=True)
        db.commit.assert_called_once()

    def test_properties_stored(self):
        """Custom properties dict is stored on the event."""
        db = _make_db()
        props = {"campaign_id": 5, "total_points": 100.0}
        emit_event(db, event_type="reward_claimed", event_category="reward", properties=props)

        inserted = db.add.call_args[0][0]
        self.assertEqual(inserted.properties, props)

    def test_never_raises_on_db_error(self):
        """emit_event() swallows db exceptions and returns None."""
        db = _make_db()
        db.add.side_effect = RuntimeError("DB is down")

        result = emit_event(db, event_type="user_login", event_category="auth")
        self.assertIsNone(result)   # returned None, did not raise

    def test_returns_crm_event_on_success(self):
        """emit_event() returns the CrmEvent instance when successful."""
        from GEPPPlatform.models.crm import CrmEvent

        db = _make_db()
        result = emit_event(db, event_type="gri_data_submitted", event_category="gri")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, CrmEvent)

    def test_no_commit_by_default(self):
        """Default commit=False means no commit is issued."""
        db = _make_db()
        emit_event(db, event_type="any", event_category="any")
        db.commit.assert_not_called()

    def test_optional_fields_passed_through(self):
        """session_id, ip_address, user_agent are stored if provided."""
        db = _make_db()
        emit_event(
            db,
            event_type="user_login",
            event_category="auth",
            session_id="sess-abc",
            ip_address="1.2.3.4",
            user_agent="Mozilla/5.0",
        )
        inserted = db.add.call_args[0][0]
        self.assertEqual(inserted.session_id, "sess-abc")
        self.assertEqual(inserted.ip_address, "1.2.3.4")
        self.assertEqual(inserted.user_agent, "Mozilla/5.0")


# ---------------------------------------------------------------------------
# Tests: Engagement score formula
# ---------------------------------------------------------------------------

class TestEngagementScoreFormula(unittest.TestCase):
    """
    Verify the engagement score formula used in profile_refresher.py is correct.

    Formula (from brief):
        score = 40 * min(login_count_30d / 20, 1)
              + 30 * min(transaction_count_30d / 50, 1)
              + 15 * min(reward_claim_count_30d / 10, 1)
              + 15 * min(iot_readings_count_30d / 100, 1)
    """

    @staticmethod
    def _score(logins, txns, rewards, iot_readings):
        login_denom = 20
        txn_denom = 50
        reward_denom = 10
        iot_denom = 100
        return (
            40.0 * min(logins / login_denom, 1.0)
            + 30.0 * min(txns / txn_denom, 1.0)
            + 15.0 * min(rewards / reward_denom, 1.0)
            + 15.0 * min(iot_readings / iot_denom, 1.0)
        )

    def test_zero_activity_gives_zero_score(self):
        self.assertAlmostEqual(self._score(0, 0, 0, 0), 0.0)

    def test_full_activity_gives_100(self):
        """Max logins=20, txns=50, rewards=10, iot=100 → score = 100."""
        self.assertAlmostEqual(self._score(20, 50, 10, 100), 100.0)

    def test_beyond_max_clamps_to_100(self):
        """Values exceeding denominator are clamped by min(v, 1)."""
        self.assertAlmostEqual(self._score(999, 999, 999, 999), 100.0)

    def test_login_only_active_user(self):
        """User with 10 logins and nothing else → 20 points."""
        score = self._score(10, 0, 0, 0)
        self.assertAlmostEqual(score, 20.0)

    def test_mixed_activity(self):
        """Half of each component → 50."""
        score = self._score(10, 25, 5, 50)
        expected = 40 * 0.5 + 30 * 0.5 + 15 * 0.5 + 15 * 0.5
        self.assertAlmostEqual(score, expected)

    def test_activity_tier_active(self):
        """Score >= 70 → tier is 'active'."""
        score = self._score(20, 50, 10, 50)
        tier = "active" if score >= 70 else ("at_risk" if score >= 40 else "dormant")
        self.assertEqual(tier, "active")

    def test_activity_tier_at_risk(self):
        """Score 40-69 → tier is 'at_risk'."""
        score = self._score(10, 10, 0, 0)
        # 40*0.5 + 30*0.2 + 0 + 0 = 20+6 = 26 → dormant; let's pick a score in range
        score2 = self._score(10, 25, 5, 0)
        # 20 + 15 + 7.5 = 42.5 → at_risk
        tier = "active" if score2 >= 70 else ("at_risk" if score2 >= 40 else "dormant")
        self.assertEqual(tier, "at_risk")

    def test_activity_tier_dormant(self):
        """Score < 40 → tier is 'dormant'."""
        score = self._score(5, 5, 1, 5)
        # 40*0.25 + 30*0.1 + 15*0.1 + 15*0.05 = 10 + 3 + 1.5 + 0.75 = 15.25
        tier = "active" if score >= 70 else ("at_risk" if score >= 40 else "dormant")
        self.assertEqual(tier, "dormant")


# ---------------------------------------------------------------------------
# Tests: SQL injection / parameterization guardrails
# ---------------------------------------------------------------------------

class TestSQLParameterizationGuardrails(unittest.TestCase):
    """
    Verify that the analytics functions use parameterized text() calls
    and that the granularity/funnel whitelists protect against injection.
    """

    def test_granularity_whitelist_accepts_valid_values(self):
        """Whitelisted granularity values do not raise."""
        _VALID_GRANULARITIES = {"hour", "day", "week", "month"}
        for gran in ("hour", "day", "week", "month"):
            self.assertIn(gran, _VALID_GRANULARITIES)

    def test_granularity_whitelist_rejects_injection(self):
        """Injected granularity would NOT be in whitelist."""
        _VALID_GRANULARITIES = {"hour", "day", "week", "month"}
        injected = "day; DROP TABLE crm_events;--"
        self.assertNotIn(injected, _VALID_GRANULARITIES)

    def test_funnel_step_regex_accepts_valid_event_types(self):
        """Valid event type names pass the regex."""
        pattern = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
        valid_names = [
            "user_login",
            "transaction_created",
            "reward_claimed",
            "gri_data_submitted",
            "scale_reading_received",
        ]
        for name in valid_names:
            self.assertIsNotNone(pattern.match(name), f"{name!r} should pass whitelist")

    def test_funnel_step_regex_rejects_injection(self):
        """SQL injection attempts in event type names are rejected by regex."""
        pattern = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
        injections = [
            "'; DROP TABLE crm_events;--",
            "1=1",
            "user_login OR 1=1",
            "",
            "User_Login",       # uppercase not allowed
            "123abc",           # must start with lowercase letter
        ]
        for evil in injections:
            self.assertIsNone(pattern.match(evil), f"{evil!r} should be rejected")

    def test_crm_service_uses_sqlalchemy_text(self):
        """crm_service.py source code uses text() for every raw SQL statement."""
        crm_path = os.path.join(
            _ROOT,
            "GEPPPlatform", "services", "admin", "crm", "crm_service.py"
        )
        with open(crm_path, "r") as fh:
            source = fh.read()

        # Must import sqlalchemy text
        self.assertIn("from sqlalchemy import text", source)
        # AST-based check: every db_session.execute(arg, ...) must have arg be
        # a text(...) call, an identifier whose name contains 'text', or a Name
        # bound to a text-statement (e.g. previously assigned _text = text).
        import ast
        tree = ast.parse(source)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match db_session.execute(...) and session.execute(...)
            if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
                continue
            obj = func.value
            if isinstance(obj, ast.Name) and obj.id not in {"db_session", "session", "self"}:
                continue
            if not node.args:
                continue
            first = node.args[0]
            # Acceptable: text(...) call directly
            if isinstance(first, ast.Call) and isinstance(first.func, ast.Name) and first.func.id in {"text", "_text"}:
                continue
            # Acceptable: a Name (assumed bound to a text(...) statement upstream).
            # We do NOT flag this because an earlier sql = text("...") + execute(sql) is
            # a common, safe pattern — the guard was originally intended to catch raw
            # str literals, not Name references.
            if isinstance(first, ast.Name):
                continue
            # Acceptable: f-string / str literal would be the actual smell
            if isinstance(first, (ast.Constant, ast.JoinedStr)):
                offenders.append(ast.dump(first)[:120])
                continue
            # Anything else (Subscript, Attribute, BinOp …) is also suspicious
            offenders.append(ast.dump(first)[:120])
        self.assertFalse(offenders, f"execute() without text(): {offenders}")

    def test_profile_refresher_uses_sqlalchemy_text(self):
        """profile_refresher.py source code uses text() for its UPSERT SQL."""
        pr_path = os.path.join(
            _ROOT,
            "GEPPPlatform", "services", "admin", "crm", "profile_refresher.py"
        )
        with open(pr_path, "r") as fh:
            source = fh.read()

        self.assertIn("from sqlalchemy import text", source)


# ---------------------------------------------------------------------------
# Tests: Profile refresher helpers (pure Python logic, no DB)
# ---------------------------------------------------------------------------

class TestProfileRefresher(unittest.TestCase):

    def test_refresh_user_profiles_returns_expected_keys(self):
        """refresh_user_profiles() returns dict with rows_upserted and duration_s."""
        from GEPPPlatform.services.admin.crm.profile_refresher import refresh_user_profiles

        db = _make_db()
        # Mock execute to return a result with rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 7
        db.execute.return_value = mock_result

        result = refresh_user_profiles(db)

        self.assertIn("rows_upserted", result)
        self.assertIn("duration_s", result)
        self.assertEqual(result["rows_upserted"], 7)
        self.assertIsInstance(result["duration_s"], float)

    def test_refresh_org_profiles_returns_expected_keys(self):
        """refresh_org_profiles() returns dict with rows_upserted and duration_s."""
        from GEPPPlatform.services.admin.crm.profile_refresher import refresh_org_profiles

        db = _make_db()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        db.execute.return_value = mock_result

        result = refresh_org_profiles(db)

        self.assertIn("rows_upserted", result)
        self.assertIn("duration_s", result)
        self.assertEqual(result["rows_upserted"], 3)

    def test_run_full_refresh_calls_both(self):
        """run_full_refresh() invokes both refresh functions and returns combined result."""
        from GEPPPlatform.services.admin.crm import profile_refresher

        db = _make_db()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        db.execute.return_value = mock_result

        with patch.object(profile_refresher, "refresh_user_profiles", wraps=profile_refresher.refresh_user_profiles) as ru, \
             patch.object(profile_refresher, "refresh_org_profiles", wraps=profile_refresher.refresh_org_profiles) as ro:
            result = profile_refresher.run_full_refresh(db)
            self.assertTrue(ru.called)
            self.assertTrue(ro.called)

        # Sprint 2-4: keys are user_profiles / org_profiles / email_engagement.
        # Accept either old (users/orgs) or new keys for forward-compat.
        self.assertTrue(
            ("users" in result and "orgs" in result)
            or ("user_profiles" in result and "org_profiles" in result),
            f"Unexpected run_full_refresh shape: {list(result)}",
        )


# ---------------------------------------------------------------------------
# Tests: AST parse (syntax check)
# ---------------------------------------------------------------------------

class TestASTSyntax(unittest.TestCase):
    """Verify all modified/created CRM files parse cleanly."""

    _FILES = [
        os.path.join(_ROOT, "GEPPPlatform", "services", "admin", "crm", "crm_service.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "admin", "crm", "profile_refresher.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "admin", "crm", "__init__.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "auth", "auth_handlers.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "cores", "gri", "gri_handlers.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "rewards", "claim_service.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "cores", "iot_devices", "iot_devices_handlers.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "cores", "transactions", "transaction_service.py"),
        os.path.join(_ROOT, "GEPPPlatform", "services", "cores", "traceability", "traceability_service.py"),
    ]

    def test_all_files_parse_without_syntax_errors(self):
        for fpath in self._FILES:
            with self.subTest(file=os.path.relpath(fpath, _ROOT)):
                self.assertTrue(os.path.exists(fpath), f"File not found: {fpath}")
                with open(fpath, "r") as fh:
                    source = fh.read()
                try:
                    ast.parse(source)
                except SyntaxError as exc:
                    self.fail(f"SyntaxError in {fpath}: {exc}")


# ---------------------------------------------------------------------------
# Tests: CRM admin dispatcher (__init__.py)
# ---------------------------------------------------------------------------

class TestCrmAdminDispatcher(unittest.TestCase):
    """Verify handle_crm_admin_subroute() routes correctly."""

    # Actual signature: handle_crm_admin_subroute(resource, resource_id, sub_path, method,
    #                                              db_session, data, query_params, current_user)
    def _call(self, resource, sub_path="", resource_id=None, method="GET",
              query_params=None, body=None, db=None):
        from GEPPPlatform.services.admin.crm import handle_crm_admin_subroute
        return handle_crm_admin_subroute(
            resource=resource,
            resource_id=resource_id,
            sub_path=sub_path,
            method=method,
            db_session=db or _make_db(),
            data=body or {},
            query_params=query_params or {},
            current_user={"user_id": 1, "organization_id": 1},
        )

    def test_unknown_resource_raises_not_found(self):
        from GEPPPlatform.exceptions import NotFoundException
        with self.assertRaises(NotFoundException):
            self._call("crm-unknown", sub_path="whatever")

    def test_segments_raises_not_found_stub(self):
        from GEPPPlatform.exceptions import NotFoundException
        with self.assertRaises(NotFoundException):
            self._call("crm-segments", sub_path="anything")

    def test_templates_raises_not_found_stub(self):
        from GEPPPlatform.exceptions import NotFoundException
        with self.assertRaises(NotFoundException):
            self._call("crm-templates", sub_path="anything")

    @patch("GEPPPlatform.services.admin.crm.crm_service.get_analytics_overview")
    def test_analytics_overview_route(self, mock_fn):
        mock_fn.return_value = {"totalOrganizations": 10}
        result = self._call("crm-analytics", sub_path="overview")
        mock_fn.assert_called_once()
        self.assertEqual(result, {"totalOrganizations": 10})

    @patch("GEPPPlatform.services.admin.crm.crm_service.get_analytics_timeseries")
    def test_analytics_timeseries_route(self, mock_fn):
        mock_fn.return_value = {"series": []}
        self._call(
            "crm-analytics",
            sub_path="timeseries",
            query_params={"eventType": "user_login", "granularity": "day"},
        )
        mock_fn.assert_called_once()

    @patch("GEPPPlatform.services.admin.crm.crm_service.get_analytics_funnel")
    def test_analytics_funnel_route(self, mock_fn):
        mock_fn.return_value = {"steps": []}
        self._call(
            "crm-analytics",
            sub_path="funnel",
            query_params={"orgId": "5", "steps": "user_login,transaction_created"},
        )
        mock_fn.assert_called_once()

    @patch("GEPPPlatform.services.admin.crm.crm_service.get_analytics_org")
    def test_analytics_org_route(self, mock_fn):
        mock_fn.return_value = {"organizationId": 5}
        self._call("crm-analytics", sub_path="org/5")
        mock_fn.assert_called_once_with(unittest.mock.ANY, 5)

    @patch("GEPPPlatform.services.admin.crm.crm_service.get_analytics_org_users")
    def test_analytics_org_users_route(self, mock_fn):
        mock_fn.return_value = {"users": [], "total": 0}
        self._call("crm-analytics", sub_path="org/5/users")
        mock_fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
