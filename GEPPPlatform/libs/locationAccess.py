"""
Location access filtering — the single definition of "what may this user see".

`UserService.resolve_access_scope()` produces the verdict; this module turns it into
a SQLAlchemy predicate. Every read path (transactions, reports, audit, traceability)
must go through `build_visibility_clause()` rather than hand-rolling `origin_id.in_(...)`,
because two definitions of "may see" is exactly how reports leaked once before
(see the docstring on `reports_service._shared_visible_parent_ids`).

Two independent ways a non-owner gets access:

  1. Location membership  → every transaction at that location and all descendants.
  2. Tag/tenant membership → only transactions at that tag/tenant's locations
     (+ descendants) that actually carry the matching `location_tag_id` / `tenant_id`,
     within the tag/tenant's date window.

An untagged transaction at a location the user only reaches via a tag is NOT visible
to them — nor is one carrying somebody else's tag.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_, or_, false


def _window_end(end_date: Any) -> Any:
    """
    Make an end_date inclusive of its whole day.

    The tag/tenant date range comes from a date picker, so `end_date` arrives at
    midnight. Comparing `transaction_date <= 2026-06-30 00:00` would silently drop
    everything logged during 30 June. When the value has no time component, roll it
    forward a day so the comparison covers the full day (still sargable, unlike
    wrapping the column in `date()`).
    """
    if isinstance(end_date, datetime) and (
        end_date.hour == 0 and end_date.minute == 0
        and end_date.second == 0 and end_date.microsecond == 0
    ):
        return end_date + timedelta(days=1) - timedelta(microseconds=1)
    return end_date


def build_visibility_clause(
    scope: Dict[str, Any],
    origin_col,
    tag_col,
    tenant_col,
    date_col=None,
):
    """
    Build the visibility predicate for `scope`.

    Args:
        scope:      output of `UserService.resolve_access_scope()`
        origin_col: the origin/location column on the model being filtered
        tag_col:    the `location_tag_id` column
        tenant_col: the `tenant_id` column
        date_col:   optional date expression used to apply each grant's window.
                    Pass `None` to skip windowing (e.g. models with no usable date).

    Returns:
        A SQLAlchemy clause, or `None` when the caller should apply no restriction
        at all (organization owner). Returns `false()` when the user has no access
        to anything — callers must treat `None` and `false()` differently.
    """
    if scope.get('is_owner'):
        return None

    clauses = []

    assigned_ids = scope.get('assigned_ids') or set()
    if assigned_ids:
        clauses.append(origin_col.in_(list(assigned_ids)))

    for grant in scope.get('scoped_grants') or []:
        location_ids = grant.get('location_ids') or set()
        if not location_ids:
            continue

        col = tag_col if grant.get('kind') == 'tag' else tenant_col
        conds = [col == grant['id'], origin_col.in_(list(location_ids))]

        if date_col is not None:
            if grant.get('start_date'):
                conds.append(date_col >= grant['start_date'])
            if grant.get('end_date'):
                conds.append(date_col <= _window_end(grant['end_date']))

        clauses.append(and_(*conds))

    if not clauses:
        return false()
    return or_(*clauses)


def scope_for_month(scope: Dict[str, Any], year: Any, month: Any) -> Dict[str, Any]:
    """
    Narrow a scope to the grants whose date window overlaps a given calendar month.

    Traceability aggregates by (transaction_year, transaction_month) and has no row-level
    date, so windowing there is month-granular. Resolving the overlap in Python keeps the
    SQL a plain `IN` — no date arithmetic on the group table.

    Returns a shallow copy; the original scope is untouched.
    """
    if scope.get('is_owner'):
        return scope
    try:
        year = int(year)
        month = int(month)
    except (TypeError, ValueError):
        return scope

    month_start = datetime(year, month, 1)
    month_end = datetime(year + (month // 12), (month % 12) + 1, 1) - timedelta(microseconds=1)

    def overlaps(grant):
        start = grant.get('start_date')
        end = grant.get('end_date')
        if start is not None and _strip_tz(start) > month_end:
            return False
        if end is not None and _window_end(_strip_tz(end)) < month_start:
            return False
        return True

    return {
        **scope,
        'scoped_grants': [g for g in (scope.get('scoped_grants') or []) if overlaps(g)],
    }


def _strip_tz(value: Any) -> Any:
    """Drop tzinfo so tz-aware grant dates compare against naive month bounds."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def accessible_location_ids(scope: Dict[str, Any]) -> set:
    """
    Every location the user can reach at all — full access plus tag/tenant-scoped.

    For pickers and filter-option lists. Do NOT use this to filter transactions:
    it drops the tag/tenant dimension, so a scoped location would leak every
    transaction on it. Use `build_visibility_clause()` for row filtering.
    """
    return set(scope.get('assigned_ids') or set()) | set(scope.get('scoped_ids') or set())


def _in_window(grant: Dict[str, Any], when: Any) -> bool:
    """Is `when` inside this grant's [start_date, end_date]? Missing date ⇒ no constraint."""
    if when is None:
        return True
    when = _strip_tz(when)
    start = grant.get('start_date')
    end = grant.get('end_date')
    if start is not None and when < _strip_tz(start):
        return False
    if end is not None and when > _window_end(_strip_tz(end)):
        return False
    return True


def grant_for_write(
    scope: Dict[str, Any],
    origin_id: Any,
    tag_id: Any = None,
    tenant_id: Any = None,
    when: Any = None,
) -> Optional[str]:
    """
    Decide whether the user may write a record at `origin_id` with this tag/tenant.

    Returns None when allowed, otherwise a short reason string for the 403.

      - owner, or origin fully assigned → any tag/tenant (or none)
      - origin only reachable via tag/tenant → the payload MUST carry a matching one.
        A bare origin is rejected: the author could not see the record afterwards.

    `when` is the record's own date (not "now"), checked against the grant's window for
    the same reason: the read filter matches on transaction_date, so accepting a write
    outside the window would create a record invisible to its author. Back-dating into
    a closed window stays legal — that is the case the window is FOR.
    """
    if scope.get('is_owner'):
        return None

    try:
        origin_id = int(origin_id)
    except (TypeError, ValueError):
        return 'Invalid origin location'

    if origin_id in (scope.get('assigned_ids') or set()):
        return None

    allowed = (scope.get('scoped_by_location') or {}).get(origin_id)
    if not allowed:
        return 'You do not have access to this location'

    def _as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    tag_id = _as_int(tag_id)
    tenant_id = _as_int(tenant_id)

    if tag_id is None and tenant_id is None:
        return 'A tag or tenant is required for this location'

    matched = False
    for grant in (scope.get('scoped_grants') or []):
        is_match = (
            (grant['kind'] == 'tag' and tag_id is not None and grant['id'] == tag_id)
            or (grant['kind'] == 'tenant' and tenant_id is not None and grant['id'] == tenant_id)
        )
        if not is_match or origin_id not in (grant.get('location_ids') or set()):
            continue
        matched = True
        if _in_window(grant, when):
            return None

    if matched:
        return 'The selected tag or tenant is not active for this date'
    return 'You are not a member of the selected tag or tenant'
