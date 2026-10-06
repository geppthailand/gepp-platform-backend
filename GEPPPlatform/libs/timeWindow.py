"""
Time-of-day window filter ("เวลาเดิมทุกวัน"): keep only rows whose local time of day falls
between two times, on every day of the selected date range — e.g. 10:00–13:00 of 1–15 Jan is
fifteen 3-hour windows, not one span. The date range itself is filtered as before; this is an
extra condition on top of it.

Query params: time_from=HH:MM, time_to=HH:MM, tz=<IANA zone> (the browser's; Asia/Bangkok when
missing or unknown). A window whose end is before its start crosses midnight (22:00–02:00).
The end minute is inclusive (13:00 keeps 13:00:59).

Used by the report queries and the transaction list, on transaction_records.transaction_date
(timestamptz in the database, so the local time needs an explicit AT TIME ZONE).
"""
from __future__ import annotations

import re
from datetime import time
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import Time, and_, cast, func, or_

_HHMM = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')
DEFAULT_TZ = 'Asia/Bangkok'
# Filter keys the window adds; copy these wherever filters are whitelisted.
TIME_WINDOW_KEYS = ('time_from', 'time_to', 'time_tz')


def parse_time_window(params: Dict[str, Any], tz_name: Optional[str] = None) -> Dict[str, str]:
    """{'time_from', 'time_to', 'time_tz'} from request params, or {} when absent / invalid.
    A full-day window (00:00–23:59) is no filter at all and also returns {}."""
    tf = str(params.get('time_from') or '').strip()
    tt = str(params.get('time_to') or '').strip()
    if not (_HHMM.match(tf) and _HHMM.match(tt)):
        return {}
    if tf == '00:00' and tt == '23:59':
        return {}
    tz = str(params.get('tz') or tz_name or DEFAULT_TZ)
    try:
        ZoneInfo(tz)
    except Exception:
        tz = DEFAULT_TZ
    return {'time_from': tf, 'time_to': tt, 'time_tz': tz}


def has_time_window(filters: Optional[Dict[str, Any]]) -> bool:
    return bool(filters and filters.get('time_from') and filters.get('time_to'))


def time_window_clause(column, filters: Optional[Dict[str, Any]]):
    """SQLAlchemy condition for the window on a timestamptz column, or None without a window."""
    if not has_time_window(filters):
        return None
    h1, m1 = (int(x) for x in str(filters['time_from']).split(':'))
    h2, m2 = (int(x) for x in str(filters['time_to']).split(':'))
    start, end = time(h1, m1), time(h2, m2, 59, 999999)
    local_time = cast(func.timezone(filters.get('time_tz') or DEFAULT_TZ, column), Time)
    if start <= end:
        return and_(local_time >= start, local_time <= end)
    return or_(local_time >= start, local_time <= end)   # crosses midnight


def apply_time_window(query, column, filters: Optional[Dict[str, Any]]):
    """query.filter(window) when a window is set; the query unchanged otherwise."""
    clause = time_window_clause(column, filters)
    return query.filter(clause) if clause is not None else query
