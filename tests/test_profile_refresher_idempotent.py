"""
Idempotency tests for GEPPPlatform/services/admin/crm/profile_refresher.py

Verifies that run_full_refresh() is safe to call repeatedly:
- Row counts do not change between runs
- Key counters reflect inserted events correctly

Run from v3/backend/:
    python -m pytest tests/test_profile_refresher_idempotent.py -v

Or standalone:
    python -m unittest tests.test_profile_refresher_idempotent
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, call, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _make_db(user_rowcount=3, org_rowcount=2):
    """
    Return a mock db session that simulates UPSERT rowcounts.
    Each execute() returns a result with the specified rowcount.
    """
    db = MagicMock()

    user_result = MagicMock()
    user_result.rowcount = user_rowcount
    user_result.fetchall.return_value = []

    org_result = MagicMock()
    org_result.rowcount = org_rowcount
    org_result.fetchall.return_value = []

    empty_result = MagicMock()
    empty_result.rowcount = 0
    empty_result.fetchall.return_value = []

    # Sprint 4: each run_full_refresh now calls execute ~6 times (user UPSERT, org UPSERT,
    # email user SELECT, email org SELECT, plus 2 zero-reset UPDATEs). Cycle every 6 calls
    # so the second run gets fresh rowcounts on the first 2 calls.
    call_idx = {"n": 0}
    def execute_handler(*args, **kwargs):
        call_idx["n"] += 1
        pos = (call_idx["n"] - 1) % 6
        if pos == 0:
            return user_result
        elif pos == 1:
            return org_result
        else:
            return empty_result

    db.execute.side_effect = execute_handler
    db.commit = MagicMock()
    return db


class TestRunFullRefreshIdempotent(unittest.TestCase):
    """
    run_full_refresh() must be safely callable multiple times without
    changing the logical state of the system (idempotent UPSERT).
    """

    def test_returns_expected_keys(self):
        """run_full_refresh() returns a dict with user_profiles and org_profiles."""
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = _make_db()
        result = run_full_refresh(db)

        self.assertIn('user_profiles', result)
        self.assertIn('org_profiles', result)

    def test_user_profiles_has_rows_upserted(self):
        """user_profiles sub-dict contains rows_upserted and duration_s."""
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = _make_db(user_rowcount=5)
        result = run_full_refresh(db)

        self.assertIn('rows_upserted', result['user_profiles'])
        self.assertIn('duration_s', result['user_profiles'])
        self.assertEqual(result['user_profiles']['rows_upserted'], 5)

    def test_org_profiles_has_rows_upserted(self):
        """org_profiles sub-dict contains rows_upserted and duration_s."""
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = _make_db(org_rowcount=2)
        result = run_full_refresh(db)

        self.assertIn('rows_upserted', result['org_profiles'])
        self.assertEqual(result['org_profiles']['rows_upserted'], 2)

    def test_idempotent_row_count_stable(self):
        """
        Calling run_full_refresh twice returns the same row counts.
        The UPSERT logic means re-running with the same underlying events
        touches the same number of rows.
        """
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        user_rc = 7
        org_rc = 3

        # Sprint 4: each run_full_refresh now calls execute 4 times (user, org, email_user, email_org).
        # Use a callable side_effect that returns rowcount-bearing results for UPSERTs and empty
        # fetchall for the email-engagement SELECTs.
        db = MagicMock()
        ur = MagicMock(); ur.rowcount = user_rc; ur.fetchall.return_value = []
        or_ = MagicMock(); or_.rowcount = org_rc; or_.fetchall.return_value = []
        empty = MagicMock(); empty.rowcount = 0; empty.fetchall.return_value = []
        idx = {"n": 0}
        def _h(*a, **k):
            idx["n"] += 1
            pos = (idx["n"] - 1) % 6
            return ur if pos == 0 else (or_ if pos == 1 else empty)
        db.execute.side_effect = _h
        db.commit = MagicMock()

        first  = run_full_refresh(db)
        second = run_full_refresh(db)

        self.assertEqual(
            first['user_profiles']['rows_upserted'],
            second['user_profiles']['rows_upserted'],
            "User profile row count must be stable across repeated runs",
        )
        self.assertEqual(
            first['org_profiles']['rows_upserted'],
            second['org_profiles']['rows_upserted'],
            "Org profile row count must be stable across repeated runs",
        )

    def test_commit_called_thrice(self):
        """run_full_refresh() commits once per sub-refresh (user, org, email_engagement = 3 total)."""
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = _make_db()
        run_full_refresh(db)

        self.assertEqual(db.commit.call_count, 3)

    def test_execute_called_at_least_four_times(self):
        """
        run_full_refresh() calls db.execute() at least 4 times: user UPSERT + org UPSERT
        + email user agg SELECT + email org agg SELECT (+ optional zero-reset UPDATEs).
        """
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = _make_db()
        run_full_refresh(db)

        self.assertGreaterEqual(db.execute.call_count, 4)

    def test_negative_rowcount_treated_as_minus_one(self):
        """If driver returns rowcount=-1 (unknown), rows_upserted is reported as -1."""
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = MagicMock()
        neg = MagicMock(); neg.rowcount = -1
        db.execute.return_value = neg
        db.commit = MagicMock()

        result = run_full_refresh(db)

        self.assertEqual(result['user_profiles']['rows_upserted'], -1)

    def test_duration_is_non_negative_float(self):
        """duration_s must be a non-negative float."""
        from GEPPPlatform.services.admin.crm.profile_refresher import run_full_refresh

        db = _make_db()
        result = run_full_refresh(db)

        self.assertIsInstance(result['user_profiles']['duration_s'], float)
        self.assertGreaterEqual(result['user_profiles']['duration_s'], 0.0)
        self.assertIsInstance(result['org_profiles']['duration_s'], float)
        self.assertGreaterEqual(result['org_profiles']['duration_s'], 0.0)

    def test_lambda_handler_wraps_run_full_refresh(self):
        """
        profile_refresher_lambda.lambda_handler() calls run_full_refresh
        and returns statusCode 200.
        """
        import GEPPPlatform.services.admin.crm.profile_refresher_lambda as lm

        mock_summary = {
            'user_profiles': {'rows_upserted': 10, 'duration_s': 0.5},
            'org_profiles': {'rows_upserted': 4, 'duration_s': 0.2},
        }

        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx_mgr.__exit__ = MagicMock(return_value=False)

        with patch.object(lm, 'run_full_refresh', return_value=mock_summary) as mock_refresh, \
             patch.object(lm, 'get_session', return_value=mock_ctx_mgr):
            response = lm.lambda_handler({}, None)

        self.assertEqual(response['statusCode'], 200)
        mock_refresh.assert_called_once_with(mock_session)

    def test_lambda_handler_importable(self):
        """lambda_handler can be imported and has a docstring."""
        from GEPPPlatform.services.admin.crm.profile_refresher_lambda import lambda_handler
        self.assertTrue(callable(lambda_handler))
        self.assertIsNotNone(lambda_handler.__doc__)


if __name__ == '__main__':
    unittest.main()
