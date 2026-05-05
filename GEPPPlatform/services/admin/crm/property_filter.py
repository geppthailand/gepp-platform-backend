"""
CRM property filter — in-memory matcher for trigger campaign property_filters.

Public API:
    matches(event_properties: dict, filter_spec: dict) -> bool

Filter spec shapes
------------------
Leaf (single field check):
    {"key": "amount", "op": "eq",       "value": 100}
    {"key": "amount", "op": "neq",      "value": 100}
    {"key": "amount", "op": "gt",       "value": 100}
    {"key": "amount", "op": "lt",       "value": 100}
    {"key": "amount", "op": "gte",      "value": 100}
    {"key": "amount", "op": "lte",      "value": 100}
    {"key": "cat",    "op": "in",       "value": ["A", "B"]}
    {"key": "cat",    "op": "not_in",   "value": ["A", "B"]}
    {"key": "tags",   "op": "contains", "value": "vip"}     # list contains element
    {"key": "amount", "op": "exists"}                       # key is present (any value)

Combinators:
    {"and": [<filter1>, <filter2>, ...]}
    {"or":  [<filter1>, <filter2>, ...]}

Backward-compat shorthand:
    {"key": "value", ...}  plain dict without "op" key → treated as AND of eq checks.
    e.g. {"source": "web"} is equivalent to {"and": [{"key": "source", "op": "eq", "value": "web"}]}

Usage in campaign_scheduler.tick:
    from .property_filter import matches
    if not matches(event.properties, campaign.trigger_config["property_filters"]):
        continue
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Supported leaf operators
_LEAF_OPS = frozenset({"eq", "neq", "gt", "lt", "gte", "lte", "in", "not_in", "contains", "exists"})


def matches(event_properties: dict, filter_spec: dict) -> bool:
    """
    Evaluate *filter_spec* against *event_properties*.

    Returns True when the spec matches, False otherwise.
    On any type error or unexpected structure, returns False and logs a warning
    (never raises — a mis-configured filter should not crash the scheduler).
    """
    if not filter_spec:
        return True
    if not isinstance(event_properties, dict):
        event_properties = {}

    try:
        return _eval(event_properties, filter_spec)
    except Exception as exc:  # pragma: no cover
        logger.warning("property_filter: unexpected error evaluating spec=%r: %s", filter_spec, exc)
        return False


# ─── Internal evaluator ────────────────────────────────────────────────────────

def _eval(props: dict, spec: dict) -> bool:
    """Recursively evaluate one node of the filter spec tree."""

    # ── Combinator nodes ─────────────────────────────────────────────────────
    if "and" in spec:
        children = spec["and"]
        if not isinstance(children, list):
            logger.warning("property_filter: 'and' value must be a list, got %r", children)
            return False
        return all(_eval(props, child) for child in children)

    if "or" in spec:
        children = spec["or"]
        if not isinstance(children, list):
            logger.warning("property_filter: 'or' value must be a list, got %r", children)
            return False
        return any(_eval(props, child) for child in children)

    # ── Leaf node with explicit 'key' + 'op' ────────────────────────────────
    if "key" in spec and "op" in spec:
        return _eval_leaf(props, spec)

    # ── Backward-compat shorthand: plain key→value dict (no 'op') ───────────
    # {"source": "web", "tier": "gold"}
    # Treated as AND-eq over all pairs.
    if "key" not in spec and "op" not in spec and "and" not in spec and "or" not in spec:
        return all(
            _eval_leaf(props, {"key": k, "op": "eq", "value": v})
            for k, v in spec.items()
        )

    # Leaf node with 'key' but no 'op' — treat as exists check
    if "key" in spec and "op" not in spec:
        return _eval_leaf(props, {**spec, "op": "exists"})

    logger.warning("property_filter: unrecognised spec shape: %r", spec)
    return False


def _eval_leaf(props: dict, spec: dict) -> bool:
    """Evaluate a single-field leaf against *props*."""
    key = spec.get("key")
    op  = spec.get("op")
    expected = spec.get("value")

    if not key or op not in _LEAF_OPS:
        logger.warning("property_filter: invalid leaf op=%r key=%r", op, key)
        return False

    # ── exists ───────────────────────────────────────────────────────────────
    if op == "exists":
        return key in props

    # ── key must be present for all other ops ────────────────────────────────
    if key not in props:
        return False

    actual = props[key]

    # ── equality / inequality ────────────────────────────────────────────────
    if op == "eq":
        return _coerce_eq(actual, expected)

    if op == "neq":
        return not _coerce_eq(actual, expected)

    # ── numeric comparisons ──────────────────────────────────────────────────
    if op in ("gt", "lt", "gte", "lte"):
        try:
            a = float(actual)
            e = float(expected)
        except (TypeError, ValueError):
            logger.debug(
                "property_filter: cannot compare key=%r actual=%r expected=%r op=%s",
                key, actual, expected, op,
            )
            return False
        if op == "gt":  return a > e
        if op == "lt":  return a < e
        if op == "gte": return a >= e
        if op == "lte": return a <= e

    # ── set membership ───────────────────────────────────────────────────────
    if op == "in":
        if not isinstance(expected, list):
            expected = [expected]
        return any(_coerce_eq(actual, v) for v in expected)

    if op == "not_in":
        if not isinstance(expected, list):
            expected = [expected]
        return not any(_coerce_eq(actual, v) for v in expected)

    # ── list contains element ────────────────────────────────────────────────
    if op == "contains":
        if isinstance(actual, list):
            return any(_coerce_eq(item, expected) for item in actual)
        # Substring match for string values
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        return False

    return False  # unreachable given _LEAF_OPS guard above


def _coerce_eq(actual: Any, expected: Any) -> bool:
    """
    Equality comparison with light type coercion:
    - numeric strings vs numbers are compared by value
    - everything else falls back to ==
    """
    if actual == expected:
        return True
    # Try numeric coercion
    try:
        return float(actual) == float(expected)
    except (TypeError, ValueError):
        pass
    # String coercion (e.g. True vs "true")
    return str(actual).lower() == str(expected).lower()
