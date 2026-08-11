"""Idle carry-over runs on every board load, so what it scans and how often matters.

With one traceability pile per weigh-in a busy site accumulates hundreds of piles a
month, and this function used to read every idle transport the organization had ever
recorded — then throw all but last month's away in Python. It also ran twice per board
load, because the board calls it directly and again through the hierarchy builder.
"""

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


class _Query:
    def __init__(self, db):
        self._db = db

    def join(self, *_a, **_k):
        self._db.joins += 1
        return self

    def filter(self, *criteria):
        self._db.filters.extend(str(c) for c in criteria)
        return self

    def all(self):
        return []


class _Db:
    def __init__(self):
        self.queries = 0
        self.joins = 0
        self.filters = []

    def query(self, *_a, **_k):
        self.queries += 1
        return _Query(self)


def test_the_scan_is_bounded_to_the_month_it_can_act_on():
    """Without the month predicate this is a full-history scan that grows forever."""
    db = _Db()
    TraceabilityService(db)._apply_idle_carry_over(1, 2026, 8)

    assert db.joins == 1, 'the group is joined, not fetched in a second pass'
    joined = ' '.join(db.filters)
    assert 'transaction_year' in joined and 'transaction_month' in joined


def test_the_second_call_in_one_request_does_no_work():
    """The board calls this directly and again via the hierarchy builder; the second
    pass can only repeat what the first already did."""
    db = _Db()
    svc = TraceabilityService(db)
    svc._apply_idle_carry_over(1, 2026, 8)
    svc._apply_idle_carry_over(1, 2026, 8)

    assert db.queries == 1


@pytest.mark.parametrize('second', [(1, 2026, 7), (1, 2025, 8), (2, 2026, 8)])
def test_a_different_month_or_organization_is_still_processed(second):
    """The guard is per request-shape, not a blanket 'only once ever' — switching the
    month picker must still carry that month over."""
    db = _Db()
    svc = TraceabilityService(db)
    svc._apply_idle_carry_over(1, 2026, 8)
    svc._apply_idle_carry_over(*second)

    assert db.queries == 2


def test_separate_requests_do_not_share_the_guard():
    """The guard lives on the service instance, which is built per request."""
    db_a, db_b = _Db(), _Db()
    TraceabilityService(db_a)._apply_idle_carry_over(1, 2026, 8)
    TraceabilityService(db_b)._apply_idle_carry_over(1, 2026, 8)

    assert db_a.queries == 1 and db_b.queries == 1
