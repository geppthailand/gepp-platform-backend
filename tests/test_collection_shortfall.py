"""ถังติดลบต้องไม่ไปหักล้างถังที่มีของจริง (086).

A collection point can legitimately go negative: waste is carried into the
room without passing the scale, the room already held stock when the system
was installed, or a weighing was simply wrong. Nothing blocks a ผู้คัดแยก from
recording an over-draw, and nothing should — the material is in front of them,
and a system that refuses the truth teaches people to work around it.

What the system MUST do is report it. Summing balances straight across hid it
twice over: a building holding 10 kg beside one that has shipped 8 kg more than
it ever received reported "2 kg in collection", so neither the stock nor the
discrepancy survived. Stock and shortfall are different facts and are kept as
different numbers — both positive, so neither can quietly erase the other.
"""

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


summarise = TraceabilityService.summarise_collection_balances


def _cp(balance):
    return {"location_id": 1, "balance_kg": balance}


def test_rooms_holding_stock_are_added_up():
    out = summarise([_cp(10.0), _cp(2.5)])
    assert out["in_collection_kg"] == 12.5
    assert out["shortfall_kg"] == 0.0
    assert out["negative_points"] == 0


def test_an_over_drawn_room_is_reported_as_a_positive_shortfall():
    """Reported as 8, not -8: a shortfall is a quantity of missing measurement,
    and a minus sign in front of it invites someone to add it to something."""
    out = summarise([_cp(-8.0)])
    assert out["in_collection_kg"] == 0.0
    assert out["shortfall_kg"] == 8.0
    assert out["negative_points"] == 1


def test_a_shortfall_never_cancels_another_room_s_stock():
    """The whole reason this function exists. 10 kg is standing in one room and
    8 kg cannot be accounted for in another; "2 kg" describes neither."""
    out = summarise([_cp(10.0), _cp(-8.0)])
    assert out["in_collection_kg"] == 10.0
    assert out["shortfall_kg"] == 8.0
    assert out["negative_points"] == 1


def test_several_over_drawn_rooms_are_counted():
    out = summarise([_cp(-1.0), _cp(-2.0), _cp(4.0)])
    assert out["shortfall_kg"] == 3.0
    assert out["negative_points"] == 2
    assert out["in_collection_kg"] == 4.0


# ── Tolerance: DECIMAL(15,4) weights rounded to 2dp must not raise an alarm ──

@pytest.mark.parametrize("balance", [0.004, -0.004, 0.0, -0.01, 0.01])
def test_rounding_dust_is_neither_stock_nor_shortfall(balance):
    out = summarise([_cp(balance)])
    assert out["in_collection_kg"] == 0.0
    assert out["shortfall_kg"] == 0.0
    assert out["negative_points"] == 0


def test_a_real_shortfall_just_past_the_tolerance_is_reported():
    out = summarise([_cp(-0.02)])
    assert out["shortfall_kg"] == 0.02
    assert out["negative_points"] == 1


# ── Degradation ─────────────────────────────────────────────────────────────

def test_no_tanks_reports_zeroes_not_an_error():
    assert summarise([]) == {"in_collection_kg": 0.0, "shortfall_kg": 0.0, "negative_points": 0}


def test_a_row_with_an_unreadable_balance_is_skipped_not_fatal():
    """The ledger read degrades to [] on failure, but a single malformed row must
    not take the whole summary down with it."""
    out = summarise([_cp(5.0), {"location_id": 2, "balance_kg": "nonsense"}, _cp(None)])
    assert out["in_collection_kg"] == 5.0
    assert out["shortfall_kg"] == 0.0
