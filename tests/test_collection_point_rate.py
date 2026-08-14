"""The recycling rate when material passes through a collection point (085).

A tenant's kilograms are real at the origin, but their FATE is decided in a
shared sorting room: the pile is opened, re-sorted, and shipped out as different
material entirely. On dev org 1756, 0.37 kg of plastic bags went IN and 0.52 kg
came OUT — more than arrived — because HDPE was picked out of the bags. So the
tenant's own chain cannot say what happened to their waste, and the room's
weigh-outs can.

That leaves exactly one honest arrangement: the tenant's delivered kilograms are
SUPERSEDED (removed from the rate's denominator) and the room's weigh-outs are
counted instead. Get it wrong in either direction and the damage is real —
forget to supersede and every kilogram is counted twice, forget to add the
weigh-outs and the site's only measured outcomes vanish behind a category guess.

These pin the arithmetic. The scenarios are the dev org's real numbers.
"""

import pytest

from GEPPPlatform.services.cores.reports.recycling_rate_helper import (
    compute_recycling_rate,
)


def _leaf(*, weight, method=None, delivered=False, group_total, status="arrived"):
    return {
        "leaf_weight": weight,
        "group_total_weight": group_total,
        "disposal_method": method,
        "delivered": delivered,
        "status": status,
        "absolute_percentage": 100.0,
    }


# ── Legacy behaviour is untouched unless asked for ──────────────────────────

def test_the_flag_is_off_by_default_so_existing_reports_do_not_move():
    """Every caller that has not opted in must get today's numbers exactly."""
    weights = [(10.0, 0.0, 1, 77)]
    leaves = {77: [_leaf(weight=10.0, delivered=True, group_total=10.0)]}
    recyclable, _ghg, total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}
    )
    # Delivered leaf ignored → category fallback on the whole weight, and the
    # denominator is still the full weight. This is what shipped before 085.
    assert (recyclable, total, rate_total) == (10.0, 10.0, 10.0)


def test_a_site_with_no_collection_points_is_unaffected_when_the_flag_is_on():
    """Turning the mechanism on must be a no-op until a tank actually exists."""
    weights = [(10.0, 0.0, 1, 77)]
    leaves = {77: [_leaf(weight=10.0, method="Recycle", group_total=10.0)]}
    recyclable, _ghg, _total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert (recyclable, rate_total) == (10.0, 10.0)


# ── The supersede itself ────────────────────────────────────────────────────

def test_delivered_material_leaves_the_denominator_entirely():
    """The tenant half of the ledger: counted as generated, not as an outcome."""
    weights = [(10.0, 0.0, 1, 77)]
    leaves = {77: [_leaf(weight=10.0, delivered=True, group_total=10.0)]}
    recyclable, _ghg, total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert total == 10.0, "still generated waste"
    assert rate_total == 0.0, "but nothing here to rate"
    assert recyclable == 0.0


def test_delivered_material_is_not_guessed_from_its_category():
    """The failure that motivated 085: a category guess standing in for the
    measurement the sorting room is about to make."""
    weights = [(10.0, 0.0, 1, 77)]  # cat 1 = "recyclable" by the old guess
    leaves = {77: [_leaf(weight=10.0, delivered=True, group_total=10.0)]}
    recyclable, *_ = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert recyclable == 0.0


def test_a_partly_delivered_pile_only_supersedes_the_part_that_went():
    """One weighing can send some material onward and drop the rest at the room."""
    weights = [(10.0, 0.0, 1, 77)]
    leaves = {77: [
        _leaf(weight=6.0, delivered=True, group_total=10.0),
        _leaf(weight=4.0, method="Recycle", group_total=10.0),
    ]}
    recyclable, _ghg, total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert total == 10.0
    assert rate_total == 4.0, "only the 4 kg with a known outcome is rateable"
    assert recyclable == 4.0


# ── The room's own weigh-out is what carries the outcome ────────────────────

def test_the_two_halves_together_report_the_measured_outcome():
    """The whole point, end to end, with dev org 1756's real numbers.

    1.25 kg delivered by tenants (superseded), 0.99 kg weighed back out by the
    ผู้คัดแยก — 0.52 kg recycled, 0.47 kg to the municipality. The site's rate
    must be 0.52/0.99, a measurement; never 1.25 kg of category guessing, and
    never 2.24 kg of both.
    """
    weights = [
        (1.25, 0.0, 1, 77),    # tenants' deliveries
        (0.52, 0.0, 1, 88),    # weighed out to the scrap dealer
        (0.47, 0.0, 2, 99),    # weighed out to the municipality
    ]
    leaves = {
        77: [_leaf(weight=1.25, delivered=True, group_total=1.25)],
        88: [_leaf(weight=0.52, method="Recycle", group_total=0.52)],
        99: [_leaf(weight=0.47, method="Municipality receive", group_total=0.47)],
    }
    completion = {77: 1.0, 88: 1.0, 99: 1.0}
    recyclable, _ghg, _total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, completion, supersede_delivered=True
    )
    assert round(rate_total, 2) == 0.99
    assert round(recyclable, 2) == 0.52
    assert round(recyclable / rate_total * 100, 1) == 52.5


# ── Material sitting in the room with no legs at all ────────────────────────

def test_material_weighed_in_at_the_room_itself_is_superseded_without_legs():
    """Weigh-in AT the collection point creates no hop — the material is already
    where it was going. It has nothing to trace, so it must not be guessed."""
    weights = [(8.0, 0.0, 1, None)]  # no group/leaves at all
    recyclable, _ghg, total, _traced, rate_total = compute_recycling_rate(
        weights, {}, {}, supersede_delivered=True, superseded_by_record={0: 8.0}
    )
    assert total == 8.0
    assert (rate_total, recyclable) == (0.0, 0.0)


def test_only_the_part_that_stayed_in_the_room_is_superseded():
    """A weighing whose records named their own destinations keeps those legs;
    only the remainder is sitting in the room."""
    weights = [(10.0, 0.0, 1, None)]
    recyclable, _ghg, _total, _traced, rate_total = compute_recycling_rate(
        weights, {}, {}, supersede_delivered=True, superseded_by_record={0: 3.0}
    )
    assert rate_total == 7.0
    assert recyclable == 7.0, "the 7 kg that left still falls back to category"


# ── The clamps: a rate above 100% is always a bug ───────────────────────────

def test_an_over_attributed_delivered_leaf_cannot_push_the_rate_over_100():
    """Leaf weights and recorded weights come from different columns, so a leaf
    CAN over-attribute (group_total 0 ⇒ the record takes the whole leaf). The
    clamp order — outcomes first, supersede against what is left — is what keeps
    the numerator inside the denominator."""
    weights = [(5.0, 0.0, 1, 77)]
    leaves = {77: [
        _leaf(weight=3.0, method="Recycle", group_total=0.0),   # → full 3.0
        _leaf(weight=10.0, delivered=True, group_total=0.0),    # → full 10.0 (!)
    ]}
    recyclable, _ghg, _total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert rate_total >= recyclable, "denominator must never fall below numerator"
    assert rate_total >= 3.0, "the measured outcome cannot be superseded away"


def test_a_hopless_marker_larger_than_the_record_is_clamped():
    weights = [(2.0, 0.0, 1, None)]
    _r, _g, total, _t, rate_total = compute_recycling_rate(
        weights, {}, {}, supersede_delivered=True, superseded_by_record={0: 99.0}
    )
    assert total == 2.0
    assert rate_total == 0.0, "clamped to the record, never negative"


def test_superseding_never_makes_the_denominator_negative():
    weights = [(1.0, 0.0, 1, 77), (1.0, 0.0, 1, 77)]
    leaves = {77: [_leaf(weight=50.0, delivered=True, group_total=0.0)]}
    *_rest, rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert rate_total >= 0.0


# ── Completion / the "fully traced" badge ───────────────────────────────────

def test_delivered_material_reads_as_accounted_for_not_as_unfinished():
    """A tenant whose waste reached the room has finished their part. Without
    this a scale site reads as permanently mid-flight and the badge never
    clears, no matter how complete the data is."""
    weights = [(10.0, 0.0, 1, 77)]
    leaves = {77: [_leaf(weight=10.0, delivered=True, group_total=10.0)]}
    *_head, fully_traced, _rate_total = compute_recycling_rate(
        weights, leaves, {77: 1.0}, supersede_delivered=True
    )
    assert fully_traced is True


@pytest.mark.parametrize("method,expected_recyclable", [
    ("Recycle", 0.52),
    ("Recycling (Own)", 0.52),
    ("Municipality receive", 0.0),
    ("Incineration without energy", 0.0),
])
def test_the_weigh_out_method_decides_the_outcome(method, expected_recyclable):
    """The ผู้คัดแยก's destination is what classifies the weight — the tenant's
    material category no longer gets a vote once the material is traced."""
    weights = [(0.52, 0.0, 1, 88)]
    leaves = {88: [_leaf(weight=0.52, method=method, group_total=0.52)]}
    recyclable, *_ = compute_recycling_rate(
        weights, leaves, {88: 1.0}, supersede_delivered=True
    )
    assert round(recyclable, 2) == expected_recyclable


# ─────────────────────────────────────────────────────────────────────
# Regressions found reviewing the first implementation.
# ─────────────────────────────────────────────────────────────────────


def test_an_over_attributed_disposal_leaf_cannot_report_over_100_percent():
    """A leaf can claim more than the record weighs — group_total_weight is 0
    whenever a pile's records were entered by quantity rather than kilograms,
    and then every record takes the WHOLE leaf. The first implementation clamped
    the numerator's weight but not the numerator itself and reported 200%.

    The denominator is therefore built from what was accounted for, the same way
    the numerator is, so the ratio survives any leaf weight.
    """
    weights = [(5.0, 0.0, 1, 7), (5.0, 0.0, 1, 7)]
    leaves = {7: [_leaf(weight=10.0, method="Recycle", group_total=0.0)]}
    recyclable, _ghg, _total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {7: 1.0}, supersede_delivered=True
    )
    assert rate_total > 0
    assert recyclable <= rate_total
    assert recyclable / rate_total * 100 <= 100.0


def test_the_same_holds_with_the_mechanism_switched_off():
    """Legacy callers get the same protection — this was reachable before 085."""
    weights = [(5.0, 0.0, 1, 7)]
    leaves = {7: [_leaf(weight=8.0, method="Recycle", group_total=0.0)]}
    recyclable, _ghg, _total, _traced, rate_total = compute_recycling_rate(
        weights, leaves, {7: 1.0}
    )
    assert recyclable <= rate_total


def test_a_delivered_pile_is_not_badged_fully_traced_for_callers_that_guess():
    """The performance tab shares this helper but does NOT supersede, so for it
    a delivered pile really is 100% category guesswork. Badging it "fully
    traced" would claim a measurement nobody made."""
    weights = [(10.0, 0.0, 1, 7)]
    leaves = {7: [_leaf(weight=10.0, delivered=True, group_total=10.0)]}
    recyclable, _ghg, _total, fully_traced, _rate = compute_recycling_rate(
        weights, leaves, {7: 0.0}
    )
    assert recyclable == 10.0, "still category-guessed for this caller"
    assert fully_traced is False, "and it must say so"


def test_the_same_pile_IS_fully_traced_once_the_room_accounts_for_it():
    """With superseding on, the tenant's part is genuinely finished."""
    weights = [(10.0, 0.0, 1, 7)]
    leaves = {7: [_leaf(weight=10.0, delivered=True, group_total=10.0)]}
    _r, _g, _t, fully_traced, rate_total = compute_recycling_rate(
        weights, leaves, {7: 0.0}, supersede_delivered=True
    )
    assert fully_traced is True
    assert rate_total == 0.0


def test_a_half_finished_pile_is_still_reported_as_incomplete():
    """One leg delivered, one still in transit: not finished, and superseding
    must not paper over that."""
    weights = [(10.0, 0.0, 1, 7)]
    leaves = {7: [
        _leaf(weight=5.0, delivered=True, group_total=10.0),
        _leaf(weight=5.0, group_total=10.0, status="in_transit"),
    ]}
    *_head, fully_traced, _rate_total = compute_recycling_rate(
        weights, leaves, {7: 0.0}, supersede_delivered=True
    )
    assert fully_traced is False
