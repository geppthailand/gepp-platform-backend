"""
Unit tests for the cookie-consent READ side (services/admin/crm/cookie_consent_handlers).

Focus is on the SQL-building contract rather than result rows: the risky part of this
module is that filters must stay bound parameters and that a malformed consentId must
filter to zero rows instead of blowing up a Postgres uuid cast.
"""

import importlib.util as _ilu
import os
import sys
import unittest
from unittest.mock import MagicMock

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm import cookie_consent_handlers as h  # noqa: E402
from GEPPPlatform.exceptions import NotFoundException  # noqa: E402


def _sql_of(call) -> str:
    """The text() clause passed to db.execute, as a string."""
    return str(call.args[0])


def _params_of(call) -> dict:
    return call.args[1] if len(call.args) > 1 else {}


class TestFilterBuilding(unittest.TestCase):
    def test_all_filter_values_are_bound_not_interpolated(self):
        where, params = h._build_filters({
            "action": "reject_all",
            "consentId": "abc",
            "country": "TH",
            "q": "'; DROP TABLE cookie_consent_log; --",
            "dateFrom": "2026-01-01",
            "dateTo": "2026-02-01",
        })
        # The injection payload must live in params, never in the SQL string.
        self.assertNotIn("DROP TABLE", where)
        self.assertIn("DROP TABLE", params["q"])
        self.assertEqual(params["action"], "reject_all")
        self.assertEqual(params["country"], "TH")

    def test_unknown_action_is_ignored_rather_than_filtering_to_nothing(self):
        where, params = h._build_filters({"action": "bogus"})
        self.assertNotIn("action", params)
        self.assertEqual(where, "1=1")

    def test_consent_id_casts_the_column_not_the_input(self):
        # Casting the input would raise on a malformed uuid; casting the column
        # simply matches no rows.
        where, params = h._build_filters({"consentId": "not-a-uuid"})
        self.assertIn("consent_id::text = :consent_id", where)
        self.assertEqual(params["consent_id"], "not-a-uuid")

    def test_blank_filters_are_dropped(self):
        where, params = h._build_filters({"action": "", "q": "  ", "country": None})
        self.assertEqual(where, "1=1")
        self.assertEqual(params, {})


class TestListPagination(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.execute.return_value.scalar.return_value = 7
        self.db.execute.return_value.fetchall.return_value = []

    def test_page_size_is_capped(self):
        r = h.list_crm_cookie_consents(self.db, {"page": 1, "pageSize": 99999})
        self.assertEqual(r["pageSize"], 200)
        self.assertEqual(_params_of(self.db.execute.call_args)["limit"], 200)

    def test_garbage_pagination_falls_back_to_defaults(self):
        r = h.list_crm_cookie_consents(self.db, {"page": "abc", "pageSize": "xyz"})
        self.assertEqual(r["page"], 1)
        self.assertEqual(r["pageSize"], 25)

    def test_offset_follows_page(self):
        h.list_crm_cookie_consents(self.db, {"page": 3, "pageSize": 10})
        self.assertEqual(_params_of(self.db.execute.call_args)["offset"], 20)

    def test_newest_first(self):
        h.list_crm_cookie_consents(self.db, {})
        self.assertIn("ORDER BY created_date DESC", _sql_of(self.db.execute.call_args))

    def test_total_comes_from_the_count_query(self):
        r = h.list_crm_cookie_consents(self.db, {})
        self.assertEqual(r["total"], 7)


class TestSummary(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        totals = MagicMock()
        totals._mapping = {
            "events": 10, "visitors": 4,
            "accept_all": 6, "reject_all": 3, "custom": 1,
            "analytics_granted": 7, "preferences_granted": 5, "marketing_granted": 2,
        }
        self.db.execute.return_value.fetchone.return_value = totals
        self.db.execute.return_value.fetchall.return_value = []

    def test_percentages_are_relative_to_events(self):
        s = h.get_cookie_consent_summary(self.db, {})
        self.assertEqual(s["grantedPct"]["analytics"], 70.0)
        self.assertEqual(s["grantedPct"]["marketing"], 20.0)

    def test_visitors_is_distinct_not_row_count(self):
        s = h.get_cookie_consent_summary(self.db, {})
        self.assertEqual(s["events"], 10)
        self.assertEqual(s["visitors"], 4)

    def test_zero_events_does_not_divide_by_zero(self):
        empty = MagicMock()
        empty._mapping = {"events": 0, "visitors": 0}
        self.db.execute.return_value.fetchone.return_value = empty
        s = h.get_cookie_consent_summary(self.db, {})
        self.assertEqual(s["grantedPct"]["analytics"], 0.0)

    def test_days_window_is_clamped(self):
        s = h.get_cookie_consent_summary(self.db, {"days": 99999})
        self.assertEqual(s["days"], h._MAX_SUMMARY_DAYS)


class TestSubroute(unittest.TestCase):
    def test_summary_is_routed(self):
        db = MagicMock()
        totals = MagicMock()
        totals._mapping = {"events": 0, "visitors": 0}
        db.execute.return_value.fetchone.return_value = totals
        db.execute.return_value.fetchall.return_value = []
        out = h.dispatch_cookie_consent_subroute(None, "summary", "GET", db, {})
        self.assertIn("byAction", out)

    def test_unknown_subroute_raises_not_found(self):
        with self.assertRaises(NotFoundException):
            h.dispatch_cookie_consent_subroute(None, "bogus", "GET", MagicMock(), {})

    def test_write_methods_are_not_routed(self):
        # The log is append-only from the public endpoint; admin must not mutate it.
        with self.assertRaises(NotFoundException):
            h.dispatch_cookie_consent_subroute(None, "summary", "POST", MagicMock(), {})


class TestGetOne(unittest.TestCase):
    def test_missing_row_raises_not_found(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        with self.assertRaises(NotFoundException):
            h.get_crm_cookie_consent(db, 999)


if __name__ == "__main__":
    unittest.main()
