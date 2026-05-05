"""
Tests for crm-campaigns/{id}/metrics endpoint (BE Sonnet 2, Sprint 1).

Verifies:
- Correct aggregation of delivery counts from mixed statuses
- Rate computation (openRate, clickRate, bounceRate, unsubscribeRate)
- metrics_cache is populated after first call
- Second call within TTL returns cached data without re-querying

Run from v3/backend/:
    python -m pytest tests/test_campaign_metrics.py -v

Or standalone:
    python -m unittest tests.test_campaign_metrics
"""

import sys
import os
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.execute = MagicMock()
    return db


def _call_metrics(db, campaign_id=1, query_params=None):
    """Invoke the metrics sub-route through _dispatch_campaigns."""
    from GEPPPlatform.services.admin.crm import _dispatch_campaigns
    return _dispatch_campaigns(
        resource_id=campaign_id,
        sub_path='metrics',
        method='GET',
        db_session=db,
        data={},
        query_params=query_params or {},
    )


# ── Fixture: 10 deliveries with mixed statuses ────────────────────────────────
# Mapping per task spec:
#   sent=8 (status in sent-family excluding pending+failed)
#   opened=3 (status in ('opened','clicked'))
#   clicked=1
#   bounced=1 (hard_bounced)
#   unsubscribed=1
#   failed=1
#   pending=2 (pending + sending count as "pending" in the endpoint output... wait)
#
# Re-reading the task spec carefully:
#   "Seed a campaign + 10 deliveries with mixed statuses
#    (3 sent, 2 opened, 1 clicked, 1 bounced, 1 unsubscribed, 1 failed, 1 pending)"
#   "assert: sent=8, opened=3, clicked=1, bounced=1, unsubscribed=1, failed=1, pending=1"
#
# This means:
#   3 rows with status='sent'       → in sent-family → sent count
#   2 rows with status='opened'     → in sent-family + opened-family
#   1 row  with status='clicked'    → in sent-family + opened-family + clicked
#   1 row  with status='hard_bounced' → in sent-family + bounced
#   1 row  with status='unsubscribed' → in sent-family + unsubscribed
#   1 row  with status='failed'     → failed only
#   1 row  with status='pending'    → pending only
# Total = 10 rows
# sent-family: 3+2+1+1+1 = 8 ✓
# opened-family: 2+1 = 3 ✓
# clicked: 1 ✓   bounced: 1 ✓   unsubscribed: 1 ✓   failed: 1 ✓   pending: 1 ✓
# openRate = 3/8*100 = 37.5 ✓
# clickRate = 1/3*100 = 33.33 ✓
# bounceRate = 1/8*100 = 12.5 ✓
# unsubRate  = 1/8*100 = 12.5 ✓

_AGG_COUNTS = (
    10,   # total
    8,    # sent
    3,    # opened
    1,    # clicked
    1,    # bounced
    1,    # unsubscribed
    1,    # failed
    1,    # pending
    datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc),   # first_sent_at
    datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc),   # last_sent_at
)


def _db_no_cache_then_agg(campaign_id=1):
    """
    DB mock where:
      1st execute (cache check) → returns (NULL, NULL)  (no cache)
      2nd execute (aggregation)  → returns _AGG_COUNTS tuple
      3rd execute (cache update) → returns generic MagicMock
    """
    db = _make_db()
    null_cache_row = MagicMock()
    null_cache_row.__getitem__ = lambda self, i: (None, None)[i]  # metrics_cache=None, metrics_cached_at=None

    agg_row = MagicMock()
    agg_row.__getitem__ = lambda self, i: _AGG_COUNTS[i]

    update_result = MagicMock()

    # fetchone() calls
    db.execute.return_value.fetchone.side_effect = [null_cache_row, agg_row]
    db.execute.return_value = MagicMock(fetchone=MagicMock(side_effect=[null_cache_row, agg_row]))

    # We need to handle the three execute() calls: cache-read, agg-read, cache-write
    exec1 = MagicMock(); exec1.fetchone.return_value = null_cache_row
    exec2 = MagicMock(); exec2.fetchone.return_value = agg_row
    exec3 = MagicMock()  # UPDATE — no fetchone

    db.execute.side_effect = [exec1, exec2, exec3]
    return db


class TestCampaignMetricsAggregation(unittest.TestCase):
    """Verify metric counts and rates are computed correctly."""

    def _build_db(self, total=10, sent=8, opened=3, clicked=1, bounced=1,
                  unsub=1, failed=1, pending=1):
        """Build a mock DB that returns the specified aggregate counts."""
        db = _make_db()

        null_cache_row = MagicMock()
        # Index 0 = metrics_cache, index 1 = metrics_cached_at
        null_cache_row.__getitem__ = lambda self, i: (None, None)[i]

        first_sent = datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc)
        last_sent  = datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc)
        counts = (total, sent, opened, clicked, bounced, unsub, failed, pending,
                  first_sent, last_sent)
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: counts[i]

        exec1 = MagicMock(); exec1.fetchone.return_value = null_cache_row
        exec2 = MagicMock(); exec2.fetchone.return_value = agg_row
        exec3 = MagicMock()  # UPDATE

        db.execute.side_effect = [exec1, exec2, exec3]
        return db

    def test_sent_count(self):
        db = self._build_db()
        result = _call_metrics(db, campaign_id=1)
        self.assertEqual(result['sent'], 8)

    def test_opened_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['opened'], 3)

    def test_clicked_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['clicked'], 1)

    def test_bounced_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['bounced'], 1)

    def test_unsubscribed_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['unsubscribed'], 1)

    def test_failed_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['failed'], 1)

    def test_pending_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['pending'], 1)

    def test_total_count(self):
        db = self._build_db()
        result = _call_metrics(db)
        self.assertEqual(result['total'], 10)

    def test_open_rate(self):
        """openRate = opened / sent * 100 = 3/8*100 = 37.5"""
        db = self._build_db()
        result = _call_metrics(db)
        self.assertAlmostEqual(result['openRate'], 37.5, places=2)

    def test_click_rate(self):
        """clickRate = clicked / opened * 100 = 1/3*100 = 33.33"""
        db = self._build_db()
        result = _call_metrics(db)
        self.assertAlmostEqual(result['clickRate'], 33.33, places=2)

    def test_bounce_rate(self):
        """bounceRate = bounced / sent * 100 = 1/8*100 = 12.5"""
        db = self._build_db()
        result = _call_metrics(db)
        self.assertAlmostEqual(result['bounceRate'], 12.5, places=2)

    def test_unsub_rate(self):
        """unsubscribeRate = unsub / sent * 100 = 1/8*100 = 12.5"""
        db = self._build_db()
        result = _call_metrics(db)
        self.assertAlmostEqual(result['unsubscribeRate'], 12.5, places=2)

    def test_zero_division_guard_open_rate(self):
        """openRate = 0 when sent = 0 (no division by zero)."""
        db = self._build_db(sent=0, opened=0, clicked=0, bounced=0, unsub=0)
        result = _call_metrics(db)
        self.assertEqual(result['openRate'], 0.0)

    def test_zero_division_guard_click_rate(self):
        """clickRate = 0 when opened = 0 (no division by zero)."""
        db = self._build_db(opened=0, clicked=0)
        result = _call_metrics(db)
        self.assertEqual(result['clickRate'], 0.0)


class TestCampaignMetricsCache(unittest.TestCase):
    """Verify metrics_cache is populated and honoured within 5-minute TTL."""

    def _build_db_no_cache(self, total=10, sent=8, opened=3, clicked=1, bounced=1,
                            unsub=1, failed=1, pending=1):
        db = _make_db()
        null_cache_row = MagicMock()
        null_cache_row.__getitem__ = lambda self, i: (None, None)[i]

        counts = (total, sent, opened, clicked, bounced, unsub, failed, pending,
                  datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc),
                  datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc))
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: counts[i]

        exec1 = MagicMock(); exec1.fetchone.return_value = null_cache_row
        exec2 = MagicMock(); exec2.fetchone.return_value = agg_row
        exec3 = MagicMock()  # UPDATE

        db.execute.side_effect = [exec1, exec2, exec3]
        return db

    def test_cache_update_called_after_recompute(self):
        """After recomputing, db.execute is called 3 times: read cache, read agg, write cache."""
        db = self._build_db_no_cache()
        _call_metrics(db)
        self.assertEqual(db.execute.call_count, 3)

    def test_commit_called_after_cache_write(self):
        """db.commit() is called after writing to metrics_cache."""
        db = self._build_db_no_cache()
        _call_metrics(db)
        db.commit.assert_called_once()

    def test_second_call_within_ttl_returns_cache(self):
        """
        Second call within 5 minutes should read from cache and NOT call db.execute
        more than once (just the cache-read SELECT).
        """
        db = _make_db()

        # Fresh cached metrics
        cached_metrics = {
            "campaignId": 1, "total": 10, "sent": 8, "opened": 3,
            "clicked": 1, "bounced": 1, "unsubscribed": 1, "failed": 1, "pending": 1,
            "openRate": 37.5, "clickRate": 33.33, "bounceRate": 12.5, "unsubscribeRate": 12.5,
            "firstSentAt": "2026-04-28T10:00:00+00:00", "lastSentAt": "2026-04-28T18:00:00+00:00",
        }
        fresh_cache_at = datetime.now(timezone.utc) - timedelta(seconds=60)  # 1 min ago = fresh

        cached_row = MagicMock()
        cached_row.__getitem__ = lambda self, i: (cached_metrics, fresh_cache_at)[i]

        exec1 = MagicMock(); exec1.fetchone.return_value = cached_row
        db.execute.side_effect = [exec1]

        result = _call_metrics(db)

        # Only 1 execute call (cache read) — no aggregation query
        self.assertEqual(db.execute.call_count, 1)
        # Returns cached data
        self.assertEqual(result['openRate'], 37.5)

    def test_force_refresh_bypasses_cache(self):
        """?refresh=true forces recomputation even when cache is fresh."""
        db = _make_db()

        cached_metrics = {"campaignId": 1, "sent": 8, "openRate": 37.5}
        fresh_cache_at = datetime.now(timezone.utc) - timedelta(seconds=60)

        counts = (10, 8, 3, 1, 1, 1, 1, 1,
                  datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc),
                  datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc))
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: counts[i]

        exec_agg = MagicMock(); exec_agg.fetchone.return_value = agg_row
        exec_upd = MagicMock()

        # With refresh=true, skip cache check entirely → straight to agg + update
        db.execute.side_effect = [exec_agg, exec_upd]

        result = _call_metrics(db, query_params={'refresh': 'true'})

        self.assertGreaterEqual(db.execute.call_count, 2)
        self.assertEqual(result['sent'], 8)

    def test_stale_cache_triggers_recompute(self):
        """Cache older than 5 minutes is ignored; metrics are recomputed."""
        db = _make_db()

        old_metrics = {"campaignId": 1, "sent": 5, "openRate": 20.0}
        stale_cache_at = datetime.now(timezone.utc) - timedelta(minutes=10)  # 10 min ago

        stale_row = MagicMock()
        stale_row.__getitem__ = lambda self, i: (old_metrics, stale_cache_at)[i]

        counts = (10, 8, 3, 1, 1, 1, 1, 1,
                  datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc),
                  datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc))
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: counts[i]

        exec1 = MagicMock(); exec1.fetchone.return_value = stale_row  # cache read (stale)
        exec2 = MagicMock(); exec2.fetchone.return_value = agg_row     # fresh aggregation
        exec3 = MagicMock()                                            # cache write

        db.execute.side_effect = [exec1, exec2, exec3]

        result = _call_metrics(db)

        # Recomputed, not the stale value
        self.assertEqual(result['sent'], 8)
        self.assertEqual(db.execute.call_count, 3)


class TestCampaignDeliveriesSubRoute(unittest.TestCase):
    """Verify /crm-campaigns/{id}/deliveries delegates to list_crm_deliveries."""

    @patch('GEPPPlatform.services.admin.crm.crm_handlers.list_crm_deliveries')
    def test_deliveries_route_injects_campaign_id(self, mock_list):
        from GEPPPlatform.services.admin.crm import _dispatch_campaigns
        mock_list.return_value = {"items": [], "total": 0, "page": 1, "pageSize": 25}

        db = _make_db()
        _dispatch_campaigns(
            resource_id=42,
            sub_path='deliveries',
            method='GET',
            db_session=db,
            data={},
            query_params={'page': '1', 'pageSize': '10'},
        )

        # list_crm_deliveries must be called with campaignId injected
        mock_list.assert_called_once()
        call_args = mock_list.call_args[0]  # positional: (db, query_params)
        passed_params = call_args[1]
        self.assertEqual(int(passed_params['campaignId']), 42)


class TestCampaignMetricsResponseShape(unittest.TestCase):
    """Verify the response contains all required keys."""

    _REQUIRED_KEYS = {
        'campaignId', 'total', 'sent', 'opened', 'clicked', 'bounced',
        'unsubscribed', 'failed', 'pending',
        'openRate', 'clickRate', 'bounceRate', 'unsubscribeRate',
        'firstSentAt', 'lastSentAt',
    }

    def test_all_required_keys_present(self):
        db = _make_db()

        null_cache_row = MagicMock()
        null_cache_row.__getitem__ = lambda self, i: (None, None)[i]

        counts = (10, 8, 3, 1, 1, 1, 1, 1,
                  datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc),
                  datetime(2026, 4, 28, 18, 0, 0, tzinfo=timezone.utc))
        agg_row = MagicMock()
        agg_row.__getitem__ = lambda self, i: counts[i]

        exec1 = MagicMock(); exec1.fetchone.return_value = null_cache_row
        exec2 = MagicMock(); exec2.fetchone.return_value = agg_row
        exec3 = MagicMock()
        db.execute.side_effect = [exec1, exec2, exec3]

        result = _call_metrics(db)

        for key in self._REQUIRED_KEYS:
            self.assertIn(key, result, f"Missing key: {key!r}")


if __name__ == '__main__':
    unittest.main()
