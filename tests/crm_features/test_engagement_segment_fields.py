"""
Tests for Sprint 4 email-engagement segment fields in segment_evaluator.py

Exercises:
  (a) 'last_email_opened_at IS NULL' compiles correctly (no bind param)
  (b) 'emails_opened_30d > 5' compiles to valid SQL with bind param
  (c) Org-scope email fields compile correctly (org_emails_received_30d, etc.)
  (d) IS NOT NULL also works
  (e) Unknown email field is rejected by whitelist

Run:
    python -m pytest tests/crm/test_engagement_segment_fields.py -v
"""

import sys
import os
import unittest

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


class TestEmailEngagementSegmentFields(unittest.TestCase):

    # ── (a) last_email_opened_at IS NULL ─────────────────────────────────────

    def test_a_last_email_opened_at_is_null(self):
        """
        'last_email_opened_at IS NULL' must compile to a clause with no bind param.
        Useful for finding users who have never opened an email.
        """
        rule = {"field": "last_email_opened_at", "operator": "IS NULL", "value": None}
        where_clause, params = compile_rules(rule, "user")

        self.assertIn("last_email_opened_at", where_clause)
        self.assertIn("IS NULL", where_clause)
        # IS NULL takes no bind parameter
        self.assertEqual(params, {})

    # ── (b) emails_opened_30d > 5 ─────────────────────────────────────────────

    def test_b_emails_opened_30d_gt(self):
        """
        'emails_opened_30d > 5' must compile to SQL with one bind param = 5.
        """
        rule = {"field": "emails_opened_30d", "operator": ">", "value": 5}
        where_clause, params = compile_rules(rule, "user")

        self.assertIn("emails_opened_30d", where_clause)
        self.assertIn(">", where_clause)
        self.assertEqual(len(params), 1)
        self.assertEqual(list(params.values())[0], 5)

    # ── (c) Org-scope email fields ────────────────────────────────────────────

    def test_c_org_email_fields_compile(self):
        """
        org_emails_received_30d, org_emails_opened_30d, org_emails_clicked_30d
        and org_last_email_opened_at must all compile in the 'organization' scope.
        """
        fields = [
            ("org_emails_received_30d",  ">",        3),
            ("org_emails_opened_30d",    ">=",       1),
            ("org_emails_clicked_30d",   "=",        0),
            ("org_last_email_opened_at", "IS NULL",  None),
        ]
        for field, op, value in fields:
            with self.subTest(field=field, operator=op):
                rule = {"field": field, "operator": op, "value": value}
                where_clause, params = compile_rules(rule, "organization")
                self.assertIn(field, where_clause)
                self.assertIn(op, where_clause)

    # ── (d) IS NOT NULL also works ────────────────────────────────────────────

    def test_d_is_not_null(self):
        """
        'last_email_received_at IS NOT NULL' must compile without a bind param.
        """
        rule = {"field": "last_email_received_at", "operator": "IS NOT NULL", "value": None}
        where_clause, params = compile_rules(rule, "user")

        self.assertIn("last_email_received_at", where_clause)
        self.assertIn("IS NOT NULL", where_clause)
        self.assertEqual(params, {})

    # ── (e) Unknown email field rejected ────────────────────────────────────

    def test_e_unknown_email_field_rejected(self):
        """
        A field not in ALLOWED_FIELDS (e.g. 'email_open_rate_30d') must raise
        BadRequestException rather than executing partial SQL.
        """
        rule = {"field": "email_open_rate_30d", "operator": ">", "value": 0.1}
        with self.assertRaises(BadRequestException):
            compile_rules(rule, "user")

    # ── Field registry includes new email fields ──────────────────────────────

    def test_f_registry_contains_email_fields(self):
        """
        get_field_registry() must expose the 5 user email fields and
        4 org email fields added in Sprint 4.
        """
        registry = get_field_registry()
        user_names = {f['name'] for f in registry['userFields']}
        org_names  = {f['name'] for f in registry['organizationFields']}

        expected_user = {
            'emails_received_30d', 'emails_opened_30d', 'emails_clicked_30d',
            'last_email_received_at', 'last_email_opened_at',
        }
        expected_org = {
            'org_emails_received_30d', 'org_emails_opened_30d',
            'org_emails_clicked_30d', 'org_last_email_opened_at',
        }

        for f in expected_user:
            self.assertIn(f, user_names, f"Missing user field: {f}")
        for f in expected_org:
            self.assertIn(f, org_names, f"Missing org field: {f}")

    # ── IS NULL / IS NOT NULL in registry operators ───────────────────────────

    def test_g_datetime_fields_expose_null_operators(self):
        """
        Datetime email fields must list 'IS NULL' and 'IS NOT NULL' as valid operators
        so the FE rule builder can render them.
        """
        registry = get_field_registry()
        dt_user_fields = [
            f for f in registry['userFields']
            if f['name'] in ('last_email_opened_at', 'last_email_received_at')
        ]
        for f in dt_user_fields:
            with self.subTest(field=f['name']):
                self.assertIn('IS NULL', f['operators'])
                self.assertIn('IS NOT NULL', f['operators'])


if __name__ == '__main__':
    unittest.main()
