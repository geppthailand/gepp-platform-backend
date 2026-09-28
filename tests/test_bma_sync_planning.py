"""What the cron decides to send, before it sends anything.

These planners exist because of one measurement: a `values.get` of a SINGLE ROW
of this workbook took **203 seconds**, while `spreadsheets.get` for tab metadata
— which serves no cell values — answered in 0.56 s. The cost is per values call,
driven by Sheets recalculating ~450,000 formula cells in the `Master-*` tabs
before it will answer, and it barely moves with payload size.

So the cron was rebuilt around two rules, and both live here rather than in the
I/O layer so they can be tested without a sheet:

* **no `clear()`** — a shrinking block is blanked inside the rectangle it is
  written to, trading free cells for an expensive round trip;
* **only changed rows** — `Origin` is 3,855 rows and this service owns ~154 of
  them; restating the other 3,700 back to the sheet every week is the entire
  payload for none of the value.
"""

from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
    SHEET_COLUMNS,
    BMAGSheetService,
)

NC = len(SHEET_COLUMNS)


def row(year, county, marker=0.0):
    r = {c: 0.0 for c in SHEET_COLUMNS}
    r.update({'Month': 1, 'Year': year, 'County': county,
              'all waste': marker, 'origin': '1'})
    return r


def sheet_row(year, county, marker='0'):
    r = [''] * NC
    r[0], r[1], r[2], r[10] = '1', str(year), county, marker
    return r


class TestPlanAllData:
    def _svc(self):
        return BMAGSheetService(None)

    def test_scoped_years_are_replaced_and_others_kept(self):
        existing = [sheet_row(2023, 'County01', '111'),
                    sheet_row(2026, 'County01', '222')]
        writes, s = self._svc().plan_all_data(
            [row(2026, 'County01', 999.0)], existing, replace_years=[2026])
        assert s['rows_kept'] == 1 and s['rows_written'] == 1
        (_rng, values), = writes
        assert values[0][1] == '2023'            # the 2023 row survived
        assert values[1][10] == 999.0            # 2026 came from the build

    def test_no_clear_is_needed_because_the_tail_is_blanked(self):
        # Three rows in the sheet, one row of output: the two vacated rows are
        # blanked inside the same rectangle instead of by a second call.
        existing = [sheet_row(2026, 'County01'), sheet_row(2026, 'County02'),
                    sheet_row(2026, 'County03')]
        writes, s = self._svc().plan_all_data(
            [row(2026, 'County01')], existing, replace_years=[2026])
        (rng, values), = writes
        assert s['rows_blanked'] == 2
        assert len(values) == 3
        assert values[1] == [''] * NC and values[2] == [''] * NC
        assert rng.endswith('T5')                # rows 3..5, one rectangle

    def test_a_growing_dataset_blanks_nothing(self):
        writes, s = self._svc().plan_all_data(
            [row(2026, 'County01'), row(2026, 'County02')],
            [sheet_row(2026, 'County01')], replace_years=[2026])
        assert s['rows_blanked'] == 0
        assert len(writes[0][1]) == 2

    def test_replace_all_ignores_what_was_there(self):
        writes, s = self._svc().plan_all_data(
            [row(2026, 'County01')],
            [sheet_row(2023, 'County09')], replace_years=None)
        assert s['replaced_years'] == 'all' and s['rows_kept'] == 0
        assert writes[0][1][0][1] == 2026

    def test_ragged_rows_read_back_are_padded(self):
        # The API right-trims empty trailing cells, so a kept row comes back
        # short; sent back short it would read as ragged.
        short = ['1', '2023', 'County01']
        writes, _ = self._svc().plan_all_data(
            [row(2026, 'County01')], [short], replace_years=[2026])
        assert all(len(r) == NC for r in writes[0][1])

    def test_blank_existing_rows_are_not_counted_as_data(self):
        writes, s = self._svc().plan_all_data(
            [row(2026, 'County01')], [[''] * NC, ['  ']], replace_years=[2026])
        assert s['rows_kept'] == 0
        assert len(writes[0][1]) == 1


class TestPlanOriginWrites:
    plan = staticmethod(BMAGSheetService.plan_origin_writes)

    def test_an_unchanged_tab_sends_nothing(self):
        rows = [['a', 'b'], ['c', 'd']]
        writes, s = self.plan(rows, rows, 2)
        assert writes == [] and s['origin_rows_rewritten'] == 0
        assert s['origin_write_mode'] == 'diff'

    def test_only_the_changed_row_is_sent(self):
        old = [['a', '1'], ['b', '2'], ['c', '3']]
        new = [['a', '1'], ['b', 'CHANGED'], ['c', '3']]
        writes, s = self.plan(old, new, 2)
        assert s['origin_rows_rewritten'] == 1
        (rng, values), = writes
        assert rng.endswith('!A4:B4') and values == [['b', 'CHANGED']]

    def test_adjacent_changes_become_one_range(self):
        old = [['a'], ['b'], ['c'], ['d']]
        new = [['a'], ['X'], ['Y'], ['d']]
        writes, s = self.plan(old, new, 1)
        assert len(writes) == 1 and s['origin_write_ranges'] == 1
        assert writes[0][0].endswith('!A4:A5')

    def test_separated_changes_stay_separate_ranges(self):
        old = [['a'], ['b'], ['c'], ['d']]
        new = [['X'], ['b'], ['c'], ['Y']]
        writes, _ = self.plan(old, new, 1)
        assert [r.split('!')[1] for r, _ in writes] == ['A3:A3', 'A6:A6']

    def test_appended_rows_are_sent(self):
        writes, s = self.plan([['a']], [['a'], ['b']], 1)
        assert s['origin_rows_rewritten'] == 1
        assert writes[0][0].endswith('!A4:A4')

    def test_a_removal_rewrites_only_from_the_removed_row_down(self):
        # Rows below a deletion shift up, so a positional diff is meaningless
        # from there — but rows ABOVE it are still aligned and must not be
        # resent. The vacated last row must not keep its old contents.
        old = [['a'], ['b'], ['c']]
        new = [['a'], ['c']]
        writes, s = self.plan(old, new, 1, shifted_from=1)
        assert s['origin_write_mode'] == 'shift'
        assert s['origin_shift_from_row'] == 4        # 'a' at row 3 untouched
        (rng, values), = writes
        assert values == [['c'], ['']]
        assert rng.endswith('!A4:A5')

    def test_a_removal_near_the_bottom_sends_only_the_tail(self):
        # The real case: 3,855 rows, the self-heal drops row 3,839. Rewriting
        # everything would send 3,855 rows to fix 17.
        old = [[str(i)] for i in range(100)]
        new = [[str(i)] for i in range(100) if i != 97]
        writes, s = self.plan(old, new, 1, shifted_from=97)
        assert s['origin_shift_from_row'] == 3 + 97
        assert s['origin_rows_rewritten'] == 3         # 98, 99, and one blank
        assert len(writes) == 1

    def test_rows_above_a_removal_that_also_changed_are_still_sent(self):
        old = [['a'], ['b'], ['c'], ['d']]
        new = [['A'], ['b'], ['d']]
        writes, s = self.plan(old, new, 1, shifted_from=2)
        assert s['origin_write_mode'] == 'shift'
        ranges = [r.split('!')[1] for r, _ in writes]
        assert ranges == ['A3:A3', 'A5:A6']            # the edit, then the tail

    def test_numbers_and_their_string_form_are_not_a_change(self):
        # The sheet returns everything as text; the builder puts numbers back.
        # Treating 9161 and '9161' as different would rewrite all 3,855 rows
        # every week and defeat the whole optimisation.
        writes, s = self.plan([['9161', ' x ']], [[9161, 'x']], 2)
        assert writes == [] and s['origin_rows_rewritten'] == 0

    def test_short_rows_are_padded_before_comparing(self):
        writes, _ = self.plan([['a']], [['a', '']], 2)
        assert writes == []


class TestProgressNeverBreaksTheJob:
    def test_step_and_timed_are_safe(self):
        from GEPPPlatform.services.integrations.bma import progress as P
        P.reset()
        P.step('stage', 'detail')
        with P.timed('thing'):
            pass
        assert P.elapsed() >= 0

    def test_timed_reports_the_failure_and_re_raises(self):
        from GEPPPlatform.services.integrations.bma import progress as P
        import pytest
        P.reset()
        with pytest.raises(ValueError):
            with P.timed('boom'):
                raise ValueError('nope')

    def test_cells_counts_a_write_plan(self):
        from GEPPPlatform.services.integrations.bma import progress as P
        assert P.cells([('a', [[1, 2, 3], [4, 5, 6]]), ('b', [[7]])]) == 7
