"""What makes a location a collection point, and which tank a weighing feeds (085).

A collection point ("ถัง") is a place material is gathered AT before being
weighed OUT again. Getting the predicate wrong is expensive in both directions:

  • too loose — a scrap dealer classified as a tank, so the leg into it is
    marked "delivered" instead of carrying its disposal method, and the site's
    real outcome silently disappears from the recycling rate;
  • too tight — a real waste room not recognised, so tenant legs never clear,
    the room's balance is never shown, and the material is counted twice.

The tank a weighing feeds is resolved the same way: explicit ห้องขยะ binding
first, then the nearest ผู้คัดแยก station above it. Deliberately NOT the
weigher's membership — that node and the sorter's station can be different
places, and then inflow and outflow accrue to different tanks and never meet.
"""

import pytest

from GEPPPlatform.services.cores.traceability.collection_points import (
    collection_point_ids,
    is_collection_point,
)
from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Db:
    """Answers the two binding SELECTs by their SQL content."""

    def __init__(self, waste_rooms=(), sorter_stations=(), explode=None):
        self.waste_rooms = list(waste_rooms)
        self.sorter_stations = list(sorter_stations)
        self.explode = explode  # 'waste_room' | 'sorter' | 'all'

    def execute(self, statement, params=None):
        sql = str(statement)
        if "waste_room_location_id" in sql:
            if self.explode in ("waste_room", "all"):
                raise RuntimeError("column does not exist")
            return _Rows([(x,) for x in self.waste_rooms])
        if "sorter_location_id" in sql:
            if self.explode in ("sorter", "all"):
                raise RuntimeError("column does not exist")
            return _Rows([(x,) for x in self.sorter_stations])
        return _Rows([])


# ── The predicate ───────────────────────────────────────────────────────────

def test_a_waste_room_target_is_a_collection_point():
    db = _Db(waste_rooms=[21111])
    assert is_collection_point(db, 21111, 1) is True


def test_a_sorter_station_is_a_collection_point():
    """The zero-configuration path: binding a ผู้คัดแยก is enough."""
    db = _Db(sorter_stations=[21111])
    assert is_collection_point(db, 21111, 1) is True


def test_an_ordinary_destination_is_not_a_collection_point():
    """A scrap dealer must keep its disposal method, or the site's only measured
    outcome is replaced by a hand-over that never resolves."""
    db = _Db(waste_rooms=[21111], sorter_stations=[21111])
    assert is_collection_point(db, 21105, 1) is False


def test_a_batch_is_answered_in_one_pass():
    """One weigh-out can feed a dealer, a landfill and another room at once."""
    db = _Db(waste_rooms=[21111], sorter_stations=[21112])
    assert collection_point_ids(db, 1, {21105, 21111, 21112, 21106}) == {21111, 21112}


def test_candidates_are_never_widened_by_the_lookup():
    """Callers pass the destinations in flight; the answer must be a subset."""
    db = _Db(waste_rooms=[21111, 21999], sorter_stations=[21888])
    assert collection_point_ids(db, 1, {21111}) == {21111}


def test_no_organization_means_no_collection_points():
    assert collection_point_ids(_Db(waste_rooms=[1]), None, {1}) == set()
    assert is_collection_point(_Db(waste_rooms=[1]), 1, None) is False


def test_an_empty_candidate_set_short_circuits():
    assert collection_point_ids(_Db(waste_rooms=[1]), 1, []) == set()


def test_unreadable_candidates_are_dropped_not_crashed():
    db = _Db(waste_rooms=[21111])
    assert collection_point_ids(db, 1, [None, "abc", 21111]) == {21111}


# ── Degrading: a missing column must never fail the caller's write ──────────

def test_one_missing_binding_column_does_not_hide_the_other():
    """Migrations 079 and 081 landed separately; the reads degrade separately."""
    db = _Db(waste_rooms=[21111], sorter_stations=[21112], explode="sorter")
    assert collection_point_ids(db, 1, {21111, 21112}) == {21111}


def test_both_columns_missing_degrades_to_no_collection_points():
    """Pre-085 behaviour exactly: nothing is a tank, nothing is flagged."""
    db = _Db(waste_rooms=[21111], explode="all")
    assert collection_point_ids(db, 1, {21111}) == set()


# ── Which tank a weighing feeds ─────────────────────────────────────────────

class _SetupRow:
    def __init__(self, root_nodes):
        self.root_nodes = root_nodes


class _Q:
    def __init__(self, single=None):
        self._single = single

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def first(self):
        return self._single


class _TankDb(_Db):
    def __init__(self, setup=None, **kw):
        super().__init__(**kw)
        self._setup = setup

    def query(self, *_a, **_k):
        return _Q(single=self._setup)


# Branch 1 > Building 1 > Floor 2 > Room 1 — the shape the dev org has.
TREE = [{'nodeId': 21090, 'children': [
            {'nodeId': 21091, 'children': [
                {'nodeId': 21092, 'children': [
                    {'nodeId': 21093, 'children': []}]}]}]}]


def _svc(db):
    svc = TransactionService.__new__(TransactionService)
    svc.db = db
    return svc


def test_the_nearest_sorter_station_above_the_origin_wins():
    """ผู้เช่า → ชั้น 2 → ปลายทาง: the floor sorts, so the floor is the tank."""
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[21092])
    assert _svc(db)._sorter_station_tank(21093, 1) == 21092


def test_a_station_on_the_building_reaches_a_room_several_levels_below():
    """ผู้เช่า → ตึก → ปลายทาง."""
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[21091])
    assert _svc(db)._sorter_station_tank(21093, 1) == 21091


def test_the_closest_station_beats_a_further_one():
    """A floor that sorts for itself must not have its material booked into the
    building's tank, which would leave one balance stuck high and one negative."""
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[21091, 21092])
    assert _svc(db)._sorter_station_tank(21093, 1) == 21092


def test_a_location_that_sorts_for_itself_is_its_own_tank():
    """room1 → ปลายทาง, with no tenants: the scale point IS the tank, and the
    weighing creates no hop because the material is already there."""
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[21093])
    assert _svc(db)._sorter_station_tank(21093, 1) == 21093


def test_no_station_anywhere_above_means_no_tank():
    """Fails visibly — the card stays in "waiting to ship" as it does today —
    rather than inventing a tank nobody weighs out of."""
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[])
    assert _svc(db)._sorter_station_tank(21093, 1) is None


def test_a_station_on_a_sibling_branch_is_not_used():
    """Only the origin's own ancestor chain counts."""
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[99999])
    assert _svc(db)._sorter_station_tank(21093, 1) is None


def test_a_missing_binding_column_falls_back_to_no_tank():
    db = _TankDb(setup=_SetupRow(TREE), explode="sorter")
    assert _svc(db)._sorter_station_tank(21093, 1) is None


def test_a_location_outside_the_chart_still_checks_its_own_row():
    """No ancestors resolvable, but the location itself may be the station."""
    db = _TankDb(setup=_SetupRow([]), sorter_stations=[21093])
    assert _svc(db)._sorter_station_tank(21093, 1) == 21093


@pytest.mark.parametrize("bad_origin", [None, 0])
def test_no_origin_means_no_tank(bad_origin):
    db = _TankDb(setup=_SetupRow(TREE), sorter_stations=[21091])
    assert _svc(db)._sorter_station_tank(bad_origin, 1) is None
