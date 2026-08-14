"""Idle carry-over runs on every board load, so what it scans and how often matters.

With one traceability pile per weigh-in a busy site accumulates hundreds of piles a
month, and this function used to read every idle transport the organization had ever
recorded — then throw all but last month's away in Python. It also ran twice per board
load, because the board calls it directly and again through the hierarchy builder.
"""

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


class _Query:
    def __init__(self, db, rows):
        self._db = db
        self._rows = rows

    def join(self, *_a, **_k):
        self._db.joins += 1
        return self

    def filter(self, *criteria):
        self._db.filters.extend(str(c) for c in criteria)
        return self

    def order_by(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class _Db:
    """Returns a scripted result per query() call, in order."""

    def __init__(self, results=None):
        self.queries = 0
        self.joins = 0
        self.filters = []
        self.added = []
        self.flushes = 0
        self._results = list(results or [])

    def query(self, *_a, **_k):
        rows = self._results[self.queries] if self.queries < len(self._results) else []
        self.queries += 1
        return _Query(self, rows)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushes += 1


class _Group:
    """A pile from last month whose idle weight needs carrying forward."""

    def __init__(self, origin_id=1, material_id=2, source_transaction_id=None):
        self.id = 100
        self.origin_id = origin_id
        self.material_id = material_id
        self.location_tag_id = None
        self.tenant_id = None
        self.source_transaction_id = source_transaction_id
        self.transaction_carried_over = []
        self.updated_date = None


class _Idle:
    def __init__(self, idle_id):
        self.id = idle_id


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


@pytest.mark.parametrize('idle_count', [1, 5, 50, 400])
def test_query_count_does_not_grow_with_the_number_of_carried_over_piles(idle_count):
    """The target pile used to be looked up once per idle transport — one round trip
    each. At a few piles a month that was invisible; with one pile per weigh-in it is
    hundreds of sequential queries inside a single board load."""
    idles = [(_Idle(i), _Group()) for i in range(idle_count)]
    db = _Db(results=[idles, []])   # 1st query: the idles; 2nd: this month's piles
    TraceabilityService(db)._apply_idle_carry_over(1, 2026, 8)

    assert db.queries == 2, 'exactly one query for idles and one for this month'


def test_two_idles_sharing_a_key_land_in_one_new_pile():
    """The old per-iteration query would find the pile the previous iteration had just
    added. An index has to be kept current or the second idle mints a duplicate."""
    shared = _Group(origin_id=1, material_id=2)
    idles = [(_Idle(1), shared), (_Idle(2), shared)]
    db = _Db(results=[idles, []])
    TraceabilityService(db)._apply_idle_carry_over(1, 2026, 8)

    assert len(db.added) == 1, 'a duplicate pile was created for the same key'
    assert sorted(db.added[0].transaction_carried_over) == [1, 2]


def test_an_existing_pile_this_month_is_reused_not_duplicated():
    existing = _Group(origin_id=1, material_id=2)
    existing.transaction_carried_over = []
    idles = [(_Idle(9), _Group(origin_id=1, material_id=2))]
    db = _Db(results=[idles, [existing]])
    TraceabilityService(db)._apply_idle_carry_over(1, 2026, 8)

    assert db.added == []
    assert existing.transaction_carried_over == [9]


def test_separate_requests_do_not_share_the_guard():
    """The guard lives on the service instance, which is built per request."""
    db_a, db_b = _Db(), _Db()
    TraceabilityService(db_a)._apply_idle_carry_over(1, 2026, 8)
    TraceabilityService(db_b)._apply_idle_carry_over(1, 2026, 8)

    assert db_a.queries == 1 and db_b.queries == 1
