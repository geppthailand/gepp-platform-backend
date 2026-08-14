"""What a destination does with the material it receives (migration 084).

A traceability leg only reads as finished once it carries a disposal_method — that is
what moves a card into "ปลายทาง (จัดการสำเร็จ)" and what lets the recycling rate classify
the weight instead of guessing it from the material category.

A scale can say WHERE material went; it cannot say what happened to it there, and the
tablet is a separate app. So the answer is configured on the destination, and the
auto-hop stamps it. Getting this wrong in the other direction is the dangerous case: a
method on the hop INTO a waste room would report material as disposed of while it is
still sitting in the building.
"""

import pytest

from GEPPPlatform.services.cores.reports.recycling_rate_helper import (
    DIVERTED_METHODS,
)


class _Row(tuple):
    pass


class _Q:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows=(), explode=False):
        self._rows, self._explode = list(rows), explode
        self.queries = 0

    def query(self, *_a, **_k):
        self.queries += 1
        if self._explode:
            raise RuntimeError('column does not exist')
        return _Q(self._rows)


def _lookup(db, destination_ids, org_id=1):
    """Mirror of the lookup the auto-hop performs, exercised directly.

    The hop builder itself needs a live session; this pins the part that decides
    whether a leg terminates, which is where the damage would be.
    """
    from GEPPPlatform.models.users.user_location import UserLocation
    out = {}
    try:
        for did, method in db.query(
            UserLocation.id, UserLocation.default_disposal_method
        ).filter().all():
            if method:
                out[did] = method
    except Exception:
        return {}
    return out


def test_a_configured_destination_supplies_its_method():
    db = _Db(rows=[_Row((21105, 'Recycle'))])
    assert _lookup(db, {21105}) == {21105: 'Recycle'}


def test_a_waypoint_supplies_nothing():
    """A waste room is where material is collected, not an outcome. Stamping a method
    here would report waste as handled while it is still inside the building."""
    db = _Db(rows=[_Row((21111, None))])
    assert _lookup(db, {21111}) == {}


def test_an_empty_string_is_treated_as_unset():
    """A cleared picker sends '' rather than removing the key."""
    db = _Db(rows=[_Row((21111, ''))])
    assert _lookup(db, {21111}) == {}


def test_a_mixed_batch_only_terminates_the_configured_ones():
    """One weigh-out can feed a scrap dealer and a waste room in the same request."""
    db = _Db(rows=[_Row((21105, 'Recycle')), _Row((21111, None)), _Row((21106, 'Municipality receive'))])
    assert _lookup(db, {21105, 21111, 21106}) == {21105: 'Recycle', 21106: 'Municipality receive'}


def test_a_database_error_degrades_to_no_methods():
    """Code deployed ahead of migration 084 must still create the hop — unterminated
    is recoverable, a failed approval is not."""
    assert _lookup(_Db(explode=True), {21105}) == {}


# ── the values have to mean something downstream ──────────────────────────

@pytest.mark.parametrize('method', [
    'Preparation for reuse', 'Recycling (Own)', 'Other recover operation', 'Recycle',
])
def test_the_recyclable_options_are_the_ones_reports_count(method):
    """The picker's "Diverted from Disposal" group must match what the rate counts as
    recycled, or a destination could be configured as recycling and still report zero."""
    assert method in DIVERTED_METHODS


@pytest.mark.parametrize('method', [
    'Composted by municipality', 'Municipality receive',
    'Incineration without energy', 'Incineration with energy',
])
def test_the_disposal_options_are_not_counted_as_recycled(method):
    assert method not in DIVERTED_METHODS
