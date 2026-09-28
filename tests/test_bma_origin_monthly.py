"""The `[Origin] <category>` tabs — row order and what is allowed to be written.

Ops keeps spreadsheet formulas in column D (`baseline`) and those formulas
address rows by position. Two invariants follow, and they are the reason this
module exists rather than being covered by a smoke test:

  * **no written range may include column D** — on any row, header included;
  * **rows are append-only** — an origin keeps the row it first got, forever,
    whatever happens to it in the database.

Both are cheap to break with a well-meaning refactor ("just write whole rows",
"sort by name so it reads nicely") and expensive to notice, because the numbers
would still look right while every baseline pointed one row off.
"""

import datetime as dt
import re

import pytest

from GEPPPlatform.services.integrations.bma.bma_origin_monthly_service import (
    CATEGORY_COLUMNS,
    COL_BASELINE,
    FIXED_COLUMNS,
    TAB_FOR_COLUMN,
    BMAOriginMonthlyService as S,
    months_between,
)

ORIGINS = {
    11: ('Head office', ''),
    22: ('Floor 6', 'Head office > Tower A'),
    33: ('Canteen', 'Head office > Tower A > Floor 6'),
}
MONTHS = ['2023-01', '2023-02', '2023-03']


def ranges(writes):
    return [rng for rng, _ in writes]


def columns_touched(a1):
    """The set of column letters a written A1 range spans."""
    body = a1.split('!', 1)[1]
    start, end = (body.split(':') + [body])[:2]
    first = re.match(r'([A-Z]+)', start).group(1)
    last = re.match(r'([A-Z]+)', end).group(1)

    def n(letters):
        v = 0
        for ch in letters:
            v = v * 26 + (ord(ch) - 64)
        return v

    return set(range(n(first), n(last) + 1))


class TestMonthsBetween:
    def test_inclusive_at_both_ends(self):
        got = months_between(dt.date(2023, 1, 1), dt.date(2023, 3, 20))
        assert got == ['2023-01', '2023-02', '2023-03']

    def test_crosses_the_year_boundary(self):
        got = months_between(dt.date(2023, 11, 1), dt.date(2024, 2, 1))
        assert got == ['2023-11', '2023-12', '2024-01', '2024-02']

    def test_single_month(self):
        assert months_between(dt.date(2026, 9, 1), dt.date(2026, 9, 30)) == ['2026-09']

    def test_history_grows_monotonically(self):
        # The write rectangle only ever extends to the right. If this ever
        # shrank, last month's column would be left holding stale numbers.
        a = months_between(dt.date(2023, 1, 1), dt.date(2026, 8, 1))
        b = months_between(dt.date(2023, 1, 1), dt.date(2026, 9, 1))
        assert b[:len(a)] == a and len(b) == len(a) + 1


class TestMergeOrderIsAppendOnly:
    def test_fresh_tab_takes_everything_in_id_order(self):
        order, stats = S.merge_order([], ORIGINS)
        assert order == [11, 22, 33]
        assert stats['rows_appended'] == 3
        assert stats['rows_existing'] == 0

    def test_existing_rows_keep_their_position(self):
        # Deliberately not in id order: whatever order the sheet is in wins.
        order, stats = S.merge_order(['33', '11'], ORIGINS)
        assert order == [33, 11, 22]
        assert stats['rows_appended'] == 1

    def test_an_origin_with_no_data_keeps_its_row(self):
        # 99 has gone quiet — it must still hold row 3, reading zero, or every
        # baseline below it shifts up one.
        order, _ = S.merge_order(['11', '99', '22'], ORIGINS)
        assert order == [11, 99, 22, 33]

    def test_unrecognised_rows_are_placeholders_not_overwrites(self):
        order, stats = S.merge_order(['11', 'TOTAL', '22'], ORIGINS)
        assert order == [11, None, 22, 33]
        assert stats['rows_unrecognised'] == 1

    def test_a_duplicated_id_is_maintained_only_at_its_first_row(self):
        # Writing both copies would put the same series against two different
        # formulas, silently double-counting whatever sums them.
        order, stats = S.merge_order(['11', '11'], ORIGINS)
        assert order == [11, None, 22, 33]
        assert stats['rows_unrecognised'] == 1

    def test_rerunning_against_its_own_output_changes_nothing(self):
        order, _ = S.merge_order([], ORIGINS)
        again, stats = S.merge_order([str(i) for i in order], ORIGINS)
        assert again == order
        assert stats['rows_appended'] == 0

    def test_blank_trailing_cells_do_not_become_rows(self):
        order, _ = S.merge_order(['11', '', '  '], ORIGINS)
        assert order[:1] == [11]
        assert order[-2:] == [22, 33]


class TestRunsSkipForeignRows:
    def test_no_foreign_rows_is_one_run(self):
        assert S._runs([11, 22, 33]) == [(0, [11, 22, 33])]

    def test_a_foreign_row_splits_the_rectangle(self):
        assert S._runs([11, None, 22, 33]) == [(0, [11]), (2, [22, 33])]

    def test_leading_and_trailing_foreign_rows(self):
        assert S._runs([None, 11, None]) == [(1, [11])]

    def test_all_foreign_writes_nothing(self):
        assert S._runs([None, None]) == []


class TestWritesNeverTouchTheBaselineColumn:
    def _writes(self, order=None, months=None):
        order = [11, 22, 33] if order is None else order
        months = months or MONTHS
        return S.tab_writes('[Origin] general waste', months, ORIGINS,
                            {11: {'2023-01': 5.0}}, order)

    def test_column_d_is_in_no_range(self):
        for rng in ranges(self._writes()):
            assert COL_BASELINE not in columns_touched(rng), rng

    def test_column_d_is_spared_even_around_a_foreign_row(self):
        for rng in ranges(self._writes([11, None, 22])):
            assert COL_BASELINE not in columns_touched(rng), rng

    def test_the_header_write_stops_at_c(self):
        header = ranges(self._writes())[0]
        assert header.endswith('!A1:C1')

    def test_baseline_is_still_declared_in_the_header_constant(self):
        # It is written exactly once, at tab creation, by `_create_tab`.
        assert FIXED_COLUMNS[COL_BASELINE - 1] == 'baseline'

    def test_no_range_is_a_whole_row(self):
        # 'A2:AW2' would sweep D along with everything else.
        assert not any(columns_touched(r) >= {1, 4} for r in ranges(self._writes()))


class TestTabWriteContents:
    def test_month_header_matches_the_month_block_width(self):
        writes = S.tab_writes('t', MONTHS, ORIGINS, {}, [11, 22])
        (_, header), = [(r, v) for r, v in writes if r.endswith('!E1:G1')]
        assert header == [MONTHS]

    def test_missing_months_are_zero_not_blank(self):
        writes = S.tab_writes('t', MONTHS, ORIGINS, {11: {'2023-02': 7.5}}, [11])
        monthly = dict(writes)["'t'!E2:G2"]
        assert monthly == [[0.0, 7.5, 0.0]]

    def test_fixed_columns_are_id_parent_name_in_that_order(self):
        writes = S.tab_writes('t', MONTHS, ORIGINS, {}, [33])
        assert dict(writes)["'t'!A2:C2"] == [
            [33, 'Head office > Tower A > Floor 6', 'Canteen']]

    def test_a_row_for_an_origin_that_vanished_still_reports_zero(self):
        # 99 is not in ORIGINS at all — it must not crash, and must not blank
        # the row, because a blank row reads as "no data collected" rather than
        # "this site stopped".
        writes = dict(S.tab_writes('t', MONTHS, ORIGINS, {}, [99]))
        assert writes["'t'!A2:C2"] == [[99, '', '']]
        assert writes["'t'!E2:G2"] == [[0.0, 0.0, 0.0]]

    def test_row_numbers_follow_the_run_offset(self):
        writes = ranges(S.tab_writes('t', MONTHS, ORIGINS, {}, [11, None, 22]))
        assert "'t'!A2:C2" in writes      # run 1 -> sheet row 2
        assert "'t'!A4:C4" in writes      # run 2 -> sheet row 4, skipping 3

    def test_values_are_rounded_to_grams(self):
        writes = dict(S.tab_writes('t', MONTHS, ORIGINS,
                                   {11: {'2023-01': 1.23456}}, [11]))
        assert writes["'t'!E2:G2"][0][0] == 1.235


class FakeSheets:
    """A Sheets workbook that records what was asked of it.

    Cells are a dict so an assertion can ask "what is in D7 now?" — which is the
    only way to prove the thing that matters: that a baseline someone typed
    survives a run, and the run after that.
    """

    def __init__(self, tabs=None):
        self.cells = {}                      # (tab, row, col) -> value
        self.props = {t: {'sheet_id': i, 'rows': 1000, 'cols': 30}
                      for i, t in enumerate(tabs or [])}
        self.calls = []

    # -- the bits of SheetsClient that `sync` uses ------------------------
    def tab_properties(self, _sheet_id):
        return {t: dict(p) for t, p in self.props.items()}

    def add_tab(self, _sheet_id, title, rows=1000, cols=26):
        self.calls.append(('add_tab', title))
        self.props[title] = {'sheet_id': len(self.props), 'rows': rows, 'cols': cols}
        return dict(self.props[title])

    def resize_tab(self, _sheet_id, tab_sheet_id, rows, cols):
        self.calls.append(('resize', tab_sheet_id, rows, cols))
        for p in self.props.values():
            if p['sheet_id'] == tab_sheet_id:
                p.update(rows=rows, cols=cols)

    def batch_get(self, _sheet_id, ranges):
        return [self._read(r) for r in ranges]

    def _read(self, rng):
        """Mimic the API: rows are right-trimmed, and trailing blanks vanish."""
        tab, body = rng.split('!', 1)
        tab = tab.strip("'")
        start, end = (body.split(':') + [body])[:2]
        c0 = ord(re.match(r'([A-Z]+)', start).group(1)) - 64
        r0 = int(re.search(r'(\d+)', start).group(1))
        c1 = ord(re.match(r'([A-Z]+)', end).group(1)) - 64
        present = [r for (t, r, c) in self.cells if t == tab and r >= r0]
        if not present:
            return []
        out = []
        for r in range(r0, max(present) + 1):
            row = [self.cells.get((tab, r, c), '') for c in range(c0, c1 + 1)]
            while row and row[-1] == '':
                row.pop()
            out.append(row)
        while out and not out[-1]:
            out.pop()
        return out

    def update(self, _sheet_id, rng, values, **_kw):
        self._write(rng, values)

    def batch_update_values(self, _sheet_id, writes, **_kw):
        for rng, values in writes:
            self._write(rng, values)

    # -- helpers ---------------------------------------------------------
    def _write(self, rng, values):
        self.calls.append(('write', rng))
        tab, body = rng.split('!', 1)
        tab = tab.strip("'")
        start = body.split(':')[0]
        col0 = ord(re.match(r'([A-Z]+)', start).group(1)) - 64
        row0 = int(re.search(r'(\d+)', start).group(1))
        for dr, row in enumerate(values):
            for dc, val in enumerate(row):
                self.cells[(tab, row0 + dr, col0 + dc)] = val

    def written_ranges(self):
        return [c[1] for c in self.calls if c[0] == 'write']


class StubService(S):
    """`sync` with the database replaced by a fixed answer."""

    def __init__(self, origins=None, totals=None):
        super().__init__(None)
        self._origins = origins if origins is not None else dict(ORIGINS)
        self._totals = totals or {}

    def build(self, org_id=None, include_shared_history=False, as_of=None):
        totals = {c: dict(self._totals.get(c, {})) for c in CATEGORY_COLUMNS}
        return MONTHS, dict(self._origins), totals, {'origins': len(self._origins)}


@pytest.fixture
def sheets(monkeypatch):
    """Point `sync` at a FakeSheets and away from real credentials."""
    book = FakeSheets()
    import GEPPPlatform.libs.google_sa_auth as auth
    monkeypatch.setattr(auth, 'SheetsClient', lambda *_a, **_k: book)
    monkeypatch.setattr(S, '_load_service_account', staticmethod(lambda: {}))
    return book


class TestSyncEndToEnd:
    def test_first_run_creates_all_seven_tabs(self, sheets):
        StubService().sync(sheet_id='x')
        created = [c[1] for c in sheets.calls if c[0] == 'add_tab']
        assert created == [TAB_FOR_COLUMN[c] for c in CATEGORY_COLUMNS]

    def test_the_created_header_carries_baseline_in_d(self, sheets):
        StubService().sync(sheet_id='x')
        tab = TAB_FOR_COLUMN['general waste']
        assert [sheets.cells[(tab, 1, c)] for c in (1, 2, 3, 4)] == FIXED_COLUMNS
        assert sheets.cells[(tab, 1, 5)] == MONTHS[0]

    def test_a_typed_baseline_survives_the_next_run(self, sheets):
        StubService().sync(sheet_id='x')
        tab = TAB_FOR_COLUMN['general waste']
        # Ops types a formula against row 3 (origin 22).
        sheets.cells[(tab, 3, 4)] = '=AVERAGE(E3:G3)'
        sheets.calls.clear()

        StubService().sync(sheet_id='x')
        assert sheets.cells[(tab, 3, 4)] == '=AVERAGE(E3:G3)'
        assert all(4 not in columns_touched(r) for r in sheets.written_ranges())

    def test_a_new_origin_is_appended_below_without_moving_the_others(self, sheets):
        StubService().sync(sheet_id='x')
        tab = TAB_FOR_COLUMN['general waste']
        sheets.cells[(tab, 3, 4)] = 'baseline for 22'

        grown = dict(ORIGINS)
        grown[5] = ('New site', '')          # a LOWER id than any existing row
        StubService(origins=grown).sync(sheet_id='x')

        ids = [sheets.cells[(tab, r, 1)] for r in range(2, 6)]
        assert ids == [11, 22, 33, 5], 'a new low id must append, not sort in'
        assert sheets.cells[(tab, 3, 4)] == 'baseline for 22'

    def test_an_origin_that_stops_reporting_keeps_its_row_and_reads_zero(self, sheets):
        totals = {'general waste': {11: {'2023-01': 5.0}, 22: {'2023-02': 8.0}}}
        StubService(totals=totals).sync(sheet_id='x')
        tab = TAB_FOR_COLUMN['general waste']
        sheets.cells[(tab, 3, 4)] = 'baseline for 22'

        StubService(totals={'general waste': {11: {'2023-01': 5.0}}}).sync(sheet_id='x')
        assert sheets.cells[(tab, 3, 1)] == 22
        assert [sheets.cells[(tab, 3, c)] for c in (5, 6, 7)] == [0.0, 0.0, 0.0]
        assert sheets.cells[(tab, 3, 4)] == 'baseline for 22'

    def test_rerun_is_idempotent(self, sheets):
        StubService().sync(sheet_id='x')
        first = dict(sheets.cells)
        StubService().sync(sheet_id='x')
        assert sheets.cells == first

    def test_columns_parameter_limits_the_run(self, sheets):
        StubService().sync(sheet_id='x', columns=['general waste'])
        assert [c[1] for c in sheets.calls if c[0] == 'add_tab'] == [
            '[Origin] general waste']

    def test_dry_run_touches_nothing(self, sheets):
        out = StubService().sync(sheet_id='x', dry_run=True)
        assert out['dry_run'] is True
        assert sheets.calls == []

    def test_an_empty_pre_made_tab_still_gets_its_header(self, sheets):
        # All seven tabs were created by hand before this service existed and
        # arrived empty, so "the tab exists" must not be read as "it is set up".
        tab = TAB_FOR_COLUMN['general waste']
        sheets.props[tab] = {'sheet_id': 99, 'rows': 1000, 'cols': 26}

        out = StubService().sync(sheet_id='x', columns=['general waste'])
        assert out['tabs'][tab]['created'] is False
        assert out['tabs'][tab]['header_initialised'] is True
        assert [sheets.cells[(tab, 1, c)] for c in (1, 2, 3, 4)] == FIXED_COLUMNS

    def test_a_narrow_pre_made_tab_is_widened_for_the_months(self, sheets):
        tab = TAB_FOR_COLUMN['general waste']
        sheets.props[tab] = {'sheet_id': 99, 'rows': 1000, 'cols': 4}
        StubService().sync(sheet_id='x', columns=['general waste'])
        assert any(c[0] == 'resize' for c in sheets.calls)
        assert sheets.props[tab]['cols'] >= 4 + len(MONTHS)

    def test_the_header_is_written_once_not_every_run(self, sheets):
        StubService().sync(sheet_id='x', columns=['general waste'])
        second = StubService().sync(sheet_id='x', columns=['general waste'])
        tab = TAB_FOR_COLUMN['general waste']
        assert second['tabs'][tab]['header_initialised'] is False
        assert all(4 not in columns_touched(r) for r in sheets.written_ranges()[-4:])


class TestTabNaming:
    def test_every_category_column_has_a_tab(self):
        assert set(TAB_FOR_COLUMN) == set(CATEGORY_COLUMNS)

    def test_tab_names_are_the_ones_ops_asked_for(self):
        assert TAB_FOR_COLUMN['organic waste'] == '[Origin] organic waste'
        assert TAB_FOR_COLUMN['general waste'] == '[Origin] general waste'

    def test_sync_rejects_an_unknown_column(self):
        with pytest.raises(ValueError, match='unknown category column'):
            S(None).sync(columns=['plastic'])
