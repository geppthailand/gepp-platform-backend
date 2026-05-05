"""
Tests for campaign impact / lift analysis — BE Sonnet 2, Sprint 2, Task 2.

Verifies:
  - compute_impact returns zeros + started=False when started_at IS NULL.
  - recipientCount is correctly derived from crm_campaign_deliveries.
  - lift computation is correct: (after-before)/before*100.
  - partial=True when the after-window extends into the future.
  - Division-by-zero guard when before==0.
  - NotFoundException raised for missing campaign.

Run from v3/backend/:
    python -m pytest tests/crm/test_campaign_impact.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _make_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.execute = MagicMock()
    return db


def _camp_row(started_at):
    row = MagicMock()
    row.__getitem__ = lambda self, i: [1, started_at][i]
    return row


def _uid_rows(ids):
    return [MagicMock(**{'__getitem__': lambda self, _: uid}) for uid in ids]


def _dim_row(login=0, tx=0, qr=0, trace=0, gri=0, reward=0):
    """Build a mock row for the dimension COUNT(*) FILTER query."""
    values = [login, tx, qr, trace, gri, reward]
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    return row


class TestComputeImpactNotStarted(unittest.TestCase):

    def test_returns_started_false_when_no_started_at(self):
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        db = _make_db()
        camp = _camp_row(started_at=None)
        exec_camp = MagicMock(); exec_camp.fetchone.return_value = camp
        db.execute.side_effect = [exec_camp]

        result = compute_impact(db, campaign_id=1)

        self.assertFalse(result['started'])
        self.assertEqual(result['recipientCount'], 0)
        self.assertEqual(result['totalEventsBefore'], 0)
        self.assertEqual(result['totalEventsAfter'], 0)
        self.assertIsNone(result['totalLiftPct'])

    def test_not_found_raises(self):
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact
        from GEPPPlatform.exceptions import NotFoundException

        db = _make_db()
        exec_none = MagicMock(); exec_none.fetchone.return_value = None
        db.execute.side_effect = [exec_none]

        with self.assertRaises(NotFoundException):
            compute_impact(db, campaign_id=999)


class TestComputeImpactLift(unittest.TestCase):
    """Seed 10 recipients with synthetic before/after events and verify lift."""

    def _setup_db(self, started_at, before_counts, after_counts, recipient_ids=None):
        """
        Build a DB mock for compute_impact.

        Calls in order:
          1. Campaign SELECT (started_at)
          2. Recipient DISTINCT SELECT
          3. Before dimension COUNT query
          4. After dimension COUNT query
        """
        if recipient_ids is None:
            recipient_ids = list(range(1, 11))  # 10 recipients

        db = _make_db()
        exec_camp = MagicMock(); exec_camp.fetchone.return_value = _camp_row(started_at)
        exec_uids = MagicMock(); exec_uids.fetchall.return_value = _uid_rows(recipient_ids)
        exec_before = MagicMock(); exec_before.fetchone.return_value = _dim_row(**before_counts)
        exec_after  = MagicMock(); exec_after.fetchone.return_value  = _dim_row(**after_counts)

        db.execute.side_effect = [exec_camp, exec_uids, exec_before, exec_after]
        return db

    def test_recipient_count(self):
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        started = datetime.now(timezone.utc) - timedelta(days=60)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 100, 'tx': 200},
            after_counts={'login': 150, 'tx': 250},
            recipient_ids=list(range(1, 11)),
        )
        result = compute_impact(db, campaign_id=1, window_days=30)
        self.assertEqual(result['recipientCount'], 10)

    def test_lift_calculation(self):
        """loginCount: before=100, after=150 → lift=50.0 %."""
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        started = datetime.now(timezone.utc) - timedelta(days=60)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 100, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
            after_counts= {'login': 150, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
        )
        result = compute_impact(db, campaign_id=1, window_days=30)

        self.assertAlmostEqual(result['lift']['loginCount'], 50.0, places=2)

    def test_total_lift(self):
        """totalLiftPct = (totalAfter - totalBefore) / totalBefore * 100."""
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        started = datetime.now(timezone.utc) - timedelta(days=60)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 100, 'tx': 200, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
            after_counts= {'login': 150, 'tx': 250, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
        )
        result = compute_impact(db, campaign_id=1, window_days=30)

        # before total = 300, after total = 400 → lift = 33.33%
        self.assertAlmostEqual(result['totalLiftPct'], 33.33, places=2)
        self.assertEqual(result['totalEventsBefore'], 300)
        self.assertEqual(result['totalEventsAfter'], 400)

    def test_division_by_zero_lift_is_none(self):
        """When before==0, lift for that dimension must be None (not crash)."""
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        started = datetime.now(timezone.utc) - timedelta(days=60)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 0, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
            after_counts= {'login': 50, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
        )
        result = compute_impact(db, campaign_id=1, window_days=30)

        self.assertIsNone(result['lift']['loginCount'])
        self.assertIsNone(result['totalLiftPct'])

    def test_partial_window_flag(self):
        """When started_at is recent, after-window is incomplete → partial=True."""
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        # Started only 5 days ago, window_days=30 → after-window runs into future
        started = datetime.now(timezone.utc) - timedelta(days=5)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 10, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
            after_counts= {'login': 12, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
        )
        result = compute_impact(db, campaign_id=1, window_days=30)

        self.assertTrue(result['partial'])
        self.assertLess(result['actualAfterDays'], 30)

    def test_complete_window_flag(self):
        """When started_at is old enough, partial=False."""
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        started = datetime.now(timezone.utc) - timedelta(days=90)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 10, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
            after_counts= {'login': 20, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
        )
        result = compute_impact(db, campaign_id=1, window_days=30)

        self.assertFalse(result['partial'])
        self.assertEqual(result['actualAfterDays'], 30)

    def test_response_shape(self):
        """All required keys must be present in the response."""
        from GEPPPlatform.services.admin.crm.campaign_impact import compute_impact

        started = datetime.now(timezone.utc) - timedelta(days=60)
        db = self._setup_db(
            started_at=started,
            before_counts={'login': 10, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
            after_counts= {'login': 15, 'tx': 0, 'qr': 0, 'trace': 0, 'gri': 0, 'reward': 0},
        )
        result = compute_impact(db, campaign_id=1, window_days=30)

        required_top_keys = {
            'campaignId', 'windowDays', 'recipientCount', 'started', 'partial',
            'actualAfterDays', 'before', 'after', 'lift',
            'totalEventsBefore', 'totalEventsAfter', 'totalLiftPct',
        }
        for key in required_top_keys:
            self.assertIn(key, result, f"Missing key: {key!r}")

        dim_keys = {'loginCount', 'transactionCount', 'qrCount',
                    'traceabilityCount', 'griCount', 'rewardCount'}
        for key in dim_keys:
            self.assertIn(key, result['before'], f"Missing before.{key!r}")
            self.assertIn(key, result['after'],  f"Missing after.{key!r}")
            self.assertIn(key, result['lift'],   f"Missing lift.{key!r}")


if __name__ == '__main__':
    unittest.main()
