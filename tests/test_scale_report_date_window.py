"""Guards how far a public report link may be stepped back in time.

The QR page can move between days, but a single photographed QR must not turn
into a window onto the station's whole history — daily intake over a run of
days shows the trend, which is more commercially revealing than any one day.
The bound lives in the token, so it cannot be widened from the client.
"""

from datetime import date

import pytest

from GEPPPlatform.libs.exceptions import APIException, ValidationException
from GEPPPlatform.services.cores.scale_reports.scale_report_token import (
    PUBLIC_DAY_WINDOW_DAYS,
    resolve_requested_day,
)

TOKEN_DAY = date(2026, 7, 26)
CLAIMS = {'origin_id': 1, 'org_id': 10, 'day': TOKEN_DAY}


@pytest.fixture(autouse=True)
def _pin_real_exceptions(real_api_exceptions):
    """See the fixture's docstring — a crm_features test mutates the shared
    exceptions module in place."""


# ── allowed ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('requested', [None, ''])
def test_no_date_means_the_day_the_qr_was_made(requested):
    assert resolve_requested_day(CLAIMS, requested) == TOKEN_DAY


def test_the_token_day_itself_is_allowed():
    assert resolve_requested_day(CLAIMS, '2026-07-26') == TOKEN_DAY


def test_one_day_back_is_allowed():
    assert resolve_requested_day(CLAIMS, '2026-07-25') == date(2026, 7, 25)


def test_the_window_is_exactly_two_days_wide():
    # If someone widens PUBLIC_DAY_WINDOW_DAYS, this states what changes.
    assert PUBLIC_DAY_WINDOW_DAYS == 1
    earliest = date(2026, 7, 26 - PUBLIC_DAY_WINDOW_DAYS)
    assert resolve_requested_day(CLAIMS, earliest.isoformat()) == earliest


# ── refused ──────────────────────────────────────────────────────────────────

def test_two_days_back_is_refused():
    with pytest.raises(APIException) as exc:
        resolve_requested_day(CLAIMS, '2026-07-24')
    assert exc.value.status_code == 403
    assert exc.value.error_code == 'DATE_OUT_OF_RANGE'


def test_a_future_day_is_refused():
    """A QR made yesterday must not keep reporting today's takings forever."""
    with pytest.raises(APIException) as exc:
        resolve_requested_day(CLAIMS, '2026-07-27')
    assert exc.value.status_code == 403


def test_far_future_and_far_past_are_refused():
    for far in ('2020-01-01', '2099-12-31'):
        with pytest.raises(APIException):
            resolve_requested_day(CLAIMS, far)


@pytest.mark.parametrize('bad', ['26/07/2026', 'yesterday', '2026-13-01',
                                 '2026-07-32', '2026-7'])
def test_malformed_dates_are_a_different_failure_from_out_of_range(bad):
    """422 means "you typed it wrong", 403 means "you may not see that".
    Collapsing them would hide which one actually happened."""
    with pytest.raises(ValidationException):
        resolve_requested_day(CLAIMS, bad)


def test_the_bound_is_relative_to_the_token_not_to_today():
    """An old token stays pinned to its own two days — it does not slide
    forward as real time passes."""
    old = {'origin_id': 1, 'org_id': 10, 'day': date(2026, 1, 15)}
    assert resolve_requested_day(old, '2026-01-14') == date(2026, 1, 14)
    with pytest.raises(APIException):
        resolve_requested_day(old, '2026-01-16')
