"""Tests for the Bangkok-day ↔ UTC window conversion.

This is the highest-value test file in the daily-report feature: if the window
maths is off by the 7-hour offset, every "today" figure is quietly wrong and
still looks plausible. Assert the boundaries explicitly.
"""

from datetime import date, datetime, timedelta

import pytest

from GEPPPlatform.services.cores.scale_reports.bkk_time import (
    BKK_OFFSET,
    bkk_day_to_utc_window,
    bkk_today,
    parse_day,
    utc_to_bkk_date,
)


# ── the window itself ────────────────────────────────────────────────────────

def test_window_starts_at_17_00_utc_the_previous_day():
    start, end = bkk_day_to_utc_window(date(2026, 7, 26))
    assert start == datetime(2026, 7, 25, 17, 0, 0)
    assert end == datetime(2026, 7, 26, 17, 0, 0)


def test_window_is_exactly_24_hours():
    start, end = bkk_day_to_utc_window(date(2026, 7, 26))
    assert end - start == timedelta(days=1)


def test_window_is_naive_so_it_compares_with_the_db_column():
    # transaction_date has no tzinfo; aware bounds would raise on comparison.
    start, end = bkk_day_to_utc_window(date(2026, 7, 26))
    assert start.tzinfo is None
    assert end.tzinfo is None


# ── boundary readings land on the right day ──────────────────────────────────

@pytest.mark.parametrize(
    'moment_utc, expected_in_window',
    [
        # first instant of Thai 26 July
        (datetime(2026, 7, 25, 17, 0, 0), True),
        # one microsecond before the day starts → previous day
        (datetime(2026, 7, 25, 16, 59, 59), False),
        # middle of the Thai working day (09:00 Bangkok)
        (datetime(2026, 7, 26, 2, 0, 0), True),
        # last instant of Thai 26 July
        (datetime(2026, 7, 26, 16, 59, 59), True),
        # 17:00 UTC is already 00:00 of Thai 27 July → excluded
        (datetime(2026, 7, 26, 17, 0, 0), False),
        # the reading that a naive 00:00–24:00 UTC filter would misplace
        (datetime(2026, 7, 26, 17, 30, 0), False),
    ],
)
def test_membership_of_boundary_readings(moment_utc, expected_in_window):
    start, end = bkk_day_to_utc_window(date(2026, 7, 26))
    assert (start <= moment_utc < end) is expected_in_window


def test_evening_bangkok_reading_belongs_to_that_thai_day_not_the_utc_one():
    """A 00:30 Bangkok reading on 27 July is 17:30 UTC on 26 July.

    Grouping by the UTC date would file it under the 26th. Grouping by Thai
    date must file it under the 27th.
    """
    moment_utc = datetime(2026, 7, 26, 17, 30, 0)
    assert utc_to_bkk_date(moment_utc) == date(2026, 7, 27)

    start_27, end_27 = bkk_day_to_utc_window(date(2026, 7, 27))
    assert start_27 <= moment_utc < end_27


# ── utc_to_bkk_date ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    'moment_utc, expected_day',
    [
        (datetime(2026, 7, 26, 16, 59, 59), date(2026, 7, 26)),
        (datetime(2026, 7, 26, 17, 0, 0), date(2026, 7, 27)),
        # month rollover
        (datetime(2026, 7, 31, 17, 0, 0), date(2026, 8, 1)),
        # year rollover
        (datetime(2026, 12, 31, 17, 0, 0), date(2027, 1, 1)),
    ],
)
def test_utc_to_bkk_date_rolls_over_at_17_00_utc(moment_utc, expected_day):
    assert utc_to_bkk_date(moment_utc) == expected_day


def test_windows_of_consecutive_days_tile_without_gap_or_overlap():
    _, end_26 = bkk_day_to_utc_window(date(2026, 7, 26))
    start_27, _ = bkk_day_to_utc_window(date(2026, 7, 27))
    assert end_26 == start_27


def test_offset_constant_is_seven_hours():
    assert BKK_OFFSET == timedelta(hours=7)


# ── parse_day ────────────────────────────────────────────────────────────────

def test_parse_day_accepts_iso_date():
    assert parse_day('2026-07-26') == date(2026, 7, 26)


@pytest.mark.parametrize('empty', [None, ''])
def test_parse_day_defaults_to_bangkok_today(empty):
    assert parse_day(empty) == bkk_today()


def test_parse_day_passes_through_a_date_object():
    assert parse_day(date(2026, 7, 26)) == date(2026, 7, 26)


@pytest.mark.parametrize(
    'bad',
    ['26/07/2026', '2026-7-26-1', 'today', '2026-13-01', '2026-07-32'],
)
def test_parse_day_rejects_bad_input(bad):
    # Callers turn this into a 422 — it must not silently fall back to today.
    with pytest.raises(ValueError):
        parse_day(bad)


def test_bkk_today_is_never_behind_the_utc_date():
    # +07:00 means Bangkok is same-day or one day ahead of UTC, never behind.
    from GEPPPlatform.services.cores.scale_reports.bkk_time import _utc_now_naive

    utc_day = _utc_now_naive().date()
    assert bkk_today() in (utc_day, utc_day + timedelta(days=1))
