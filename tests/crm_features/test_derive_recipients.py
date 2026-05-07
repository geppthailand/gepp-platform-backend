"""
Tests for POST /admin/crm-campaigns/{id}/derive-recipients

Exercises:
  (a) kind='non_openers'          → returns matching user IDs and emails
  (b) kind='openers_not_clickers' → returns matching rows
  (c) kind='bouncers'             → returns matching rows
  (d) No matching rows            → returns empty lists (count=0)
  (e) Invalid kind                → BadRequestException
  (f) Campaign not found          → NotFoundException

Run:
    python -m pytest tests/crm/test_derive_recipients.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm import _derive_recipients
from GEPPPlatform.exceptions import BadRequestException, NotFoundException


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_db_for_derive(campaign_exists=True, delivery_rows=None):
    """
    Build a mock db session for _derive_recipients.
    Execute calls:
      1. Campaign EXISTS check
      2. SELECT on crm_campaign_deliveries → fetchall() returns delivery_rows
    """
    db = MagicMock()

    exists_mock = MagicMock()
    exists_mock.fetchone.return_value = (1,) if campaign_exists else None

    deliveries_mock = MagicMock()
    deliveries_mock.fetchall.return_value = delivery_rows or []

    db.execute.side_effect = [exists_mock, deliveries_mock]
    return db


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestDeriveRecipients(unittest.TestCase):

    def test_a_non_openers(self):
        """
        (a) kind='non_openers' returns user IDs and emails from rows with
        status IN ('sent','delivered').
        """
        rows = [(101, 'alice@example.com'), (102, 'bob@example.com')]
        db = _make_db_for_derive(delivery_rows=rows)

        result = _derive_recipients(db, campaign_id=1, kind='non_openers')

        self.assertEqual(result['kind'], 'non_openers')
        self.assertEqual(result['campaignId'], 1)
        self.assertEqual(result['recipientUserIds'], [101, 102])
        self.assertEqual(result['emails'], ['alice@example.com', 'bob@example.com'])
        self.assertEqual(result['count'], 2)

    def test_b_openers_not_clickers(self):
        """
        (b) kind='openers_not_clickers' returns the matching rows.
        """
        rows = [(55, 'carol@example.com')]
        db = _make_db_for_derive(delivery_rows=rows)

        result = _derive_recipients(db, campaign_id=7, kind='openers_not_clickers')

        self.assertEqual(result['kind'], 'openers_not_clickers')
        self.assertEqual(result['count'], 1)
        self.assertIn(55, result['recipientUserIds'])
        self.assertIn('carol@example.com', result['emails'])

    def test_c_bouncers(self):
        """
        (c) kind='bouncers' returns the matching rows.
        """
        rows = [(200, 'bounce@bad.com'), (201, None)]   # one row has no email
        db = _make_db_for_derive(delivery_rows=rows)

        result = _derive_recipients(db, campaign_id=3, kind='bouncers')

        self.assertEqual(result['kind'], 'bouncers')
        self.assertEqual(result['count'], 2)
        # user IDs: both present
        self.assertIn(200, result['recipientUserIds'])
        self.assertIn(201, result['recipientUserIds'])
        # email: None row filtered out
        self.assertNotIn(None, result['emails'])
        self.assertEqual(len(result['emails']), 1)

    def test_d_empty_list_for_no_matching_rows(self):
        """
        (d) When no deliveries match the kind, return empty lists and count=0.
        """
        db = _make_db_for_derive(delivery_rows=[])

        result = _derive_recipients(db, campaign_id=10, kind='bouncers')

        self.assertEqual(result['recipientUserIds'], [])
        self.assertEqual(result['emails'], [])
        self.assertEqual(result['count'], 0)

    def test_e_invalid_kind_raises(self):
        """
        (e) An unknown kind must raise BadRequestException before touching the DB.
        """
        db = _make_db_for_derive()

        with self.assertRaises(BadRequestException) as ctx:
            _derive_recipients(db, campaign_id=1, kind='unknown_kind')

        self.assertIn('kind', str(ctx.exception).lower())

    def test_f_campaign_not_found(self):
        """
        (f) A non-existent campaign_id must raise NotFoundException.
        """
        db = _make_db_for_derive(campaign_exists=False)

        with self.assertRaises(NotFoundException):
            _derive_recipients(db, campaign_id=9999, kind='non_openers')

    def test_g_response_has_computed_at(self):
        """
        computedAt must be present and ISO-parseable.
        """
        db = _make_db_for_derive(delivery_rows=[])
        result = _derive_recipients(db, campaign_id=1, kind='non_openers')

        from datetime import datetime
        dt = datetime.fromisoformat(result['computedAt'].replace('Z', '+00:00'))
        self.assertIsInstance(dt, datetime)

    def test_h_user_id_none_excluded_from_user_ids(self):
        """
        Rows where user_location_id is None (email-list-only recipients)
        must be excluded from recipientUserIds but included in emails.
        """
        rows = [(None, 'list@example.com'), (42, 'user@example.com')]
        db = _make_db_for_derive(delivery_rows=rows)

        result = _derive_recipients(db, campaign_id=1, kind='non_openers')

        self.assertNotIn(None, result['recipientUserIds'])
        self.assertIn(42, result['recipientUserIds'])
        self.assertIn('list@example.com', result['emails'])
        self.assertIn('user@example.com', result['emails'])


if __name__ == '__main__':
    unittest.main()
