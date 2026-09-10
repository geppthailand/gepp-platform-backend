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


class TestUpdatePeriodValidationOrder:
    """`update_subscription` must validate the date range BEFORE assigning it.

    Assigning first and checking after left the ORM object dirty with rejected
    values: autoflush would push them on the next query in the same session,
    and every later edit to that row failed the same validation even when it
    never mentioned the dates. This pins the ordering without needing a DB.
    """

    class _Row:
        """A stand-in for the Subscription row, recording what got written."""

        def __init__(self, start, end):
            self.id = 1
            self.current_period_starts_at = start
            self.current_period_ends_at = end
            self.plan_id = 1
            self.status = 'active'
            self.create_transaction_limit = 100
            self.ai_audit_limit = 10
            self.allow_ai_audit_exceed_quota = False
            self.duration_type = 'monthly'
            self.period_label = 'before'
            self.notes = None
            self.max_file_size_mb = None

    def _update(self, row, data):
        """Drive the real method with a fake session, so only the field logic
        under test runs — no database involved."""
        from GEPPPlatform.services.admin.admin_service import AdminService

        class FakeQuery:
            def __init__(self, r):
                self._r = r

            def filter(self, *_a, **_k):
                return self

            def first(self):
                return self._r

        class FakeSession:
            def __init__(self, r):
                self._r = r
                self.flushed = False

            def query(self, _m):
                return FakeQuery(self._r)

            def flush(self):
                self.flushed = True

        svc = object.__new__(AdminService)
        svc.db_session = FakeSession(row)
        return svc.update_subscription(1, data), svc.db_session

    def test_rejected_range_leaves_the_row_untouched(self):
        from GEPPPlatform.libs.exceptions import BadRequestException

        row = self._Row(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                        dt.datetime(2026, 12, 31, tzinfo=dt.timezone.utc))
        with pytest.raises(BadRequestException):
            self._update(row, {'periodStartsAt': '2026-06-01',
                               'periodEndsAt': '2026-01-01',
                               'periodLabel': 'should not stick'})

        # Neither the dates NOR the unrelated field may have been written.
        assert row.current_period_starts_at.date() == dt.date(2026, 1, 1)
        assert row.current_period_ends_at.date() == dt.date(2026, 12, 31)
        assert row.period_label == 'before'

    def test_a_later_edit_still_works_after_a_rejection(self):
        """The actual symptom: one bad save used to poison every save after it."""
        from GEPPPlatform.libs.exceptions import BadRequestException

        row = self._Row(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                        dt.datetime(2026, 12, 31, tzinfo=dt.timezone.utc))
        with pytest.raises(BadRequestException):
            self._update(row, {'periodStartsAt': '2026-06-01',
                               'periodEndsAt': '2026-01-01'})
        self._update(row, {'periodLabel': 'after'})     # must not raise
        assert row.period_label == 'after'

    def test_partial_patch_validates_against_the_stored_other_end(self):
        # Sending only a start date that is after the STORED end must fail, even
        # though the payload never mentions the end.
        from GEPPPlatform.libs.exceptions import BadRequestException

        row = self._Row(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                        dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc))
        with pytest.raises(BadRequestException):
            self._update(row, {'periodStartsAt': '2026-09-01'})

    def test_clearing_the_end_date_makes_it_open_ended(self):
        row = self._Row(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                        dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc))
        self._update(row, {'periodEndsAt': None})
        assert row.current_period_ends_at is None

    def test_clearing_max_file_size_restores_inheritance(self):
        # None is a real value here: it removes the period override so the org
        # default applies again.
        row = self._Row(None, None)
        row.max_file_size_mb = 7.5
        self._update(row, {'maxFileSizeMb': None})
        assert row.max_file_size_mb is None

    def test_absent_keys_are_left_alone(self):
        row = self._Row(None, None)
        row.max_file_size_mb = 7.5
        self._update(row, {'periodLabel': 'x'})
        assert row.max_file_size_mb == 7.5      # not clobbered to None


class TestPeriodDateState:
    """`status` is typed in by hand and says 'active' on periods that ended
    months ago. That is how a 0.1 MB limit looked like it was in force while
    uploads were still being checked against the 50 MB system default — the
    period ran 16 Feb to 18 Mar and the test happened in September.

    `dateState` is derived from the dates so the UI can say so.
    """

    @staticmethod
    def _sub(start, end):
        return SimpleNamespace(
            current_period_starts_at=(dt.datetime.fromisoformat(start)
                                      if start else None),
            current_period_ends_at=(dt.datetime.fromisoformat(end)
                                    if end else None),
        )

    def _state(self, start, end, today='2026-09-07'):
        from GEPPPlatform.services.admin.admin_service import _period_date_state
        return _period_date_state(self._sub(start, end),
                                  dt.date.fromisoformat(today))

    def test_the_reported_case_is_expired(self):
        # status said 'active'; the dates say otherwise.
        assert self._state('2026-02-16', '2026-03-18') == 'expired'

    def test_covering_today_is_in_force(self):
        assert self._state('2026-08-01', '2026-12-31') == 'in_force'

    def test_future_period_is_scheduled(self):
        assert self._state('2026-10-01', '2026-12-31') == 'scheduled'

    def test_open_ended_that_has_started_is_in_force(self):
        assert self._state('2026-01-01', None) == 'in_force'

    def test_no_start_date_never_applies(self):
        # An unbounded row would otherwise silently capture every date.
        assert self._state(None, '2026-12-31') == 'undated'

    def test_boundaries_are_inclusive(self):
        assert self._state('2026-09-07', '2026-09-07') == 'in_force'
        assert self._state('2026-09-08', '2026-12-31') == 'scheduled'
        assert self._state('2026-01-01', '2026-09-06') == 'expired'

    def test_expired_period_does_not_supply_limits(self):
        # The behaviour behind the tag: an expired period is not found, so its
        # limits are not what enforcement uses.
        from GEPPPlatform.services.subscriptions.limits import find_period

        expired = period(size=0.1, start='2026-02-16', end='2026-03-18')
        db = FakeDB(org(), found_period=None)   # find_period would match nothing
        r = resolve_org_limits(db, 42, at=dt.date(2026, 9, 7))
        assert r.max_file_size_mb == DEFAULT_MAX_FILE_SIZE_MB
        assert r.file_size_source == 'system'
        # ...and it WOULD have applied inside its own range.
        r2 = resolve_org_limits(FakeDB(org()), 42, period=expired)
        assert (r2.max_file_size_mb, r2.file_size_source) == (0.1, 'period')


class TestLapsedOrgKeepsItsLastTerms:
    """No period covers today AND the global access gate is off.

    The org is still working, so it has to work under *some* agreed terms. The
    tempting answer — fall through to the org/system defaults — is wrong in a
    specific and expensive way: the system file-size default is 50 MB, so a
    customer contracted to 0.1 MB would get 500x their allowance by letting
    their subscription lapse. A lapse must never be an upgrade.
    """

    class LapsedDB:
        """Org lookup, then TWO subscription lookups: the covering one (None)
        and the most-recently-started one."""

        def __init__(self, organization, last=None):
            self._org = organization
            self._last = last
            self._wants = None
            self.sub_lookups = 0

        def query(self, model):
            self._wants = getattr(model, '__name__', str(model))
            return self

        def filter(self, *_a, **_k):
            return self

        def order_by(self, *_a, **_k):
            return self

        def first(self):
            if self._wants != 'Subscription':
                return self._org
            self.sub_lookups += 1
            # 1st = find_period (nothing covers today), 2nd = latest started.
            return None if self.sub_lookups == 1 else self._last

    def resolve_lapsed(self, organization, last, gate=False):
        db = self.LapsedDB(organization, last)
        return resolve_org_limits(db, organization.id,
                                  fall_back_to_last_period=not gate), db

    def test_the_expired_periods_limits_still_apply(self):
        # The reported org: period 33 set 0.1 MB and ended 2026-03-18.
        last = period(txn=10000, size=0.1, start='2026-02-16', end='2026-03-18',
                      pid=33)
        limits, _ = self.resolve_lapsed(org(), last)
        assert limits.max_file_size_mb == 0.1
        assert limits.transactions_per_month == 10000
        assert limits.file_size_source == 'last_period'
        assert limits.subscription_id == 33
        assert limits.from_expired_period is True

    def test_it_does_not_silently_become_the_permissive_default(self):
        last = period(txn=10000, size=0.1, start='2026-02-16', end='2026-03-18')
        limits, _ = self.resolve_lapsed(org(), last)
        assert limits.max_file_size_mb != DEFAULT_MAX_FILE_SIZE_MB

    def test_gate_on_means_no_fallback(self):
        # With the gate ON the org has no access at all, so its limits fall to
        # the defaults — and the backoffice must show that, not a stale number
        # from a dead contract.
        last = period(txn=10000, size=0.1, start='2026-02-16', end='2026-03-18')
        limits, db = self.resolve_lapsed(org(), last, gate=True)
        assert limits.max_file_size_mb == DEFAULT_MAX_FILE_SIZE_MB
        assert limits.file_size_source == 'system'
        assert limits.from_expired_period is False
        assert db.sub_lookups == 1      # the latest-period lookup never ran

    def test_org_default_still_beats_a_silent_expired_period(self):
        # An expired period that set nothing contributes nothing; the org
        # default is more specific than the system one and must still win.
        last = period(txn=None, size=None, start='2026-02-16', end='2026-03-18')
        limits, _ = self.resolve_lapsed(org(size=3.0), last)
        assert (limits.max_file_size_mb, limits.file_size_source) == (3.0, 'organization')
        # Nothing came from the period, so do not claim it did.
        assert limits.from_expired_period is False

    def test_no_periods_at_all_falls_through_cleanly(self):
        limits, _ = self.resolve_lapsed(org(), None)
        assert limits.max_file_size_mb == DEFAULT_MAX_FILE_SIZE_MB
        assert limits.subscription_id is None
        assert limits.from_expired_period is False


class TestLatestStartedPeriodIgnoresTheFuture:
    """`latest_started_period` must not pick a period that has not begun.

    It is the latest by start date, which is exactly the trap: applying a
    contract early is the same class of mistake as inventing one.
    """

    def test_the_filter_excludes_future_starts(self):
        from GEPPPlatform.services.subscriptions.limits import latest_started_period

        captured = []

        class SpyDB:
            def query(self, _m):
                return self

            def filter(self, *conds, **_k):
                captured.extend(str(c) for c in conds)
                return self

            def order_by(self, *_a, **_k):
                return self

            def first(self):
                return None

        latest_started_period(SpyDB(), 42, at=dt.date(2026, 9, 8))
        sql = ' '.join(captured)
        # Bounded above by the date asked about...
        assert 'current_period_starts_at <=' in sql
        # ...and deliberately NOT bounded by the end date, or it would just be
        # find_period again and never match an expired period.
        assert 'current_period_ends_at' not in sql
