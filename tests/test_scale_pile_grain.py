"""One weigh-in = one traceability pile, for scale-recorded waste only (migration 082).

A pile is normally one per (origin, material, tag, tenant) per MONTH. Under a scale
that grain loses data: later records are appended into a pile that already has a
transport, and such a pile is hidden from the "waiting to ship" column, so the first
dispatch of the month swallows the rest of that tenant's month.

These tests pin the two decisions that keep piles apart. Get either wrong and two
weigh-ins silently merge back into one — the failure is invisible in the UI, which is
why it is worth a test rather than a comment.
"""

import pytest

from GEPPPlatform.services.cores.iot_devices.auto_approve import (
    SCALE_TRANSACTION_METHOD,
    scale_pile_source_transaction_id,
)
from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


class _Txn:
    def __init__(self, txn_id=None, method=None):
        if txn_id is not None:
            self.id = txn_id
        if method is not None:
            self.transaction_method = method


# --------------------------------------------------------------------------
# Which grain does a transaction use?
# --------------------------------------------------------------------------

def test_scale_transaction_gets_its_own_pile():
    assert scale_pile_source_transaction_id(_Txn(77, SCALE_TRANSACTION_METHOD)) == 77


def test_web_entry_keeps_the_monthly_pile():
    """None is not a fallback — it is the key value that matches every pre-scale row."""
    assert scale_pile_source_transaction_id(_Txn(88, 'origin')) is None


@pytest.mark.parametrize('method', ['transport', 'transform', 'qr_input', 'reward', 'manual_input'])
def test_every_other_transaction_method_keeps_the_monthly_pile(method):
    assert scale_pile_source_transaction_id(_Txn(99, method)) is None


def test_missing_method_keeps_the_monthly_pile():
    """A partially built object must never be mistaken for a scale reading."""
    assert scale_pile_source_transaction_id(_Txn(101)) is None


def test_scale_transaction_without_an_id_yields_none():
    """Before flush there is no id; keying on None is safer than inventing one."""
    assert scale_pile_source_transaction_id(_Txn(None, SCALE_TRANSACTION_METHOD)) is None


def test_no_transaction_at_all():
    """The month backfill reaches records whose parent transaction failed to load."""
    assert scale_pile_source_transaction_id(None) is None


# --------------------------------------------------------------------------
# The tentative-pile key gained an optional 8th segment
# --------------------------------------------------------------------------

_SENTINEL = 'reached-the-database'


class _ExplodingDb:
    """Passing the key guard is proven by getting as far as a query."""

    def query(self, *_args, **_kwargs):
        raise RuntimeError(_SENTINEL)


def _materialize(key):
    return TraceabilityService(_ExplodingDb()).materialize_tentative_group(key, organization_id=1)


@pytest.mark.parametrize('key', [
    'tentative:10:20:None:None:2026:8',          # monthly pile — the only shape before scales
    'tentative:10:20:None:None:2026:8:4567',     # per-weigh-in scale pile
    'tentative:None:None:None:None:2026:8',      # every optional component absent
])
def test_valid_keys_get_past_the_guard(key):
    result = _materialize(key)
    assert result['success'] is False
    assert result['message'] == _SENTINEL, 'key was rejected before reaching the lookup'


@pytest.mark.parametrize('key', [
    'tentative:10:20:None:None:2026',            # too few
    'tentative:10:20:None:None:2026:8:4567:99',  # too many
    'group:10:20:None:None:2026:8',              # wrong prefix
    '',
])
def test_malformed_keys_are_rejected_before_any_query(key):
    result = _materialize(key)
    assert result['success'] is False
    assert result['message'] == 'Invalid tentative group key'


def test_seven_and_eight_part_keys_are_not_the_same_pile():
    """The 8th segment is the whole point: same tenant, same material, two weigh-ins.

    Both must be accepted, and they must not be interchangeable — that is enforced by
    the lookup, but the shapes have to survive parsing first.
    """
    monthly = 'tentative:10:20:None:None:2026:8'
    weigh_in = 'tentative:10:20:None:None:2026:8:4567'
    assert monthly != weigh_in
    for key in (monthly, weigh_in):
        assert _materialize(key)['message'] == _SENTINEL
