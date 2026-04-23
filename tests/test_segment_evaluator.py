"""
Unit tests for GEPPPlatform/services/admin/crm/segment_evaluator.py

Run from v3/backend/:
    python -m pytest tests/test_segment_evaluator.py -v

Or standalone:
    python -m unittest tests.test_segment_evaluator
"""

import sys
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from GEPPPlatform.services.admin.crm.segment_evaluator import (
    compile_rules,
    get_field_registry,
    ALLOWED_FIELDS,
    ALLOWED_OPERATORS,
)
from GEPPPlatform.exceptions import BadRequestException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def condition(field, operator, value):
    return {"field": field, "operator": operator, "value": value}


def group(op, *conditions):
    return {"op": op, "conditions": list(conditions)}


# ---------------------------------------------------------------------------
# Security tests — SQL injection + operator injection
# ---------------------------------------------------------------------------

class TestSQLInjectionRejected(unittest.TestCase):
    """Hostile inputs must raise BadRequestException before any SQL is produced."""

    def test_sql_injection_field_name(self):
        """'; DROP TABLE users; --  must be rejected as a field name."""
        node = condition("; DROP TABLE users; --", "=", 1)
        with self.assertRaises(BadRequestException) as ctx:
            compile_rules(node, "user")
        self.assertIn("field", str(ctx.exception).lower())

    def test_or_injection_as_operator(self):
        """'OR 1=1' must be rejected as an operator."""
        node = condition("days_since_last_login", "OR 1=1", 30)
        with self.assertRaises(BadRequestException) as ctx:
            compile_rules(node, "user")
        self.assertIn("operator", str(ctx.exception).lower())

    def test_union_injection_field(self):
        """'1 UNION SELECT password FROM users' must be rejected."""
        node = condition("1 UNION SELECT password FROM users", "=", "x")
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")

    def test_comment_injection_operator(self):
        """'=/* comment */' must be rejected as an operator."""
        node = condition("days_since_last_login", "=/* comment */", 5)
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")

    def test_unknown_field_for_scope(self):
        """A field valid for 'organization' scope must be rejected for 'user' scope if not in user set."""
        # 'subscription_active' is an organization field, not in user ALLOWED_FIELDS
        node = condition("subscription_active", "=", True)
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")


# ---------------------------------------------------------------------------
# Valid rule compilation tests
# ---------------------------------------------------------------------------

class TestSimpleConditions(unittest.TestCase):
    """Leaf conditions produce correct SQL + bind params."""

    def test_greater_than(self):
        node = condition("days_since_last_login", ">", 30)
        where, params = compile_rules(node, "user")
        self.assertIn("days_since_last_login", where)
        self.assertIn(">", where)
        self.assertIn(":p0", where)
        self.assertEqual(params["p0"], 30)

    def test_equals(self):
        node = condition("activity_tier", "=", "dormant")
        where, params = compile_rules(node, "user")
        self.assertIn("activity_tier", where)
        self.assertIn(":p0", where)
        self.assertEqual(params["p0"], "dormant")

    def test_in_operator(self):
        node = condition("subscription_plan_id", "IN", [1, 2, 3])
        where, params = compile_rules(node, "user")
        self.assertIn("IN", where)
        # Three placeholders
        self.assertIn(":p0", where)
        self.assertIn(":p1", where)
        self.assertIn(":p2", where)
        self.assertEqual(params["p0"], 1)
        self.assertEqual(params["p2"], 3)

    def test_not_in_operator(self):
        node = condition("activity_tier", "NOT IN", ["active"])
        where, params = compile_rules(node, "user")
        self.assertIn("NOT IN", where)

    def test_between_operator(self):
        node = condition("engagement_score", "BETWEEN", [50, 80])
        where, params = compile_rules(node, "user")
        self.assertIn("BETWEEN", where)
        self.assertIn("AND", where)
        vals = list(params.values())
        self.assertIn(50, vals)
        self.assertIn(80, vals)

    def test_between_wrong_value_count(self):
        node = condition("engagement_score", "BETWEEN", [50])  # only 1 value
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")

    def test_in_requires_list(self):
        node = condition("subscription_plan_id", "IN", 1)  # scalar, not list
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")

    def test_org_scope(self):
        node = condition("active_user_count_30d", ">=", 5)
        where, params = compile_rules(node, "organization")
        self.assertIn("active_user_count_30d", where)
        self.assertEqual(params["p0"], 5)


class TestGroupNodes(unittest.TestCase):
    """AND / OR group nodes produce correct SQL structure."""

    def test_and_group(self):
        node = group("AND",
            condition("days_since_last_login", ">", 30),
            condition("activity_tier", "=", "dormant"),
        )
        where, params = compile_rules(node, "user")
        self.assertIn("AND", where)
        self.assertIn("days_since_last_login", where)
        self.assertIn("activity_tier", where)
        self.assertEqual(len(params), 2)

    def test_or_group(self):
        node = group("OR",
            condition("login_count_30d", "=", 0),
            condition("reward_claim_count_30d", ">=", 1),
        )
        where, params = compile_rules(node, "user")
        self.assertIn("OR", where)
        self.assertEqual(len(params), 2)

    def test_invalid_logical_operator(self):
        node = {"op": "XOR", "conditions": [condition("days_since_last_login", ">", 30)]}
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")

    def test_empty_conditions_list(self):
        node = {"op": "AND", "conditions": []}
        with self.assertRaises(BadRequestException):
            compile_rules(node, "user")


class TestNestedThreeLevels(unittest.TestCase):
    """3-level nested AND/OR compiles correctly."""

    def test_3_level_nesting(self):
        """
        (days_since_last_login > 30)
        AND (
            (activity_tier = 'dormant')
            OR (
                (transaction_count_30d = 0)
                AND (reward_claim_count_30d >= 1)
            )
        )
        """
        inner_and = group("AND",
            condition("transaction_count_30d", "=", 0),
            condition("reward_claim_count_30d", ">=", 1),
        )
        middle_or = group("OR",
            condition("activity_tier", "=", "dormant"),
            inner_and,
        )
        root = group("AND",
            condition("days_since_last_login", ">", 30),
            middle_or,
        )

        where, params = compile_rules(root, "user")

        # Check all four conditions appear
        self.assertIn("days_since_last_login", where)
        self.assertIn("activity_tier", where)
        self.assertIn("transaction_count_30d", where)
        self.assertIn("reward_claim_count_30d", where)

        # Check both logical operators appear
        self.assertIn("AND", where)
        self.assertIn("OR", where)

        # Correct number of bind params
        self.assertEqual(len(params), 4)

        # Values are bound correctly
        values = set(params.values())
        self.assertIn(30, values)
        self.assertIn("dormant", values)
        self.assertIn(0, values)
        self.assertIn(1, values)


class TestTypicalMarketerRules(unittest.TestCase):
    """Real-world marketer rule combinations produce correct SQL."""

    def test_inactivity_win_back(self):
        """Classic win-back: dormant users inactive > 30 days."""
        node = group("AND",
            condition("days_since_last_login", ">", 30),
            condition("activity_tier", "=", "dormant"),
        )
        where, params = compile_rules(node, "user")
        self.assertIn(">", where)
        self.assertIn("days_since_last_login", where)
        self.assertIn("activity_tier", where)
        self.assertEqual(params["p0"], 30)
        self.assertEqual(params["p1"], "dormant")

    def test_no_transactions_last_month(self):
        """Users who have not completed any transactions in 30 days."""
        node = condition("transaction_count_30d", "=", 0)
        where, params = compile_rules(node, "user")
        self.assertIn("transaction_count_30d", where)
        self.assertEqual(params["p0"], 0)

    def test_high_value_reward_users(self):
        """Users with high reward claims on a specific plan."""
        node = group("AND",
            condition("reward_claim_count_30d", ">=", 5),
            condition("subscription_plan_id", "IN", [2, 3]),
        )
        where, params = compile_rules(node, "user")
        self.assertIn("reward_claim_count_30d", where)
        self.assertIn("IN", where)

    def test_at_risk_orgs(self):
        """Orgs that are at-risk and have few active users."""
        node = group("AND",
            condition("activity_tier", "=", "at_risk"),
            condition("active_user_count_30d", "<", 3),
        )
        where, params = compile_rules(node, "organization")
        self.assertIn("activity_tier", where)
        self.assertIn("active_user_count_30d", where)

    def test_subscription_expiry_users(self):
        """Users on specific plans with low recent engagement."""
        node = group("AND",
            condition("subscription_plan_id", "IN", [1, 4, 7]),
            condition("login_count_30d", "<=", 1),
        )
        where, params = compile_rules(node, "user")
        self.assertIn("subscription_plan_id", where)
        self.assertIn("login_count_30d", where)


class TestUnknownScope(unittest.TestCase):
    """Unknown scope raises BadRequestException."""

    def test_unknown_scope(self):
        node = condition("days_since_last_login", ">", 0)
        with self.assertRaises(BadRequestException):
            compile_rules(node, "company")


class TestFieldRegistry(unittest.TestCase):
    """get_field_registry() returns the expected structure for the API."""

    def test_has_user_and_org_keys(self):
        registry = get_field_registry()
        self.assertIn("userFields", registry)
        self.assertIn("organizationFields", registry)

    def test_user_fields_is_list(self):
        registry = get_field_registry()
        self.assertIsInstance(registry["userFields"], list)
        self.assertGreater(len(registry["userFields"]), 0)

    def test_each_field_has_name_label_type_operators(self):
        registry = get_field_registry()
        for field_def in registry["userFields"] + registry["organizationFields"]:
            self.assertIn("name",      field_def, f"Missing 'name' in {field_def}")
            self.assertIn("label",     field_def, f"Missing 'label' in {field_def}")
            self.assertIn("type",      field_def, f"Missing 'type' in {field_def}")
            self.assertIn("operators", field_def, f"Missing 'operators' in {field_def}")


if __name__ == "__main__":
    unittest.main()
