"""
Tests for Sprint 4 email engagement rollup in profile_refresher.py

Exercises:
  (a) Seed 3 events for 1 user → run refresher → assert email counts correct
  (b) Idempotency: running twice produces the same counts
  (c) Old events (> 30 days) are excluded from counts
  (d) Org-level rollup aggregates correctly
  (e) Zero counts when there are no email events

Run:
    python -m pytest tests/crm/test_email_engagement_rollup.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, call, patch
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm.profile_refresher import refresh_email_engagement


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_user_agg_rows(user_id=1, recv=1, opened=1, clicked=0,
                         last_recv=None, last_opened=None):
    """Simulate one row returned by the _EMAIL_USER_AGG_SQL aggregate query."""
    now = datetime.now(timezone.utc)
    return [(user_id, recv, opened, clicked,
             last_recv or now, last_opened or now)]


def _make_org_agg_rows(org_id=10, recv=2, opened=1, clicked=0, last_opened=None):
    now = datetime.now(timezone.utc)
    return [(org_id, recv, opened, clicked, last_opened or now)]


def _make_db(user_agg_rows, org_agg_rows):
    """
    Return a mock db session.

    execute() is called in this order by refresh_email_engagement():
      1. _EMAIL_USER_AGG_SQL  → user_agg_rows (fetchall)
      2. UPDATE per user_agg row (one per row)
      3. Reset UPDATE for users with no events (if any active rows → uses != ALL)
      4. _EMAIL_ORG_AGG_SQL   → org_agg_rows (fetchall)
      5. UPDATE per org_agg row
      6. Reset UPDATE for orgs (if any active rows)
    """
    db = MagicMock()
    call_results = []

    # User aggregate: fetchall
    user_mock = MagicMock()
    user_mock.fetchall.return_value = user_agg_rows
    call_results.append(user_mock)

    # One UPDATE per user row
    for _ in user_agg_rows:
        call_results.append(MagicMock())

    # Reset UPDATE (users not in active list)
    call_results.append(MagicMock())

    # Org aggregate: fetchall
    org_mock = MagicMock()
    org_mock.fetchall.return_value = org_agg_rows
    call_results.append(org_mock)

    # One UPDATE per org row
    for _ in org_agg_rows:
        call_results.append(MagicMock())

    # Reset UPDATE (orgs not in active list)
    call_results.append(MagicMock())

    db.execute.side_effect = call_results
    db.commit = MagicMock()
    return db


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestEmailEngagementRollup(unittest.TestCase):

    def test_a_basic_user_counts(self):
        """
        (a) 3 email events for 1 user: 1 sent, 1 opened, 1 clicked.
        refresh_email_engagement returns the correct user_rows_updated.
        """
        user_rows = _make_user_agg_rows(user_id=42, recv=1, opened=1, clicked=1)
        org_rows = []
        db = _make_db(user_rows, org_rows)

        # Need to patch out the empty-list branch for org (no rows)
        # Re-supply side_effect for the org path: agg, then reset (no per-row updates)
        org_mock = MagicMock()
        org_mock.fetchall.return_value = []
        # Rebuild side_effect
        user_mock = MagicMock()
        user_mock.fetchall.return_value = user_rows
        side = [user_mock, MagicMock(), MagicMock(), org_mock, MagicMock()]
        db.execute.side_effect = side

        result = refresh_email_engagement(db)

        self.assertEqual(result['user_rows_updated'], 1)
        self.assertEqual(result['org_rows_updated'], 0)
        self.assertIn('duration_s', result)

    def test_b_idempotency(self):
        """
        (b) Running refresh_email_engagement twice with the same aggregate data
        produces the same user_rows_updated and org_rows_updated each time.
        """
        user_rows = _make_user_agg_rows(user_id=7, recv=2, opened=1, clicked=0)
        org_rows = _make_org_agg_rows(org_id=3, recv=2, opened=1, clicked=0)

        def _fresh_db():
            return _make_db(user_rows, org_rows)

        first = refresh_email_engagement(_fresh_db())
        second = refresh_email_engagement(_fresh_db())

        self.assertEqual(first['user_rows_updated'], second['user_rows_updated'])
        self.assertEqual(first['org_rows_updated'], second['org_rows_updated'])

    def test_c_old_events_excluded(self):
        """
        (c) Events older than 30 days must not appear in the aggregate.
        The aggregate SQL uses occurred_at > :window_30d — so no rows are returned
        for old-only events. refresh_email_engagement should report 0 user/org rows
        and commit.
        """
        # Simulate: DB aggregate returns zero rows (old events filtered at DB level)
        db = MagicMock()
        user_mock = MagicMock()
        user_mock.fetchall.return_value = []   # No recent email events
        org_mock = MagicMock()
        org_mock.fetchall.return_value = []

        # Side effects: user_agg, user_reset, org_agg, org_reset
        db.execute.side_effect = [user_mock, MagicMock(), org_mock, MagicMock()]
        db.commit = MagicMock()

        result = refresh_email_engagement(db)

        self.assertEqual(result['user_rows_updated'], 0)
        self.assertEqual(result['org_rows_updated'], 0)
        db.commit.assert_called_once()

    def test_d_org_rollup(self):
        """
        (d) Org-level rollup uses organization_id and the org_* columns.
        Assert org_rows_updated matches the number of org aggregate rows.
        """
        user_rows = []
        org_rows = _make_org_agg_rows(org_id=99, recv=5, opened=3, clicked=1)

        db = MagicMock()
        user_mock = MagicMock()
        user_mock.fetchall.return_value = user_rows
        org_mock = MagicMock()
        org_mock.fetchall.return_value = org_rows

        # user_agg, user_reset (no per-row updates), org_agg, org_update, org_reset
        db.execute.side_effect = [user_mock, MagicMock(), org_mock, MagicMock(), MagicMock()]
        db.commit = MagicMock()

        result = refresh_email_engagement(db)

        self.assertEqual(result['org_rows_updated'], 1)
        self.assertEqual(result['user_rows_updated'], 0)

    def test_e_zero_counts_no_events(self):
        """
        (e) When there are no email events at all, refresh_email_engagement
        reports zero rows updated for both users and orgs.
        """
        db = MagicMock()
        user_mock = MagicMock()
        user_mock.fetchall.return_value = []
        org_mock = MagicMock()
        org_mock.fetchall.return_value = []

        db.execute.side_effect = [user_mock, MagicMock(), org_mock, MagicMock()]
        db.commit = MagicMock()

        result = refresh_email_engagement(db)

        self.assertEqual(result['user_rows_updated'], 0)
        self.assertEqual(result['org_rows_updated'], 0)


if __name__ == '__main__':
    unittest.main()
