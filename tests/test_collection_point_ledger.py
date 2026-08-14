"""The tank ledger: IN − OUT = what is still in the room (085).

The balance is what JOINS the two halves of a scale-run site. A tenant's chain
ENDS when material reaches the collection point; the point's own weigh-outs
start a new chain to the real destinations. Nothing links them per-kilogram —
and nothing can, because sorting legitimately changes material types (0.37 kg
of bags in, 0.52 kg of bags out once HDPE has been picked out of them). Only
the total weight balances, which is exactly what a ledger models.

These tests drive the Python half — how the three aggregate reads are combined
into cards, and how each one degrades — with a fake session. The SQL itself is
exercised on dev against org 1756; the one predicate pinned here by text is the
idle-root exclusion, because getting it wrong empties a tank nobody shipped
anything out of and there is no other guard against that.
"""

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Loc:
    def __init__(self, loc_id, name):
        self.id = loc_id
        self.display_name = name


class _Query:
    def __init__(self, locations):
        self._locations = locations

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._locations


class _Db:
    """Answers each of the ledger's reads by its SQL content.

    delivered / hopless / weighed-out are the three terms; live_points is what
    the binding tables say TODAY, which is deliberately not how tanks are
    enumerated.
    """

    def __init__(
        self,
        delivered=(),        # [(destination_id, kg)] — legs that arrived here
        hopless=(),          # [(location_id, kg)]    — weighed in here, never left
        weighed_out=(),      # [(origin_id, kg)]      — ผู้คัดแยก shipped it onward
        live_points=(),
        names=None,
        explode=None,        # 'delivered' | 'hopless' | 'out'
    ):
        self.delivered = list(delivered)
        self.hopless = list(hopless)
        self.weighed_out = list(weighed_out)
        self.live_points = list(live_points)
        self.names = names or {}
        self.explode = explode
        self.sql_seen = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql_seen.append(sql)
        if "delivered_to_collection = TRUE" in sql:
            if self.explode == "delivered":
                raise RuntimeError("column does not exist")
            return _Rows(self.delivered)
        if "st.collection_location_id = g.origin_id" in sql:
            if self.explode == "hopless":
                raise RuntimeError("column does not exist")
            return _Rows(self.hopless)
        if "st.is_internal_transfer = TRUE" in sql:
            if self.explode == "out":
                raise RuntimeError("boom")
            return _Rows(self.weighed_out)
        if "waste_room_location_id" in sql or "sorter_location_id" in sql:
            return _Rows([(x,) for x in self.live_points])
        return _Rows([])

    def query(self, *args, **kwargs):
        return _Query([_Loc(i, n) for i, n in self.names.items()])


def _cards(db, org=1756, year=2026, month=8):
    return TraceabilityService(db)._collection_point_balances(org, year, month)


# ── The join ────────────────────────────────────────────────────────────────

def test_what_came_in_minus_what_went_out_is_what_is_left():
    db = _Db(delivered=[(21111, 100.0)], weighed_out=[(21111, 60.0)],
             live_points=[21111], names={21111: "ห้องขยะ A"})
    card, = _cards(db)
    assert (card["in_kg"], card["out_kg"], card["balance_kg"]) == (100.0, 60.0, 40.0)
    assert card["name"] == "ห้องขยะ A"


def test_both_inflow_terms_land_on_the_same_tank():
    """Material dragged in from a tenant AND material weighed straight into the
    room are the same room's stock — counting only one of them would report a
    tank as empty while it is full."""
    db = _Db(delivered=[(21111, 100.0)], hopless=[(21111, 25.0)],
             weighed_out=[(21111, 30.0)], live_points=[21111])
    card, = _cards(db)
    assert card["in_kg"] == 125.0
    assert card["balance_kg"] == 95.0


def test_a_room_that_only_ships_still_gets_a_card():
    """Outflow with no recorded inflow is the loudest possible signal that
    material reaches this room without passing a scale. Hiding the card would
    hide exactly the problem the ledger exists to surface."""
    db = _Db(weighed_out=[(21111, 40.0)], live_points=[21111])
    card, = _cards(db)
    assert card["balance_kg"] == -40.0
    assert card["negative"] is True


def test_rounding_dust_is_not_reported_as_a_negative_balance():
    """Record weight is DECIMAL(15,4) and the web app rounds to 2dp; an exact
    test would flag honest sites."""
    db = _Db(delivered=[(21111, 100.0)], weighed_out=[(21111, 100.004)],
             live_points=[21111])
    card, = _cards(db)
    assert card["negative"] is False


def test_a_tank_whose_sorter_was_unbound_still_reports_its_stock():
    """Tanks are enumerated from STAMPED DATA, not from the live config: a
    station whose ผู้คัดแยก was removed still has kilograms in it, and hiding
    the card would strand them invisibly."""
    db = _Db(delivered=[(21111, 100.0)], live_points=[])
    card, = _cards(db)
    assert card["balance_kg"] == 100.0
    assert card["no_active_sorter"] is True


def test_a_live_tank_is_not_flagged():
    db = _Db(delivered=[(21111, 100.0)], live_points=[21111])
    card, = _cards(db)
    assert card["no_active_sorter"] is False


def test_several_tanks_are_reported_independently():
    """"ทุกจุดที่รับขยะ คือห้องขยะในตัวมันเอง" — no forced flow into one central
    place, so each point keeps its own ledger."""
    db = _Db(delivered=[(21111, 100.0), (21112, 50.0)],
             weighed_out=[(21111, 100.0)], live_points=[21111, 21112])
    by_id = {c["location_id"]: c for c in _cards(db)}
    assert by_id[21111]["balance_kg"] == 0.0
    assert by_id[21112]["balance_kg"] == 50.0


def test_a_named_location_beats_the_placeholder():
    db = _Db(delivered=[(21111, 1.0)], names={})
    card, = _cards(db)
    assert card["name"] == "Location 21111"


# ── Degradation ─────────────────────────────────────────────────────────────

def test_a_site_with_no_tanks_shows_no_cards():
    assert _cards(_Db()) == []


@pytest.mark.parametrize("term", ["delivered", "hopless", "out"])
def test_a_failed_read_reports_nothing_rather_than_a_wrong_balance(term):
    """Pre-085 sessions have neither column. A partial ledger would read as a
    real shortfall — an empty one reads as "not measured", which is true."""
    db = _Db(delivered=[(21111, 100.0)], weighed_out=[(21111, 10.0)], explode=term)
    assert _cards(db) == []


def test_the_month_is_a_cutoff_not_a_bucket():
    """A tank accumulates: stock weighed in during May is still standing there
    in August. The window must be cumulative to the end of the viewed month, or
    every month would open with an empty room."""
    db = _Db(delivered=[(21111, 1.0)])
    _cards(db, year=2026, month=8)
    window_sql = next(s for s in db.sql_seen if "delivered_to_collection = TRUE" in s)
    assert "g.transaction_year < :y" in window_sql
    assert "g.transaction_month <= :m" in window_sql


def test_idle_roots_are_not_treated_as_material_that_left():
    """An idle root is the board's "waiting to ship" placeholder — no
    destination, nothing dispatched, the kilograms are still standing in this
    room. Subtracting it would empty a tank nobody shipped anything out of, and
    it is credited nowhere else: the inflow term needs an arrival AND a
    destination. Pinned by text because the arithmetic lives in SQL."""
    db = _Db(hopless=[(21111, 5.0)])
    _cards(db)
    remainder_sql = next(
        s for s in db.sql_seen if "st.collection_location_id = g.origin_id" in s
    )
    assert "x.status <> 'idle'" in remainder_sql
