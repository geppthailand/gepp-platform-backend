"""
Tests for GEPPPlatform/services/admin/crm/property_filter.py

Run:
    python -m pytest tests/crm/test_property_filter.py -v

All tests are pure Python — no DB, no mocks needed.
"""

import sys
import os
import importlib.util as _ilu
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Isolated loader — avoids GEPPPlatform package chain
# ---------------------------------------------------------------------------

def _load(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load(
    "GEPPPlatform/services/admin/crm/property_filter.py",
    "GEPPPlatform.services.admin.crm.property_filter",
)
matches = _mod.matches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(props, spec, msg=""):
    assert matches(props, spec) is True, f"Expected True for props={props!r}, spec={spec!r}. {msg}"


def no(props, spec, msg=""):
    assert matches(props, spec) is False, f"Expected False for props={props!r}, spec={spec!r}. {msg}"


# ---------------------------------------------------------------------------
# Test: eq operator
# ---------------------------------------------------------------------------

class TestEq(unittest.TestCase):

    def test_eq_match_int(self):
        ok({"amount": 100}, {"key": "amount", "op": "eq", "value": 100})

    def test_eq_match_string(self):
        ok({"category": "A"}, {"key": "category", "op": "eq", "value": "A"})

    def test_eq_no_match(self):
        no({"amount": 99}, {"key": "amount", "op": "eq", "value": 100})

    def test_eq_numeric_coercion(self):
        # "100" string vs 100 int — should match via coercion
        ok({"amount": "100"}, {"key": "amount", "op": "eq", "value": 100})

    def test_eq_bool_coercion(self):
        ok({"active": "true"}, {"key": "active", "op": "eq", "value": True})

    def test_eq_missing_key_no_match(self):
        no({}, {"key": "amount", "op": "eq", "value": 100})


# ---------------------------------------------------------------------------
# Test: neq operator
# ---------------------------------------------------------------------------

class TestNeq(unittest.TestCase):

    def test_neq_different_values(self):
        ok({"amount": 50}, {"key": "amount", "op": "neq", "value": 100})

    def test_neq_same_value(self):
        no({"amount": 100}, {"key": "amount", "op": "neq", "value": 100})

    def test_neq_missing_key(self):
        # missing key → eq returns False → neq returns True? No — missing key returns False for leaf ops
        no({}, {"key": "amount", "op": "neq", "value": 100})


# ---------------------------------------------------------------------------
# Test: gt / lt / gte / lte operators
# ---------------------------------------------------------------------------

class TestNumericComparisons(unittest.TestCase):

    def test_gt_above(self):
        ok({"amount": 150}, {"key": "amount", "op": "gt", "value": 100})

    def test_gt_equal(self):
        no({"amount": 100}, {"key": "amount", "op": "gt", "value": 100})

    def test_gt_below(self):
        no({"amount": 50}, {"key": "amount", "op": "gt", "value": 100})

    def test_lt_below(self):
        ok({"amount": 50}, {"key": "amount", "op": "lt", "value": 100})

    def test_lt_equal(self):
        no({"amount": 100}, {"key": "amount", "op": "lt", "value": 100})

    def test_gte_equal(self):
        ok({"amount": 100}, {"key": "amount", "op": "gte", "value": 100})

    def test_gte_above(self):
        ok({"amount": 101}, {"key": "amount", "op": "gte", "value": 100})

    def test_gte_below(self):
        no({"amount": 99}, {"key": "amount", "op": "gte", "value": 100})

    def test_lte_equal(self):
        ok({"amount": 100}, {"key": "amount", "op": "lte", "value": 100})

    def test_lte_below(self):
        ok({"amount": 0}, {"key": "amount", "op": "lte", "value": 100})

    def test_lte_above(self):
        no({"amount": 101}, {"key": "amount", "op": "lte", "value": 100})

    def test_numeric_string_value(self):
        ok({"amount": "150"}, {"key": "amount", "op": "gt", "value": 100})

    def test_type_mismatch_returns_false(self):
        # Non-numeric value should not raise — just return False
        no({"amount": "not_a_number"}, {"key": "amount", "op": "gt", "value": 100})

    def test_none_value_returns_false(self):
        no({"amount": None}, {"key": "amount", "op": "gt", "value": 0})


# ---------------------------------------------------------------------------
# Test: in / not_in operators
# ---------------------------------------------------------------------------

class TestSetMembership(unittest.TestCase):

    def test_in_match(self):
        ok({"category": "A"}, {"key": "category", "op": "in", "value": ["A", "B", "C"]})

    def test_in_no_match(self):
        no({"category": "D"}, {"key": "category", "op": "in", "value": ["A", "B", "C"]})

    def test_in_single_value_not_list(self):
        # value is scalar, not list — should auto-wrap
        ok({"category": "A"}, {"key": "category", "op": "in", "value": "A"})

    def test_in_numeric(self):
        ok({"score": 2}, {"key": "score", "op": "in", "value": [1, 2, 3]})

    def test_in_missing_key(self):
        no({}, {"key": "category", "op": "in", "value": ["A"]})

    def test_not_in_not_present(self):
        ok({"category": "D"}, {"key": "category", "op": "not_in", "value": ["A", "B"]})

    def test_not_in_present(self):
        no({"category": "A"}, {"key": "category", "op": "not_in", "value": ["A", "B"]})

    def test_not_in_missing_key(self):
        no({}, {"key": "category", "op": "not_in", "value": ["A"]})


# ---------------------------------------------------------------------------
# Test: contains operator
# ---------------------------------------------------------------------------

class TestContains(unittest.TestCase):

    def test_contains_list_element(self):
        ok({"tags": ["vip", "active"]}, {"key": "tags", "op": "contains", "value": "vip"})

    def test_contains_list_element_not_present(self):
        no({"tags": ["active"]}, {"key": "tags", "op": "contains", "value": "vip"})

    def test_contains_empty_list(self):
        no({"tags": []}, {"key": "tags", "op": "contains", "value": "vip"})

    def test_contains_substring(self):
        ok({"label": "hello world"}, {"key": "label", "op": "contains", "value": "world"})

    def test_contains_substring_not_present(self):
        no({"label": "hello"}, {"key": "label", "op": "contains", "value": "world"})

    def test_contains_non_string_type_mismatch(self):
        # numeric value and string expected — not a list, not a string → False
        no({"amount": 100}, {"key": "amount", "op": "contains", "value": "vip"})


# ---------------------------------------------------------------------------
# Test: exists operator
# ---------------------------------------------------------------------------

class TestExists(unittest.TestCase):

    def test_exists_key_present(self):
        ok({"amount": 100}, {"key": "amount", "op": "exists"})

    def test_exists_key_none_value(self):
        # key is present but value is None — still "exists"
        ok({"amount": None}, {"key": "amount", "op": "exists"})

    def test_exists_key_missing(self):
        no({}, {"key": "amount", "op": "exists"})

    def test_exists_empty_string(self):
        ok({"label": ""}, {"key": "label", "op": "exists"})


# ---------------------------------------------------------------------------
# Test: AND combinator
# ---------------------------------------------------------------------------

class TestAndCombinator(unittest.TestCase):

    def test_and_all_match(self):
        ok(
            {"amount": 150, "category": "A"},
            {"and": [
                {"key": "amount", "op": "gt", "value": 100},
                {"key": "category", "op": "eq", "value": "A"},
            ]},
        )

    def test_and_one_fails(self):
        no(
            {"amount": 50, "category": "A"},
            {"and": [
                {"key": "amount", "op": "gt", "value": 100},
                {"key": "category", "op": "eq", "value": "A"},
            ]},
        )

    def test_and_empty_list(self):
        # All of [] → True (vacuously true)
        ok({}, {"and": []})

    def test_and_nested(self):
        ok(
            {"amount": 200, "category": "B", "active": True},
            {"and": [
                {"key": "amount", "op": "gt", "value": 100},
                {"and": [
                    {"key": "category", "op": "in", "value": ["A", "B"]},
                    {"key": "active", "op": "eq", "value": True},
                ]},
            ]},
        )

    def test_and_not_a_list_returns_false(self):
        no({}, {"and": "not-a-list"})


# ---------------------------------------------------------------------------
# Test: OR combinator
# ---------------------------------------------------------------------------

class TestOrCombinator(unittest.TestCase):

    def test_or_first_matches(self):
        ok(
            {"amount": 150},
            {"or": [
                {"key": "amount", "op": "gt", "value": 100},
                {"key": "amount", "op": "lt", "value": 0},
            ]},
        )

    def test_or_second_matches(self):
        ok(
            {"amount": -5},
            {"or": [
                {"key": "amount", "op": "gt", "value": 100},
                {"key": "amount", "op": "lt", "value": 0},
            ]},
        )

    def test_or_none_matches(self):
        no(
            {"amount": 50},
            {"or": [
                {"key": "amount", "op": "gt", "value": 100},
                {"key": "amount", "op": "lt", "value": 0},
            ]},
        )

    def test_or_empty_list(self):
        # Any of [] → False
        no({}, {"or": []})

    def test_or_not_a_list_returns_false(self):
        no({}, {"or": "not-a-list"})


# ---------------------------------------------------------------------------
# Test: backward-compat shorthand
# ---------------------------------------------------------------------------

class TestBackwardCompat(unittest.TestCase):

    def test_plain_dict_eq_match(self):
        ok({"source": "web"}, {"source": "web"})

    def test_plain_dict_eq_no_match(self):
        no({"source": "app"}, {"source": "web"})

    def test_plain_dict_multi_field(self):
        ok(
            {"source": "web", "tier": "gold"},
            {"source": "web", "tier": "gold"},
        )

    def test_plain_dict_multi_field_one_fail(self):
        no(
            {"source": "web", "tier": "silver"},
            {"source": "web", "tier": "gold"},
        )

    def test_plain_dict_missing_key_returns_false(self):
        no({}, {"source": "web"})


# ---------------------------------------------------------------------------
# Test: edge cases / robustness
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):

    def test_empty_spec_always_matches(self):
        ok({"any": "props"}, {})

    def test_none_props_treated_as_empty(self):
        # matches() coerces non-dict props to {}
        no(None, {"key": "amount", "op": "exists"})

    def test_invalid_op_returns_false(self):
        no({"amount": 100}, {"key": "amount", "op": "unknown_op", "value": 1})

    def test_unrecognised_spec_shape_returns_false(self):
        # Has neither key/op nor and/or — hits the backward-compat path
        # which iterates items and calls eq. If the key is not in props → False.
        no({}, {"nonexistent_key": "some_value"})

    def test_deeply_nested_and_or(self):
        spec = {
            "and": [
                {"key": "amount", "op": "gte", "value": 100},
                {"or": [
                    {"key": "category", "op": "eq", "value": "premium"},
                    {"key": "tags", "op": "contains", "value": "vip"},
                ]},
            ]
        }
        ok({"amount": 100, "category": "premium"}, spec)
        ok({"amount": 200, "tags": ["vip", "active"]}, spec)
        no({"amount": 99, "category": "premium"}, spec)
        no({"amount": 100, "category": "basic", "tags": ["normal"]}, spec)

    def test_never_raises_on_bad_input(self):
        # These should all return False without raising
        for bad_spec in [
            {"key": None, "op": "eq", "value": 1},
            {"key": "x", "op": None, "value": 1},
            {"and": None},
            {"or": None},
        ]:
            result = matches({"x": 1}, bad_spec)
            self.assertIsInstance(result, bool)

    def test_list_of_dicts_in_contains(self):
        # JSONB arrays of objects — contains checks each element with coerce_eq
        ok(
            {"items": [{"id": 1}, {"id": 2}]},
            {"key": "items", "op": "contains", "value": {"id": 1}},
        )

    def test_float_comparison(self):
        ok({"score": 99.5}, {"key": "score", "op": "gte", "value": 99.5})
        no({"score": 99.4}, {"key": "score", "op": "gte", "value": 99.5})


if __name__ == "__main__":
    unittest.main()
