"""The traceability board's KPI tiles must count each kilogram once.

A ผู้คัดแยก's weigh-out is a real pile with real legs — it is how we know where the
material ended up — but its weight was already reported when the tenant weighed the
same material in. So it is excluded from "how much waste is there" and kept for
"where did it go". Getting that split backwards is invisible on screen: the tiles
still add up, they just describe twice as much waste as exists.
"""

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *_a, **_k):
        return self

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows=(), explode=False):
        self._rows = list(rows)
        self._explode = explode
        self.queries = 0

    def query(self, *_a, **_k):
        self.queries += 1
        if self._explode:
            raise RuntimeError('relation does not exist')
        return _Rows(self._rows)


def _svc(db):
    return TraceabilityService(db)


def test_internal_piles_are_returned_as_strings():
    """Callers compare against ids that have been through JSON, where a pile id may
    arrive as either 7 or "7"."""
    ids = _svc(_Db(rows=[(7,), (9,)]))._internal_transfer_group_ids(1)
    assert ids == {'7', '9'}


def test_no_internal_piles_is_an_empty_set_not_none():
    """The result is used with `in`, so None would raise rather than degrade."""
    assert _svc(_Db(rows=[]))._internal_transfer_group_ids(1) == set()


@pytest.mark.parametrize('organization_id', [None, 0])
def test_missing_organization_skips_the_query_entirely(organization_id):
    db = _Db(rows=[(7,)])
    assert _svc(db)._internal_transfer_group_ids(organization_id) == set()
    assert db.queries == 0


def test_a_database_error_degrades_to_pre_migration_numbers():
    """If the column is missing — code deployed ahead of migration 083 — the board
    must still render with the old totals rather than fail or blank out."""
    assert _svc(_Db(explode=True))._internal_transfer_group_ids(1) == set()
