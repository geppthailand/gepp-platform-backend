"""Bangkok calendar-day ↔ UTC window helpers for the scale daily report.

Why this module exists
----------------------
`transaction_records.transaction_date` is a naive `DateTime` column holding
**UTC** — the scale tablet sends `DateTime.toUtc().toIso8601String()` (see
`app_state.dart` `_formatDateTimeUtc`). Operators, however, think in Thai
calendar days: "today" means 00:00–24:00 Asia/Bangkok.

Filtering the UTC column with naive local-looking bounds silently shifts the
report by 7 hours — every reading between 17:00 and 24:00 UTC lands on the
wrong Thai day and nobody notices because the number still *looks* plausible.
So the day→window conversion lives here, alone, with tests.

Why a fixed +07:00 offset instead of `zoneinfo`
-----------------------------------------------
Thailand dropped DST in 1976 and has been a flat UTC+07:00 ever since, so a
constant offset is exactly correct for every date this report can be asked
about. It also avoids depending on the IANA tz database being present in the
Lambda runtime image.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Tuple

#: Asia/Bangkok is a fixed UTC+07:00 (no DST since 1976).
BKK_OFFSET = timedelta(hours=7)

#: Format accepted by the API for the optional `date` parameter.
DAY_FORMAT = '%Y-%m-%d'


def _utc_now_naive() -> datetime:
    """Current UTC instant as a *naive* datetime.

    Naive on purpose: it has to be comparable with `transaction_date`, which
    is stored without a tzinfo. `datetime.utcnow()` would do the same thing
    but is deprecated from Python 3.12, so build it explicitly instead.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_to_bkk_date(moment_utc: datetime) -> date:
    """Which Thai calendar day does this UTC instant fall on?

    This is the whole 7-hour bug in one function, so it is separated out to be
    testable without mocking the clock.
    """
    return (moment_utc + BKK_OFFSET).date()


def bkk_today() -> date:
    """Today's date in Asia/Bangkok."""
    return utc_to_bkk_date(_utc_now_naive())


def bkk_day_to_utc_window(day: date) -> Tuple[datetime, datetime]:
    """Half-open UTC window `[start, end)` covering the Thai calendar day.

    e.g. 2026-07-26 → (2026-07-25 17:00, 2026-07-26 17:00)

    Half-open on purpose: a reading at exactly 17:00:00 UTC belongs to the
    *next* Thai day. A closed upper bound would double-count it.
    """
    start_local = datetime(day.year, day.month, day.day)
    start_utc = start_local - BKK_OFFSET
    return start_utc, start_utc + timedelta(days=1)


def parse_day(value) -> date:
    """Parse the API's optional `date` parameter, defaulting to today (Bangkok).

    Raises:
        ValueError: if *value* is a non-empty string that isn't `YYYY-MM-DD`.
            Callers translate this into a 422.
    """
    if value is None or value == '':
        return bkk_today()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return datetime.strptime(str(value), DAY_FORMAT).date()
