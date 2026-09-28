"""No live subscription period -> no access to the business platform.

This is the highest-consequence check in the feature: get it wrong and every
customer is locked out. So the cases that matter most are not the happy path
but the ones that must NOT block:

  * `/api/admin/*` — the backoffice creates the period that unblocks an org. Gate
    it and a lapsed org can only be fixed by someone who cannot log in to fix it.
  * `/api/auth/*` — a blocked user still has to be able to log out.
  * a check that throws — must fail OPEN, or one bug takes everyone offline.

Most tests here describe what happens with the global switch ON (Global
Settings → Subscription → *disable when not in period*), so `gate_on` forces
it: the fake sessions have no `system_settings` table, and a settings read that
cannot answer resolves to OFF — which would make every "is it blocked?"
assertion below trivially pass for the wrong reason. `TestGlobalSwitch` covers
the switch itself.
"""

import datetime as dt
from types import SimpleNamespace

import pytest

from GEPPPlatform.services.subscriptions.access import (
    ALWAYS_ALLOWED_PREFIXES,
    BLOCKED_ERROR_CODE,
    blocked_message,
    gate_enabled,
    path_is_always_allowed,
    subscription_access,
)

#: The real implementation, captured before `gate_on` shadows it on the module.
REAL_GATE_ENABLED = gate_enabled


def period(start='2026-01-01', end='2026-12-31'):
    return SimpleNamespace(
        id=1, plan_id=3,
        create_transaction_limit=100, max_file_size_mb=None,
        deleted_date=None,
        current_period_starts_at=dt.datetime.fromisoformat(start) if start else None,
        current_period_ends_at=dt.datetime.fromisoformat(end) if end else None,
    )


class FakeDB:
    """`find_period` result, then the `latest period` lookup."""

    def __init__(self, covering=None, latest=None, explode=False):
        self._covering = covering
        self._latest = latest
        self._explode = explode
        self._calls = 0

    def query(self, _m):
        if self._explode:
            raise RuntimeError('session is dead')
        return self

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def first(self):
        self._calls += 1
        return self._covering if self._calls == 1 else self._latest


AS_OF = dt.date(2026, 9, 8)


@pytest.fixture(autouse=True)
def gate_on(monkeypatch):
    """Force the global switch ON for every test in this module.

    Patched at the point of USE (`access.gate_enabled`) rather than stubbing the
    settings module, so a test still exercises the real decision code path.
    Individual tests re-patch it to False where the switch itself is the subject.
    """
    import GEPPPlatform.services.subscriptions.access as access_mod
    monkeypatch.setattr(access_mod, 'gate_enabled', lambda _db: True)


class TestMustNotBlock:
    def test_admin_paths_are_never_gated(self):
        # Otherwise: lapsed org -> staff cannot reach the backoffice -> cannot
        # create the period -> the org can never be unblocked.
        assert path_is_always_allowed('/api/admin')
        assert path_is_always_allowed('/api/admin/organizations/3/subscription-periods')

    def test_auth_paths_are_never_gated(self):
        # A blocked user must still be able to log out and clear their session.
        assert path_is_always_allowed('/api/auth/login')
        assert path_is_always_allowed('/api/auth/logout')
        assert path_is_always_allowed('/api/auth/refresh')

    def test_health_is_never_gated(self):
        assert path_is_always_allowed('/health')

    def test_allowlist_is_short_on_purpose(self):
        # Every entry is a hole in the policy; this fails loudly if one is added
        # without a deliberate decision.
        assert set(ALWAYS_ALLOWED_PREFIXES) == {'/api/admin', '/api/auth', '/health'}

    def test_the_allowlist_cannot_be_widened_by_appending(self):
        # `startswith('/api/admin')` also accepts '/api/adminfoo'.
        assert not path_is_always_allowed('/api/adminfoo')
        assert not path_is_always_allowed('/healthz')

    def test_business_paths_ARE_gated(self):
        for p in ('/api/transactions', '/api/locations', '/api/reports/x',
                  '/api/organizations/setup'):
            assert not path_is_always_allowed(p), p

    def test_empty_path_is_not_allowlisted(self):
        assert not path_is_always_allowed('')
        assert not path_is_always_allowed(None)


class TestFailsOpen:
    def test_a_broken_check_grants_access(self):
        # A bug here must not take every customer offline.
        d = subscription_access(FakeDB(explode=True), 42, as_of=AS_OF)
        assert d['allowed'] is True
        assert d['reason'] == 'check_failed'

    def test_no_organization_is_allowed(self):
        # Service accounts, IoT devices and the public QR channel have no org
        # member behind them and are out of scope for a per-org gate.
        for org_id in (None, 0):
            d = subscription_access(FakeDB(), org_id, as_of=AS_OF)
            assert d['allowed'] is True and d['reason'] == 'no_organization'


class TestDecisions:
    def test_a_covering_period_is_allowed(self):
        d = subscription_access(FakeDB(covering=period()), 42, as_of=AS_OF)
        assert (d['allowed'], d['reason']) == (True, 'ok')

    def test_lapsed_is_blocked_and_reports_the_end_date(self):
        # The reported shape: Period 33 ran 16 Feb -> 18 Mar, today is September.
        latest = period(start='2026-02-16', end='2026-03-18')
        d = subscription_access(FakeDB(covering=None, latest=latest), 42, as_of=AS_OF)
        assert d['allowed'] is False
        assert d['reason'] == 'lapsed'
        assert d['ended_at'].startswith('2026-03-18')

    def test_never_subscribed_is_blocked_with_its_own_reason(self):
        # Needs a different message from "your subscription ended".
        d = subscription_access(FakeDB(covering=None, latest=None), 42, as_of=AS_OF)
        assert (d['allowed'], d['reason']) == (False, 'never_subscribed')

    def test_a_future_period_is_blocked_as_not_started(self):
        latest = period(start='2026-12-01', end='2027-11-30')
        d = subscription_access(FakeDB(covering=None, latest=latest), 42, as_of=AS_OF)
        assert (d['allowed'], d['reason']) == (False, 'not_started')
        assert d['starts_at'].startswith('2026-12-01')


class TestMessages:
    @pytest.mark.parametrize('reason,expect', [
        ('lapsed', 'ended'),
        ('never_subscribed', 'does not have a subscription'),
        ('not_started', 'starts on'),
    ])
    def test_each_reason_says_something_different(self, reason, expect):
        msg = blocked_message({
            'reason': reason,
            'ended_at': '2026-03-18T23:59:59+07:00',
            'starts_at': '2026-12-01T00:00:00+07:00',
        })
        assert expect in msg

    def test_error_code_is_stable_for_clients(self):
        # Clients key their screen off this, not off the prose.
        assert BLOCKED_ERROR_CODE == 'NO_ACTIVE_SUBSCRIPTION'


class TestQrChannelIsGatedToo:
    """A QR form is unauthenticated but NOT anonymous: the channel row carries
    `organization_id`. Leaving it open would be a hole straight past the gate —
    anyone with the link could keep feeding a lapsed organization."""

    class ChannelDB(FakeDB):
        def __init__(self, org_id, covering=None, latest=None,
                     row_missing=False, explode_lookup=False):
            super().__init__(covering=covering, latest=latest)
            self._org_id = org_id
            self._row_missing = row_missing
            self._explode_lookup = explode_lookup

        def execute(self, *_a, **_k):
            if self._explode_lookup:
                raise RuntimeError('db is gone')
            outer = self

            class R:
                def fetchone(self_inner):
                    return None if outer._row_missing else (outer._org_id,)

            return R()

    def _access(self, db, hash_='H'):
        from GEPPPlatform.services.subscriptions.access import (
            channel_subscription_access,
        )
        return channel_subscription_access(db, hash_, as_of=AS_OF)

    def test_channel_of_a_lapsed_org_is_blocked(self):
        latest = period(start='2026-02-16', end='2026-03-18')
        d = self._access(self.ChannelDB(8, covering=None, latest=latest))
        assert d['allowed'] is False
        assert d['reason'] == 'lapsed'
        assert d['channel_hash'] == 'H'

    def test_channel_of_a_live_org_is_allowed(self):
        d = self._access(self.ChannelDB(8, covering=period()))
        assert (d['allowed'], d['reason']) == (True, 'ok')

    def test_unknown_hash_fails_open(self):
        # The route's own 404 handles a bad hash; the gate must not turn it into
        # a confusing 403.
        d = self._access(self.ChannelDB(None, row_missing=True))
        assert (d['allowed'], d['reason']) == (True, 'channel_not_found')

    def test_missing_hash_fails_open(self):
        d = self._access(self.ChannelDB(8), hash_=None)
        assert (d['allowed'], d['reason']) == (True, 'no_channel')

    def test_a_broken_lookup_fails_open(self):
        d = self._access(self.ChannelDB(8, explode_lookup=True))
        assert (d['allowed'], d['reason']) == (True, 'check_failed')


class TestChannelWording:
    """Whoever scanned the QR is site staff or a contractor. They do not know
    what a subscription period is and cannot renew one, so sending them to GEPP
    is sending them to the wrong place."""

    def test_channel_audience_points_at_the_organization(self):
        msg = blocked_message({'reason': 'lapsed', 'ended_at': '2026-03-18'},
                              audience='channel')
        assert 'contact the organization' in msg
        assert 'GEPP' not in msg
        # No dates or subscription jargon leaked to an outsider.
        assert '2026-03-18' not in msg
        assert 'subscription' not in msg.lower()

    def test_member_audience_still_gets_the_detail(self):
        msg = blocked_message({'reason': 'lapsed', 'ended_at': '2026-03-18'})
        assert 'GEPP' in msg and '2026-03-18' in msg

    def test_channel_wording_is_the_same_for_every_reason(self):
        # An outsider does not need to know WHY, only that it is inactive.
        msgs = {
            blocked_message({'reason': r}, audience='channel')
            for r in ('lapsed', 'never_subscribed', 'not_started')
        }
        assert len(msgs) == 1


class TestGlobalSwitch:
    """Global Settings → Subscription → *disable when not in period*.

    The whole policy hangs off this one boolean, and it ships OFF because
    turning it on locks out 237 organizations on current data. So the cases
    that matter are: off means nobody is blocked, on means the policy applies,
    and an unreadable setting means OFF (never a surprise lockout).
    """

    @pytest.fixture
    def gate_off(self, monkeypatch):
        import GEPPPlatform.services.subscriptions.access as access_mod
        monkeypatch.setattr(access_mod, 'gate_enabled', lambda _db: False)

    def test_switch_off_allows_an_org_that_would_otherwise_be_blocked(self, gate_off):
        latest = period(start='2026-02-16', end='2026-03-18')  # long expired
        d = subscription_access(FakeDB(covering=None, latest=latest), 42, as_of=AS_OF)
        assert (d['allowed'], d['reason']) == (True, 'gate_disabled')

    def test_switch_off_short_circuits_before_touching_the_org(self, gate_off):
        # Costs nothing on the request path: no period lookup at all. A dead
        # session would raise if it were queried, so this also proves the
        # ordering rather than just the answer.
        db = FakeDB(explode=True)
        d = subscription_access(db, 42, as_of=AS_OF)
        assert d['reason'] == 'gate_disabled'
        assert db._calls == 0

    def test_switch_off_also_opens_the_qr_channel(self, gate_off):
        # Same switch, both doors — a QR left gated while logins are open (or
        # the reverse) is the kind of half-applied policy nobody can reason
        # about. Proven by a DB whose channel lookup would explode.
        from GEPPPlatform.services.subscriptions.access import (
            channel_subscription_access,
        )
        db = TestQrChannelIsGatedToo.ChannelDB(8, explode_lookup=True)
        d = channel_subscription_access(db, 'H', as_of=AS_OF)
        assert (d['allowed'], d['reason']) == (True, 'gate_disabled')

    def test_switch_on_still_blocks(self):
        # The autouse fixture leaves it on; this is the contrast case.
        latest = period(start='2026-02-16', end='2026-03-18')
        d = subscription_access(FakeDB(covering=None, latest=latest), 42, as_of=AS_OF)
        assert (d['allowed'], d['reason']) == (False, 'lapsed')

    def test_an_unreadable_setting_resolves_to_off(self):
        """A broken settings table must not block anyone.

        Runs the REAL `gate_enabled` — captured at import, before the autouse
        fixture could shadow it — against a session with no `system_settings`.
        That is exactly what a deploy whose migration has not run yet looks
        like, and it must not be the moment every customer gets locked out.
        """
        from GEPPPlatform.services.settings import global_settings as gs
        gs.invalidate_cache()

        class NoSettingsTable:
            def execute(self, *_a, **_k):
                raise RuntimeError('relation "system_settings" does not exist')

        try:
            assert REAL_GATE_ENABLED(NoSettingsTable()) is False
        finally:
            # The cache is module-level; a poisoned entry would leak into
            # whatever test runs next.
            gs.invalidate_cache()
