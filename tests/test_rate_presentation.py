"""ใครเห็นเลข % รีไซเคิลแบบไหน — นโยบายทั้งหมดอยู่ในฟังก์ชันเดียว (086).

The first cut of the two-scope report suppressed the rate in EVERY narrowed
scope, for every organization. That broke a report thousands of pre-scale
organizations already rely on: their filtered views lost a number that was
never wrong for them, because nothing of theirs ever crosses into a shared
room. The policy is now data-driven — suppression only where the tank model
actually bites — and lives in resolve_rate_presentation so it can be pinned
here without a database.

The three-way rule, one case per test below:

  scope never meets a tank      → the pre-tank ESTIMATE (labelled 'estimate')
  org-wide scope of a tank site → MEASURED ('outcome') + estimate for a toggle
  narrowed scope meeting a tank → None ('unavailable')
"""

import pytest

from GEPPPlatform.services.cores.reports.reports_handlers import resolve_rate_presentation


# ── Pre-scale organizations: nothing may move ────────────────────────────────

def test_a_legacy_org_keeps_its_number_in_the_org_view():
    rate, basis, toggle = resolve_rate_presentation(True, False, 91.7, 91.7)
    assert rate == 91.7
    assert basis == 'estimate'
    assert toggle is None, "no toggle: there is no second number to flip to"


def test_a_legacy_org_keeps_its_number_when_filtering():
    """The regression this policy exists to fix: a filtered view in an
    organization with no tanks lost its rate for a reason that does not apply
    to it. Narrowed scope + no tank contact = the old number, full stop."""
    rate, basis, toggle = resolve_rate_presentation(False, False, 88.2, 88.2)
    assert rate == 88.2
    assert basis == 'estimate'
    assert toggle is None


# ── Scale sites, org-wide: measured leads, the old number stays visible ─────

def test_a_tank_site_reports_the_measured_rate_org_wide():
    rate, basis, toggle = resolve_rate_presentation(True, True, 0.0, 92.0)
    assert rate == 0.0
    assert basis == 'outcome'


def test_the_estimate_rides_along_for_the_view_toggle():
    """People who watched ~92% for years and now see 0% deserve to flip to the
    old basis and understand the drop — as a view, not as a setting that
    changes the official figure."""
    _, _, toggle = resolve_rate_presentation(True, True, 0.0, 92.0)
    assert toggle == 92.0


# ── Scale sites, narrowed scopes ─────────────────────────────────────────────

def test_a_filtered_corner_the_tanks_never_touch_keeps_the_estimate():
    """A branch with no scale inside a scale-running org: its chains are as
    complete as they ever were, so its old number is as right as it ever was."""
    rate, basis, toggle = resolve_rate_presentation(False, False, 75.0, 75.0)
    assert rate == 75.0
    assert basis == 'estimate'
    assert toggle is None


def test_a_scope_whose_material_enters_a_tank_gets_no_rate():
    """One tenant's deliveries measured against a shared room's outcomes is a
    wrong number, not a conservative one."""
    rate, basis, toggle = resolve_rate_presentation(False, True, 40.0, 92.0)
    assert rate is None
    assert basis == 'unavailable'
    assert toggle is None


# ── Degenerate corners ───────────────────────────────────────────────────────

def test_zero_is_a_real_answer_not_a_missing_one():
    """0.0 must survive the trip — a falsy-check would turn a measured zero
    into 'unavailable', hiding exactly the number that matters most."""
    rate, basis, _ = resolve_rate_presentation(True, True, 0.0, 0.0)
    assert rate == 0.0
    assert basis == 'outcome'


@pytest.mark.parametrize("outcome_scope", [True, False])
def test_no_tank_contact_never_suppresses(outcome_scope):
    rate, basis, _ = resolve_rate_presentation(outcome_scope, False, 50.0, 50.0)
    assert rate is not None
    assert basis == 'estimate'
