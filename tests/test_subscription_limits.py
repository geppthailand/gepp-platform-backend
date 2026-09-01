"""Limit resolution + period arithmetic.

Everything here is a billing input, so the cases that matter are the ones that
would be *silently* wrong: a 0 mistaken for "unset", a partial month not billed,
an open-ended period reporting nothing.
"""

import datetime as dt
from types import SimpleNamespace

import pytest

from GEPPPlatform.services.subscriptions.limits import (
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_IMAGE_DIMENSION_PX,
    DEFAULT_TRANSACTIONS_PER_MONTH,
    MIN_IMAGE_DIMENSION_PX,
    _first_not_none,
    months_in_period,
    period_transaction_allowance,
    resolve_org_limits,
)


def period(txn=None, size=None, start='2026-01-01', end='2026-12-31', pid=7):
    return SimpleNamespace(
        id=pid, plan_id=3,
        create_transaction_limit=txn,
        max_file_size_mb=size,
        current_period_starts_at=dt.datetime.fromisoformat(start) if start else None,
        current_period_ends_at=dt.datetime.fromisoformat(end) if end else None,
    )


def org(txn=None, size=None, dim=None, oid=42):
    return SimpleNamespace(
        id=oid,
        default_transaction_limit_per_month=txn,
        default_max_file_size_mb=size,
        max_image_dimension_px=dim,
    )


class FakeDB:
    """Minimal Query chain: returns the org for an Organization lookup and
    `found_period` for a Subscription lookup.

    It supports `order_by` so the `period=None` path really runs `find_period`
    and its filter/order construction gets exercised, rather than being skipped.
    """

    def __init__(self, organization, found_period=None):
        self._org = organization
        self._period = found_period
        self._wants = None

    def query(self, model):
        self._wants = getattr(model, '__name__', str(model))
        return self

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def first(self):
        return self._period if self._wants == 'Subscription' else self._org


def resolve(organization, p):
    return resolve_org_limits(FakeDB(organization), organization.id, period=p)


class TestPrecedence:
    def test_period_beats_organization(self):
        r = resolve(org(txn=500, size=20), period(txn=900, size=5))
        assert (r.transactions_per_month, r.max_file_size_mb) == (900, 5.0)
        assert r.transactions_source == r.file_size_source == 'period'

    def test_organization_used_when_period_is_silent(self):
        r = resolve(org(txn=500, size=20), period(txn=None, size=None))
        assert (r.transactions_per_month, r.max_file_size_mb) == (500, 20.0)
        assert r.transactions_source == 'organization'

    def test_system_default_when_nothing_is_set(self):
        r = resolve(org(), period())
        assert r.transactions_per_month == DEFAULT_TRANSACTIONS_PER_MONTH
        assert r.max_file_size_mb == DEFAULT_MAX_FILE_SIZE_MB
        assert r.transactions_source == 'system'

    def test_no_period_at_all_falls_back(self):
        # period not passed in AND the lookup finds nothing -> org default.
        o = org(txn=250)
        r = resolve_org_limits(FakeDB(o, found_period=None), o.id)
        assert (r.transactions_per_month, r.transactions_source) == (250, 'organization')
        assert r.subscription_id is None

    def test_lookup_is_used_when_period_not_passed(self):
        o = org(txn=250)
        r = resolve_org_limits(FakeDB(o, found_period=period(txn=800, pid=11)), o.id)
        assert (r.transactions_per_month, r.subscription_id) == (800, 11)

    def test_sources_are_resolved_independently(self):
        # One limit from the period, the other from the org. A single "source"
        # field would have to lie about one of them.
        r = resolve(org(size=8), period(txn=700, size=None))
        assert (r.transactions_source, r.file_size_source) == ('period', 'organization')


class TestZeroIsNotUnset:
    """`a or b` would skip a real 0. These are the cases that would catch it."""

    def test_zero_transactions_on_the_period_is_honoured(self):
        r = resolve(org(txn=500), period(txn=0))
        assert (r.transactions_per_month, r.transactions_source) == (0, 'period')

    def test_zero_file_size_on_the_org_is_honoured(self):
        r = resolve(org(size=0), period(size=None))
        assert (r.max_file_size_mb, r.file_size_source) == (0.0, 'organization')

    def test_first_not_none_helper_directly(self):
        assert _first_not_none((0, 'period'), (9, 'org')) == (0, 'period')
        assert _first_not_none((None, 'period'), (9, 'org')) == (9, 'org')


class TestImageDimension:
    def test_has_no_period_layer(self):
        # Deliberate: a period carrying an image cap would store the same photo
        # at different resolutions depending on when it arrived.
        p = period()
        p.max_image_dimension_px = 4000          # must be ignored
        r = resolve(org(dim=1280), p)
        assert (r.max_image_dimension_px, r.image_dimension_source) == (1280, 'organization')

    def test_floor_is_applied(self):
        r = resolve(org(dim=64), period())
        assert r.max_image_dimension_px == MIN_IMAGE_DIMENSION_PX

    def test_system_default(self):
        assert resolve(org(), period()).max_image_dimension_px == \
            DEFAULT_MAX_IMAGE_DIMENSION_PX


class TestBytesConversion:
    def test_mb_to_bytes(self):
        assert resolve(org(), period(size=5)).max_file_size_bytes == 5 * 1024 * 1024

    def test_fractional_mb(self):
        assert resolve(org(), period(size=0.5)).max_file_size_bytes == 524288

    def test_to_dict_carries_bytes(self):
        d = resolve(org(), period(size=2)).to_dict()
        assert d['max_file_size_bytes'] == 2 * 1024 * 1024
        assert d['file_size_source'] == 'period'


class TestMonthsInPeriod:
    @pytest.mark.parametrize('start,end,expected', [
        ('2026-01-01', '2026-01-31', 1),    # exactly one month
        ('2026-01-01', '2026-12-31', 12),   # a full year
        ('2026-01-15', '2026-03-02', 3),    # partial ends still bill Jan+Feb+Mar
        ('2026-01-31', '2026-02-01', 2),    # two days, two calendar months
        ('2026-12-01', '2027-01-31', 2),    # crosses a year boundary
        ('2026-01-01', '2026-01-01', 1),    # single day
    ])
    def test_counts_calendar_months_inclusive(self, start, end, expected):
        assert months_in_period(dt.date.fromisoformat(start),
                                dt.date.fromisoformat(end)) == expected

    def test_open_ended_is_capped_at_today(self):
        # A running contract must report what it has consumed so far, not 0.
        assert months_in_period(dt.date(2026, 1, 1), None,
                                cap_at=dt.date(2026, 4, 15)) == 4

    def test_no_start_means_nothing_to_count(self):
        assert months_in_period(None, dt.date(2026, 4, 1)) == 0

    def test_end_before_start_is_zero_not_negative(self):
        assert months_in_period(dt.date(2026, 6, 1), dt.date(2026, 1, 1)) == 0


class TestPeriodAllowance:
    def test_year_at_100_per_month(self):
        assert period_transaction_allowance(
            period(txn=100, start='2026-01-01', end='2026-12-31')) == 1200

    def test_partial_months_are_billed_whole(self):
        assert period_transaction_allowance(
            period(txn=50, start='2026-01-20', end='2026-03-05')) == 150

    def test_no_monthly_limit_gives_none_not_zero(self):
        # None means "unlimited / not agreed"; 0 would mean "none allowed".
        assert period_transaction_allowance(period(txn=None)) is None

    def test_open_ended_period_uses_cap(self):
        assert period_transaction_allowance(
            period(txn=10, start='2026-01-01', end=None),
            cap_at=dt.date(2026, 3, 31)) == 30

    def test_per_month_override_wins(self):
        # The report recomputes with the resolved value, which may have come
        # from the org default rather than the period row.
        assert period_transaction_allowance(
            period(txn=100, start='2026-01-01', end='2026-02-28'),
            per_month=7) == 14

    def test_none_period(self):
        assert period_transaction_allowance(None) is None
