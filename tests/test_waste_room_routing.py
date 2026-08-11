"""Resolving the ห้องขยะ a location feeds (migration 080), used to auto-route the first hop.

This lookup decides where material physically goes without a human confirming it, so
every "no answer" path matters as much as the happy one: a wrong id moves waste to the
wrong building, and a raised exception would abort a transaction approval.
"""

import pytest

from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService


class _Row(tuple):
    """Mimics SQLAlchemy's single-column result row."""


class _Db:
    def __init__(self, row=None, explode=False):
        self._row = row
        self._explode = explode
        self.filter_calls = 0

    def query(self, *_args, **_kwargs):
        if self._explode:
            raise RuntimeError('column does not exist')
        return self

    def filter(self, *_args, **_kwargs):
        self.filter_calls += 1
        return self

    def first(self):
        return self._row


def _svc(db):
    svc = TransactionService.__new__(TransactionService)
    svc.db = db
    return svc


def test_returns_the_bound_waste_room():
    assert _svc(_Db(row=_Row((55,))))._waste_room_for_location(10, 1) == 55


@pytest.mark.parametrize('row', [None, _Row((None,)), _Row((0,))])
def test_no_binding_means_material_stays_put(row):
    """None is the answer that preserves today's behaviour, so it must be the answer
    for every shape of 'not set' — including a 0 that would otherwise be a real id."""
    assert _svc(_Db(row=row))._waste_room_for_location(10, 1) is None


@pytest.mark.parametrize('location_id,organization_id', [
    (None, 1), (0, 1), (10, None), (10, 0), (None, None),
])
def test_missing_identifiers_short_circuit_before_any_query(location_id, organization_id):
    db = _Db(row=_Row((55,)))
    assert _svc(db)._waste_room_for_location(location_id, organization_id) is None
    assert db.filter_calls == 0


def test_a_database_error_never_escapes():
    """This runs inside transaction approval. If the column is missing — code deployed
    ahead of migration 081/080 — approval must still succeed, just without routing."""
    assert _svc(_Db(explode=True))._waste_room_for_location(10, 1) is None
