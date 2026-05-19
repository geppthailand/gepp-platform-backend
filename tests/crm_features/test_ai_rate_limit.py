"""
Tests for AI template generation rate limit — BE Sonnet 2, Sprint 2, Task 3.

Verifies:
  - count_today returns correct per-user and per-org counts.
  - check_and_increment raises BadRequestException at the user limit (20/day).
  - check_and_increment raises BadRequestException at the org limit (100/day).
  - check_and_increment passes when under both limits.
  - Event emitted AFTER successful AI call (integration shape verified via mock).
  - After resetting events (simulated), first call succeeds again.

Run from v3/backend/:
    python -m pytest tests/crm/test_ai_rate_limit.py -v
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _make_db(user_count=0, org_count=0):
    """DB that returns user_count for first scalar(), org_count for second."""
    db = MagicMock()
    exec1 = MagicMock(); exec1.scalar.return_value = user_count
    exec2 = MagicMock(); exec2.scalar.return_value = org_count
    db.execute.side_effect = [exec1, exec2]
    return db


class TestCountToday(unittest.TestCase):

    def test_user_count_returned(self):
        from GEPPPlatform.services.admin.crm.ai_rate_limit import count_today
        db = _make_db(user_count=5, org_count=10)
        result = count_today(db, user_location_id=1, organization_id=42)
        self.assertEqual(result['user'], 5)
        self.assertEqual(result['org'], 10)

    def test_none_user_skips_user_query(self):
        from GEPPPlatform.services.admin.crm.ai_rate_limit import count_today
        # Only org query fires
        db = MagicMock()
        exec_org = MagicMock(); exec_org.scalar.return_value = 15
        db.execute.side_effect = [exec_org]
        result = count_today(db, user_location_id=None, organization_id=99)
        self.assertEqual(result['user'], 0)
        self.assertEqual(result['org'], 15)
        self.assertEqual(db.execute.call_count, 1)

    def test_none_org_skips_org_query(self):
        from GEPPPlatform.services.admin.crm.ai_rate_limit import count_today
        db = MagicMock()
        exec_user = MagicMock(); exec_user.scalar.return_value = 3
        db.execute.side_effect = [exec_user]
        result = count_today(db, user_location_id=7, organization_id=None)
        self.assertEqual(result['user'], 3)
        self.assertEqual(result['org'], 0)
        self.assertEqual(db.execute.call_count, 1)


class TestCheckAndIncrement(unittest.TestCase):

    def test_passes_when_under_limits(self):
        from GEPPPlatform.services.admin.crm.ai_rate_limit import check_and_increment
        db = _make_db(user_count=5, org_count=10)
        # Should not raise
        check_and_increment(db, user_location_id=1, organization_id=42)

    def test_raises_at_user_limit(self):
        """21st call for a user (count=20 existing) must raise."""
        from GEPPPlatform.services.admin.crm.ai_rate_limit import check_and_increment
        from GEPPPlatform.exceptions import BadRequestException
        db = _make_db(user_count=20, org_count=5)
        with self.assertRaises(BadRequestException) as ctx:
            check_and_increment(db, user_location_id=1, organization_id=42)
        self.assertIn('rate limit', str(ctx.exception).lower())
        self.assertIn('20', str(ctx.exception))

    def test_raises_at_org_limit(self):
        """101st call for an org (count=100 existing) must raise."""
        from GEPPPlatform.services.admin.crm.ai_rate_limit import check_and_increment
        from GEPPPlatform.exceptions import BadRequestException
        # user count is 0 but org count is at limit
        db = _make_db(user_count=0, org_count=100)
        with self.assertRaises(BadRequestException) as ctx:
            check_and_increment(db, user_location_id=1, organization_id=42)
        self.assertIn('rate limit', str(ctx.exception).lower())
        self.assertIn('100', str(ctx.exception))

    def test_user_limit_exact_boundary(self):
        """count=19 (under limit of 20) must pass."""
        from GEPPPlatform.services.admin.crm.ai_rate_limit import check_and_increment
        db = _make_db(user_count=19, org_count=0)
        check_and_increment(db, user_location_id=1, organization_id=None)  # must not raise

    def test_no_user_no_org_passes(self):
        """Both None — no queries fired, no exception."""
        from GEPPPlatform.services.admin.crm.ai_rate_limit import check_and_increment
        db = MagicMock()
        check_and_increment(db, user_location_id=None, organization_id=None)
        db.execute.assert_not_called()

    def test_after_reset_first_call_succeeds(self):
        """Simulated reset: count=0, call succeeds again."""
        from GEPPPlatform.services.admin.crm.ai_rate_limit import check_and_increment
        # Simulate that all previous events were deleted (count=0)
        db = _make_db(user_count=0, org_count=0)
        check_and_increment(db, user_location_id=1, organization_id=42)  # must not raise


class TestAIGenerateEndpointRateLimit(unittest.TestCase):
    """
    Integration-level: verify _dispatch_templates calls check_and_increment
    before calling call_llm_for_email, and emits an event after success.
    """

    @patch('GEPPPlatform.services.admin.crm.crm_service.emit_event')
    @patch('GEPPPlatform.services.admin.crm.ai_rate_limit.check_and_increment')
    @patch('GEPPPlatform.prompts.crm_email_gen.default.clients.llm_client.call_llm_for_email')
    def test_rate_limit_checked_before_llm(self, mock_llm, mock_check, mock_emit):
        from GEPPPlatform.services.admin.crm import _dispatch_templates

        mock_llm.return_value = {
            'subject': 'Test', 'body_html': '<p>Hi</p>', 'body_plain': 'Hi',
            'variables_detected': [], 'model': 'claude-3', 'token_usage': 100,
        }
        db = MagicMock()
        current_user = {'id': 1, 'organization_id': 42}

        _dispatch_templates(
            resource_id=None,
            sub_path='generate-ai',
            method='POST',
            db_session=db,
            data={'prompt': 'Write a welcome email'},
            query_params={},
            current_user=current_user,
        )

        # check_and_increment was called
        mock_check.assert_called_once()
        call_kwargs = mock_check.call_args[1]
        self.assertEqual(call_kwargs['user_location_id'], 1)
        self.assertEqual(call_kwargs['organization_id'], 42)

        # LLM was called after the guard
        mock_llm.assert_called_once()

        # Event emitted after success
        mock_emit.assert_called_once()
        emit_kwargs = mock_emit.call_args[1]
        self.assertEqual(emit_kwargs['event_type'], 'ai_template_generated')

    @patch('GEPPPlatform.services.admin.crm.ai_rate_limit.check_and_increment')
    @patch('GEPPPlatform.prompts.crm_email_gen.default.clients.llm_client.call_llm_for_email')
    def test_llm_not_called_when_rate_limit_exceeded(self, mock_llm, mock_check):
        from GEPPPlatform.services.admin.crm import _dispatch_templates
        from GEPPPlatform.exceptions import BadRequestException

        mock_check.side_effect = BadRequestException("AI rate limit exceeded: user …")
        db = MagicMock()

        with self.assertRaises(BadRequestException):
            _dispatch_templates(
                resource_id=None,
                sub_path='generate-ai',
                method='POST',
                db_session=db,
                data={'prompt': 'Hi'},
                query_params={},
                current_user={'id': 1, 'organization_id': 42},
            )

        mock_llm.assert_not_called()


if __name__ == '__main__':
    unittest.main()
