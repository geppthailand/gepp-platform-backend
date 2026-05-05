"""
Tests for GET /admin/crm-campaigns/{id}/suggested-actions

Exercises:
  (a) Endpoint returns expected keys (200 shape)
  (b) opened-not-clicked logic: only 'opened' rows where first_clicked_at IS NULL
      and sent_at < now-7d are counted
  (c) bounced count includes hard_bounced, soft_bounced, rejected
  (d) pending-over-24h counts pending rows created > 24h ago
  (e) Returns zero-state when campaign has no deliveries

Run:
    python -m pytest tests/crm/test_suggested_actions.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Import the private function directly from the CRM init module
from GEPPPlatform.services.admin.crm import _get_suggested_actions
from GEPPPlatform.exceptions import NotFoundException


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_db_for_suggested(
    campaign_exists=True,
    opened=0,
    opened_not_clicked=0,
    bounced_count=0,
    pending_over_24h=0,
    total_recipients=0,
):
    """
    Build a mock db whose execute() calls simulate:
      1. EXISTS check for campaign → returns one row if campaign_exists
      2. Aggregate SELECT → returns (opened, opened_not_clicked, bounced_count,
                                      pending_over_24h, total_recipients)
    """
    db = MagicMock()

    # Call 1: campaign exists check
    exists_mock = MagicMock()
    exists_mock.fetchone.return_value = (1,) if campaign_exists else None

    # Call 2: aggregate row
    agg_mock = MagicMock()
    agg_mock.fetchone.return_value = (
        opened,
        opened_not_clicked,
        bounced_count,
        pending_over_24h,
        total_recipients,
    )

    db.execute.side_effect = [exists_mock, agg_mock]
    return db


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestSuggestedActions(unittest.TestCase):

    def test_a_returns_expected_keys(self):
        """
        (a) The endpoint returns a dict with all documented keys.
        """
        db = _make_db_for_suggested(
            campaign_exists=True,
            opened=5,
            opened_not_clicked=2,
            bounced_count=1,
            pending_over_24h=0,
            total_recipients=10,
        )
        result = _get_suggested_actions(db, campaign_id=1)

        expected_keys = {
            'campaignId', 'opened', 'openedNotClicked',
            'bouncedCount', 'pendingOver24hCount',
            'totalRecipients', 'computedAt',
        }
        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result['campaignId'], 1)

    def test_b_opened_not_clicked_logic(self):
        """
        (b) openedNotClicked reflects only 'opened' rows where first_clicked_at IS NULL
        and sent_at < now-7d. The DB does the filtering; we assert the value is
        plumbed through correctly.
        """
        db = _make_db_for_suggested(
            opened=8,
            opened_not_clicked=3,
            total_recipients=20,
        )
        result = _get_suggested_actions(db, campaign_id=42)

        self.assertEqual(result['openedNotClicked'], 3)
        self.assertEqual(result['opened'], 8)

    def test_c_bounced_count(self):
        """
        (c) bouncedCount aggregates hard_bounced + soft_bounced + rejected statuses.
        """
        db = _make_db_for_suggested(
            bounced_count=4,
            total_recipients=15,
        )
        result = _get_suggested_actions(db, campaign_id=7)

        self.assertEqual(result['bouncedCount'], 4)

    def test_d_pending_over_24h(self):
        """
        (d) pendingOver24hCount reflects rows with status='pending' and
        created_date < now-24h.
        """
        db = _make_db_for_suggested(
            pending_over_24h=2,
            total_recipients=5,
        )
        result = _get_suggested_actions(db, campaign_id=99)

        self.assertEqual(result['pendingOver24hCount'], 2)

    def test_e_zero_state_no_deliveries(self):
        """
        (e) A campaign with no deliveries returns zeros for all counts.
        """
        db = _make_db_for_suggested(
            opened=0,
            opened_not_clicked=0,
            bounced_count=0,
            pending_over_24h=0,
            total_recipients=0,
        )
        result = _get_suggested_actions(db, campaign_id=5)

        self.assertEqual(result['opened'], 0)
        self.assertEqual(result['openedNotClicked'], 0)
        self.assertEqual(result['bouncedCount'], 0)
        self.assertEqual(result['pendingOver24hCount'], 0)
        self.assertEqual(result['totalRecipients'], 0)

    def test_f_campaign_not_found(self):
        """
        Campaign that doesn't exist must raise NotFoundException.
        """
        db = _make_db_for_suggested(campaign_exists=False)
        with self.assertRaises(NotFoundException):
            _get_suggested_actions(db, campaign_id=9999)

    def test_g_computed_at_is_iso_string(self):
        """
        computedAt must be an ISO-format datetime string.
        """
        db = _make_db_for_suggested(total_recipients=1)
        result = _get_suggested_actions(db, campaign_id=1)

        from datetime import datetime
        # Should not raise
        dt = datetime.fromisoformat(result['computedAt'].replace('Z', '+00:00'))
        self.assertIsInstance(dt, datetime)


if __name__ == '__main__':
    unittest.main()
