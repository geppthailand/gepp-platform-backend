"""A per-weigh-in pile must be dispatched whole, and debug routes must not be live in prod.

Both guards added after review found that migration 082's discriminator on its own
guarantees nothing: `create_transport_transactions` still accepts any number of root
legs of any weight, and `_recalculate_absolute_percentage` divides by the sum of those
legs — so dispatching 40 kg of a 100 kg pile is still stamped 100%, and the other 60 kg
becomes unreachable because a pile with a transport leaves the "waiting to ship" column.
"""

import os

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService
from GEPPPlatform.services.debug.debug_handlers import _debug_routes_enabled


class _Group:
    def __init__(self, group_id=1, source_transaction_id=None):
        self.id = group_id
        self.source_transaction_id = source_transaction_id


class _NoRootsDb:
    """No root legs exist yet, so only the weights under test count."""

    def query(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return []


def _svc(pile_weight):
    svc = TraceabilityService(_NoRootsDb())
    svc._pile_weight_kg = lambda _group: pile_weight
    return svc


# --------------------------------------------------------------------------
# The guard never touches a pile that predates the scale
# --------------------------------------------------------------------------

@pytest.mark.parametrize('weights', [[40], [40, 30], [999], []])
def test_monthly_piles_are_left_completely_alone(weights):
    """source_transaction_id is NULL on every pre-existing row — this is the whole
    reason the guard can ship without measuring anyone's data first."""
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=None), weights) is None


# --------------------------------------------------------------------------
# A scale pile goes out whole or not at all
# --------------------------------------------------------------------------

def test_whole_pile_in_one_leg_is_allowed():
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [100.0]) is None


def test_whole_pile_split_across_several_destinations_is_allowed():
    """Splitting a pile between two recyclers is fine — leaving some behind is not."""
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [60.0, 40.0]) is None


def test_under_dispatch_is_rejected():
    svc = _svc(pile_weight=100.0)
    msg = svc._reject_partial_dispatch(_Group(source_transaction_id=900), [40.0])
    assert msg is not None
    assert '40.00' in msg and '100.00' in msg


def test_over_dispatch_is_rejected():
    """Nothing server-side checked this before, in either direction."""
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [140.0]) is not None


def test_two_legs_that_still_leave_a_remainder_are_rejected():
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [40.0, 30.0]) is not None


@pytest.mark.parametrize('dispatched', [99.995, 100.005, 100.01, 99.99])
def test_rounding_noise_is_tolerated(dispatched):
    """Records are DECIMAL(15,4) and the web app rounds to 2dp; an exact test would
    reject legitimate whole-pile dispatches."""
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [dispatched]) is None


@pytest.mark.parametrize('dispatched', [99.9, 100.1])
def test_a_real_difference_is_not_tolerated(dispatched):
    svc = _svc(pile_weight=100.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [dispatched]) is not None


def test_empty_pile_is_not_blocked():
    """A pile whose records are all unapproved weighs 0; blocking it would strand it."""
    svc = _svc(pile_weight=0.0)
    assert svc._reject_partial_dispatch(_Group(source_transaction_id=900), [10.0]) is None


# --------------------------------------------------------------------------
# Debug routes fail closed
# --------------------------------------------------------------------------

@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv('AWS_LAMBDA_FUNCTION_NAME', raising=False)
    monkeypatch.delenv('ENABLE_DEBUG_ROUTES', raising=False)
    return monkeypatch


def test_debug_routes_are_on_outside_lambda(clean_env):
    """Local development and this test suite keep working with no configuration."""
    assert _debug_routes_enabled() is True


def test_debug_routes_are_off_in_a_deployed_function(clean_env):
    """One of these routes merges traceability groups and soft-deletes the losers,
    which cannot be undone without a restore. It was reachable by any authenticated
    user in production."""
    clean_env.setenv('AWS_LAMBDA_FUNCTION_NAME', 'gepp-platform-api')
    assert _debug_routes_enabled() is False


@pytest.mark.parametrize('value', ['1', 'true', 'TRUE', 'yes', 'on'])
def test_debug_routes_can_be_opened_deliberately(clean_env, value):
    clean_env.setenv('AWS_LAMBDA_FUNCTION_NAME', 'gepp-platform-api')
    clean_env.setenv('ENABLE_DEBUG_ROUTES', value)
    assert _debug_routes_enabled() is True


@pytest.mark.parametrize('value', ['0', 'false', 'no', '', '   '])
def test_a_non_affirmative_flag_does_not_open_them(clean_env, value):
    clean_env.setenv('AWS_LAMBDA_FUNCTION_NAME', 'gepp-platform-api')
    clean_env.setenv('ENABLE_DEBUG_ROUTES', value)
    assert _debug_routes_enabled() is False
