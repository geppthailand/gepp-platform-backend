"""Daily time window ("เวลาเดิมทุกวัน") — params parsing and the SQL condition."""
from sqlalchemy import Column, DateTime, MetaData, Table, select
from sqlalchemy.dialects import postgresql

from GEPPPlatform.libs.timeWindow import apply_time_window, has_time_window, parse_time_window, time_window_clause

_t = Table('t', MetaData(), Column('ts', DateTime(timezone=True)))


def _sql(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))


def test_parse_valid_window_with_browser_zone():
    assert parse_time_window({'time_from': '10:00', 'time_to': '13:30', 'tz': 'Asia/Bangkok'}) == {
        'time_from': '10:00', 'time_to': '13:30', 'time_tz': 'Asia/Bangkok'}


def test_parse_falls_back_to_bangkok_for_unknown_zone_and_uses_handler_zone():
    assert parse_time_window({'time_from': '10:00', 'time_to': '13:00', 'tz': 'Mars/Base'})['time_tz'] == 'Asia/Bangkok'
    assert parse_time_window({'time_from': '10:00', 'time_to': '13:00'}, 'Asia/Tokyo')['time_tz'] == 'Asia/Tokyo'


def test_parse_rejects_bad_or_missing_values_and_full_day():
    assert parse_time_window({}) == {}
    assert parse_time_window({'time_from': '10:00'}) == {}
    assert parse_time_window({'time_from': '24:00', 'time_to': '13:00'}) == {}
    assert parse_time_window({'time_from': "10:00'; drop table x;--", 'time_to': '13:00'}) == {}
    assert parse_time_window({'time_from': '00:00', 'time_to': '23:59'}) == {}   # whole day = no filter


def test_clause_is_none_without_window():
    assert time_window_clause(_t.c.ts, None) is None
    assert time_window_clause(_t.c.ts, {'date_from': 'x'}) is None
    assert not has_time_window({'time_from': '10:00'})


def test_same_day_window_is_an_inclusive_range_in_local_time():
    sql = _sql(time_window_clause(_t.c.ts, {'time_from': '10:00', 'time_to': '13:00', 'time_tz': 'Asia/Bangkok'}))
    assert "timezone('Asia/Bangkok', t.ts)" in sql
    assert ">= '10:00:00'" in sql and "<= '13:00:59.999999'" in sql
    assert ' AND ' in sql


def test_window_crossing_midnight_uses_or():
    sql = _sql(time_window_clause(_t.c.ts, {'time_from': '22:00', 'time_to': '02:00', 'time_tz': 'Asia/Bangkok'}))
    assert ">= '22:00:00'" in sql and "<= '02:00:59.999999'" in sql
    assert ' OR ' in sql


def test_apply_leaves_query_alone_without_window():
    q = select(_t.c.ts)
    assert apply_time_window(q, _t.c.ts, {}) is q
    assert 'WHERE' in _sql(apply_time_window(q, _t.c.ts, {'time_from': '10:00', 'time_to': '11:00'}))
