"""One read and one write for the whole BMA workbook.

WHY THIS EXISTS
    The three services that feed this workbook each did their own I/O, and
    between them made roughly 25 `values` calls per run: a header read, a data
    read, a clear and a write for `Origin`; the same for `All data-GEPP`; and a
    read plus a write for each of the seven `[Origin] <category>` tabs.

    On this workbook that is fatal, and not for the reason it looks like. The
    payload is small. **A single `values.get` of ONE ROW was measured at 203
    seconds**, while `spreadsheets.get` for tab metadata — which serves no cell
    values — answered in 0.56 s. The difference is recalculation: `Master-GEPP`,
    `Master-District` and `Master-BMA` hold on the order of 450,000 formula
    cells wired to the tabs this cron writes, and Sheets brings them up to date
    before it will serve a value. Every write re-dirties them, so the cost is
    paid per call, over and over, whatever the call asks for.

    So the fix is not a smaller payload, it is fewer calls. This coordinator
    does the whole job in:

        1 x spreadsheets.get        (tab metadata, cheap, no values)
        1 x values.batchGet         (every range every tab needs)
        0-2 x spreadsheets.batchUpdate  (create/resize tabs, only when needed)
        1 x values.batchUpdate      (every range every tab writes)

    Round trips: ~25 -> 3. `clear()` is gone entirely — a shrinking block is
    blanked inside the same rectangle it is written to, which costs cells
    (free) instead of a round trip (expensive).

PROGRESS
    Every step prints, with flush, through `progress` — see that module for why
    `print` and not `logging`. A run that is going to blow the Lambda timeout is
    exactly the run whose final summary never arrives, and "which step was it on
    at minute 9" is the only question worth answering then.
"""

import os

from GEPPPlatform.libs.google_sa_auth import SheetsClient, column_letter
from GEPPPlatform.services.integrations.bma import progress as P
from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
    DEFAULT_SHEET_ID,
    DEFAULT_START_ROW,
    DEFAULT_TAB,
    ORG_ID,
    ORIGIN_HEADER_ROW,
    ORIGIN_LOCATION_ID,
    ORIGIN_ADDED_ON,
    ORIGIN_TAB,
    OVERALL_TAB,
    REPLACE_ALL,
    default_managed_years,
    origin_column_map,
)
from GEPPPlatform.services.integrations.bma.bma_origin_monthly_service import (
    CATEGORY_COLUMNS,
    FIXED_COLUMNS,
    HEADER_ROW,
    NEW_TAB_COLS,
    NEW_TAB_ROWS,
    START_ROW,
    TAB_FOR_COLUMN,
    BMAOriginMonthlyService,
)


#: How far down each tab the read goes.
#:
#: A range is bounded by the GRID, not by the data, and these grids are mostly
#: empty: `All data-GEPP` is 50,500 rows tall and holds 592 of data, so
#: `A3:T50500` asked Google for 1,009,940 cells to retrieve 11,840. Across the
#: whole batchGet, **90.6% of what was requested was blank rows** — and on
#: 2026-09-28 that request stopped being merely wasteful and started coming back
#: `HTTP 503: The service is currently unavailable` after 372 s. Too big to
#: serve is a different failure from slow, and it is not fixed by waiting.
#:
#: The numbers are headroom, not guesses: `All data-GEPP` grows ~130 rows a year
#: (130 were written the run this was measured on), so 5,000 is about 30 years.
#: Saturation is checked after the read and is a hard error, never a silent
#: truncation — see `_check_read_extent`.
MAX_ALLDATA_ROWS = 5000
MAX_ORIGIN_ROWS = 20000
MAX_TAB_ROWS = 4000


class BMASheetSync:
    """Plans every tab against the database, then talks to Google once."""

    def __init__(self, db, sheet_id=None):
        self.db = db
        self.sheet_id = sheet_id or os.environ.get('BMA_GSHEET_ID',
                                                   DEFAULT_SHEET_ID)
        # One service instance for the whole run, so the memoised district /
        # org-chart / share maps are computed once and shared by all three tabs.
        self.svc = BMAOriginMonthlyService(db)

    # ── the plan ─────────────────────────────────────────────────────────

    def run(self, org_id=ORG_ID, year_from=None, replace_years=None,
            dry_run=False, include_shared_history=False,
            skip_origin=False, skip_origin_monthly=False,
            origin_monthly_columns=None, prepare_only=False):
        P.reset()
        svc = self.svc
        result = {'sheet_id': self.sheet_id, 'dry_run': bool(dry_run)}

        # ---- 1. database: everything computed before a single byte moves ----
        replace_years = self._scope_years(replace_years, result)

        with P.timed('db.all-data', 'month x เขต'):
            rows, stats = svc.build_rows(org_id, year_from, include_shared_history)
        result.update(stats)
        P.step('db.all-data', f"{len(rows)} rows, coverage {stats['coverage_pct']}%")

        monthly = None
        if not skip_origin_monthly:
            with P.timed('db.origin-monthly', 'origin x month x 7 categories'):
                months, origins, totals, mstats = svc.build(
                    org_id, include_shared_history)
            monthly = (months, origins, totals)
            result['origin_monthly'] = dict(mstats)
            P.step('db.origin-monthly',
                   f"{mstats['origins']} origins x {mstats['months']} months, "
                   f"{mstats['shared_descendants_folded']} shared children folded")

        # ---- 2. tab metadata (cheap: serves no cell values) ----------------
        client = None if dry_run else SheetsClient(svc._load_service_account())
        if dry_run:
            P.step('sheets', 'dry run — no calls')
            return self._finish(result, [], None)

        with P.timed('sheets.tabs', 'spreadsheets.get'):
            props = client.tab_properties(self.sheet_id)

        wanted = list(origin_monthly_columns or CATEGORY_COLUMNS)
        # Grid preparation happens FIRST, before the expensive read.
        #
        # It was at the end, on the assumption that a structural call is cheap
        # because it serves no cell values. **That assumption is wrong and cost
        # a whole Lambda invocation**: growing a grid on this workbook makes
        # every `Master-*` formula that references the widened range dirty, and
        # the observed `updateSheetProperties` for seven tabs hung for 622 s and
        # then timed out — after the 172 s read had already been paid for and
        # thrown away. Doing it first means a slow resize fails before the run
        # has spent anything, and `prepare_tabs` lets it be done once, alone.
        created, resized = self._prepare_tabs(
            client, props, wanted, monthly, skip_origin_monthly)
        result['tabs_created'] = sorted(created)
        result['tabs_resized'] = resized
        if prepare_only:
            P.step('prepare-only', 'grid ready; no values written')
            return self._finish(result, [], None)

        # ---- 3. ONE batchGet for every range every tab needs ---------------
        reads, plan = self._read_ranges(props, wanted, skip_origin,
                                        skip_origin_monthly, created)
        with P.timed('sheets.read', f'values.batchGet, {len(reads)} ranges'):
            got = client.batch_get(self.sheet_id, reads) if reads else []
        data = dict(zip(reads, got))
        self._check_read_extent(data, plan)

        # ---- 4. build every write ------------------------------------------
        writes = []
        with P.timed('plan', 'building write ranges'):
            writes += self._plan_all_data(svc, rows, data, plan, replace_years,
                                          result)
            if not skip_origin:
                writes += self._plan_origin(svc, org_id, data, plan, result,
                                            include_shared_history)
            if monthly is not None:
                writes += self._plan_monthly(svc, monthly, data, plan,
                                             wanted, result)
        P.step('plan', f'{len(writes)} ranges, {P.human(P.cells(writes))} cells')

        # ---- 5. ONE batchUpdate --------------------------------------------
        if writes:
            with P.timed('sheets.write',
                         f'values.batchUpdate, {len(writes)} ranges'):
                client.batch_update_values(self.sheet_id, writes)
        else:
            P.step('sheets.write', 'nothing to write')
        return self._finish(result, writes, None)

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _finish(result, writes, _):
        result['write_ranges'] = len(writes)
        result['write_cells'] = P.cells(writes)
        result['seconds'] = round(P.elapsed(), 1)
        P.step('done', f"{result['seconds']}s total")
        return result

    def _scope_years(self, replace_years, result):
        from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
            MANAGED_FROM_YEAR)
        if replace_years == REPLACE_ALL:
            return None
        if replace_years is None:
            replace_years = default_managed_years()
        requested = {int(y) for y in replace_years}
        allowed = sorted(y for y in requested if y >= MANAGED_FROM_YEAR)
        refused = sorted(requested - set(allowed))
        if refused:
            P.step('scope', f'refusing years {refused} (managed from '
                            f'{MANAGED_FROM_YEAR})')
            result['refused_years'] = refused
        return allowed

    def _prepare_tabs(self, client, props, wanted, monthly,
                      skip_origin_monthly):
        """Create and widen the `[Origin]` tabs so the values write fits.

        Returns ``(created, resized)``. Both are structural
        (`spreadsheets.batchUpdate`) and both are batched into a single call —
        but "structural" does NOT mean "cheap" on this workbook, so this runs
        before anything expensive rather than after it.

        The grid only needs to grow when the months outrun it, which is once
        every 26 columns — roughly every two years — plus the first run, where
        the seven hand-made tabs arrive 26 columns wide and need 49. After that
        this is a no-op and costs nothing.
        """
        if skip_origin_monthly or monthly is None:
            return set(), []
        months, origins, _ = monthly
        need_cols = max(len(FIXED_COLUMNS) + len(months), len(FIXED_COLUMNS))
        need_rows = START_ROW + len(origins)

        missing = [TAB_FOR_COLUMN[c] for c in wanted
                   if TAB_FOR_COLUMN[c] not in props]
        requests, created = [], set()
        for title in missing:
            created.add(title)
            requests.append({'addSheet': {'properties': {
                'title': title,
                'gridProperties': {'rowCount': max(need_rows, NEW_TAB_ROWS),
                                   'columnCount': max(need_cols, NEW_TAB_COLS)}}}})

        resized = []
        for col in wanted:
            tab = TAB_FOR_COLUMN[col]
            info = props.get(tab)
            if not info:
                continue
            rows_ = max(info['rows'], need_rows)
            cols_ = max(info['cols'], need_cols)
            if rows_ == info['rows'] and cols_ == info['cols']:
                continue
            resized.append(tab)
            requests.append({'updateSheetProperties': {
                'properties': {'sheetId': info['sheet_id'],
                               'gridProperties': {'rowCount': rows_,
                                                  'columnCount': cols_}},
                'fields': 'gridProperties.rowCount,gridProperties.columnCount'}})
            info.update(rows=rows_, cols=cols_)

        if not requests:
            P.step('sheets.prepare', 'grid already big enough')
            return created, resized

        with P.timed('sheets.prepare',
                     f'{len(missing)} created, {len(resized)} widened '
                     f'-> {need_cols} cols x {need_rows} rows'):
            resp = client.batch_update(self.sheet_id, requests)
        for title, reply in zip(missing, resp.get('replies') or []):
            pr = (reply.get('addSheet') or {}).get('properties') or {}
            grid = pr.get('gridProperties') or {}
            props[title] = {'sheet_id': pr.get('sheetId'),
                            'rows': grid.get('rowCount', need_rows),
                            'cols': grid.get('columnCount', need_cols)}
        return created, resized

    def _read_ranges(self, props, wanted, skip_origin, skip_origin_monthly,
                     created):
        """Every range the run needs, as one flat list."""
        reads, plan = [], {}

        grid = props.get(DEFAULT_TAB) or {}
        last = min(grid.get('rows') or MAX_ALLDATA_ROWS, MAX_ALLDATA_ROWS)
        plan['alldata'] = f"'{DEFAULT_TAB}'!A{DEFAULT_START_ROW}:T{last}"
        plan['alldata_bound'] = last
        reads.append(plan['alldata'])

        if not skip_origin:
            g = props.get(ORIGIN_TAB) or {}
            col = column_letter(max(g.get('cols') or 14, 1))
            last = min(g.get('rows') or MAX_ORIGIN_ROWS, MAX_ORIGIN_ROWS)
            plan['origin_header'] = f"'{ORIGIN_TAB}'!A{ORIGIN_HEADER_ROW}:{col}{ORIGIN_HEADER_ROW}"
            plan['origin_data'] = f"'{ORIGIN_TAB}'!A{DEFAULT_START_ROW}:{col}{last}"
            plan['origin_bound'] = last
            reads += [plan['origin_header'], plan['origin_data']]

        if not skip_origin_monthly:
            for col in wanted:
                tab = TAB_FOR_COLUMN[col]
                if tab in created:
                    continue          # brand new: nothing to read back
                last = min((props.get(tab) or {}).get('rows') or MAX_TAB_ROWS,
                           MAX_TAB_ROWS)
                plan[('tab_header', tab)] = f"'{tab}'!A{HEADER_ROW}:D{HEADER_ROW}"
                plan[('tab_ids', tab)] = f"'{tab}'!A{START_ROW}:A{last}"
                reads += [plan[('tab_header', tab)], plan[('tab_ids', tab)]]
        return reads, plan

    @staticmethod
    def _check_read_extent(data, plan):
        """Refuse to plan from a read that may have been cut short.

        The bounds above are generous, but "generous" is an assumption with a
        date on it. If a tab ever fills its bound, the rows past it were never
        read — and because both `All data-GEPP` and `Origin` are rewritten as a
        block with the tail blanked, planning from a short read would DELETE the
        rows it could not see. Failing loudly is the only safe answer; raising
        the constant is a one-line fix once someone has looked.
        """
        for key, bound_key, name in (('alldata', 'alldata_bound', DEFAULT_TAB),
                                     ('origin_data', 'origin_bound', ORIGIN_TAB)):
            rng, bound = plan.get(key), plan.get(bound_key)
            if not rng or not bound:
                continue
            got = len(data.get(rng) or [])
            capacity = bound - DEFAULT_START_ROW + 1
            if got >= capacity:
                raise RuntimeError(
                    f"'{name}' filled the read bound ({got} rows at row "
                    f"{bound}); rows below it were not read and would be blanked. "
                    f"Raise the bound in bma_sync_service and re-run.")
            P.step('sheets.read', f'{name}: {got} rows (bound {capacity})')

    def _plan_all_data(self, svc, rows, data, plan, replace_years, result):
        existing = data.get(plan['alldata'], [])
        if replace_years:
            years = {int(y) for y in replace_years}
            scoped = [r for r in rows if r['Year'] in years]
            result['rows_in_scope'] = len(scoped)
            if not scoped:
                # Better a loud no-op than clearing a year because its data has
                # not landed yet.
                P.step('plan.all-data',
                       f'nothing built for {sorted(years)} — leaving the tab alone')
                result['skipped_all_data'] = 'no rows in scope'
                return []
        writes, summary = svc.plan_all_data(rows, existing,
                                            replace_years=replace_years)
        result.update(summary)
        P.step('plan.all-data', f"kept {summary['rows_kept']}, wrote "
                                f"{summary['rows_written']}, blanked "
                                f"{summary['rows_blanked']}")
        return writes

    def _plan_origin(self, svc, org_id, data, plan, result,
                     include_shared_history):
        header = (data.get(plan['origin_header']) or [[]])
        header = header[0] if header else []
        colmap = origin_column_map(header)
        width = len(header)
        for name in (ORIGIN_LOCATION_ID, ORIGIN_ADDED_ON):
            if name not in colmap:
                colmap[name] = width
                width += 1
        existing_raw = data.get(plan['origin_data'], [])
        existing = [r for r in existing_raw if r and str(r[0]).strip()]

        rows, stats = svc.build_origin_rows(
            existing, org_id, include_shared_history=include_shared_history,
            colmap=colmap, width=width)
        baseline_t, landfill_t = svc.overall_from_origin(rows, colmap)
        writes, wstats = svc.plan_origin_writes(
            existing, rows, width,
            shifted_from=stats['origin_first_removed_index'])
        writes.append((f"'{OVERALL_TAB}'!A{DEFAULT_START_ROW}",
                       [[baseline_t, landfill_t]]))
        stats.update(wstats)
        stats.update({'overall_baseline_tonne': baseline_t,
                      'overall_landfill_reduction_tonne': landfill_t,
                      'origin_columns': width,
                      'origin_location_id_column': column_letter(
                          colmap[ORIGIN_LOCATION_ID] + 1)})
        result['origin'] = stats
        P.step('plan.origin',
               f"{wstats['origin_write_mode']}: {wstats['origin_rows_rewritten']} "
               f"of {stats['origin_rows_total']} rows")
        return writes

    def _plan_monthly(self, svc, monthly, data, plan, wanted, result):
        """Write ranges for the seven tabs. The grid they need was already
        created and widened by `_prepare_tabs`, before the read."""
        months, origins, totals = monthly
        writes = []
        tabs = result.setdefault('origin_monthly', {}).setdefault('tabs', {})
        for col in wanted:
            tab = TAB_FOR_COLUMN[col]
            header = data.get(plan.get(('tab_header', tab)), [])
            ids = data.get(plan.get(('tab_ids', tab)), [])
            first_column = [(r[0] if r else '') for r in ids]
            if svc._needs_header(header):
                writes.append((f"'{tab}'!A{HEADER_ROW}", [FIXED_COLUMNS]))
            order, tstats = svc.merge_order(first_column, origins)
            writes += svc.tab_writes(tab, months, origins, totals[col], order)
            tstats['kg'] = round(sum(v for m in totals[col].values()
                                     for v in m.values()), 2)
            tabs[tab] = tstats
        P.step('plan.origin-monthly', f'{len(wanted)} tabs')
        return writes
