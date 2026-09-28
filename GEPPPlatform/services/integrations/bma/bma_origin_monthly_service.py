"""Per-origin monthly weight, one tab per material category.

WHAT IT WRITES
    Seven tabs — `[Origin] organic waste`, `[Origin] recycled materials`, …,
    `[Origin] general waste` — one per category column of `All data-GEPP`. Each
    has the same shape:

        A  location id       the v3 `user_locations.id`
        B  location parent   'branch > building > floor', from the org chart
        C  location name
        D  baseline          NEVER WRITTEN — reserved for the sheet's own formulas
        E… monthly kg        2023-01 onwards, 0 where a month has no data

    Rows are origins: every location in org 67 (or shared into it) that carries
    at least one transaction record. No roll-up — unlike the `Origin` tab, a
    floor gets its own row, because this is the collection-level detail view.

WHY D IS SACRED
    Ops puts spreadsheet formulas in `baseline` and those formulas address rows
    by position. Two consequences run through the whole module:

      * **column D is never in a written range.** Not on the data rows, not even
        on the header — the header cell is written once, when the tab is
        created, and never again. Splitting the write into A:C and E:… is the
        entire reason this service does not just push whole rows.
      * **rows are append-only.** An origin keeps its row forever, in the order
        it first appeared. One that stops reporting is not removed, it reads 0.
        Sorting, compacting or deleting would silently re-point every formula.

    Nothing is cleared, either. The block only ever grows — one more column per
    month, one more row per new origin — so `values.update` on the exact
    rectangle leaves everything outside it untouched. A `clear()` here would be
    one typo away from wiping the baselines.

WHY IT RE-READS EVERY MONTH
    The cron runs weekly and rewrites the whole history from 2023-01, not just
    the current month. Records get back-dated, corrected and soft-deleted long
    after the fact, so a month is only as valid as the last time it was checked.
    Recomputing 45 months costs one grouped query.

RELATIONSHIP TO `All data-GEPP`
    Same source query, different grain: that tab is (month × เขต) and drops any
    origin with no เขต; these are (origin × month) and drop nobody. The
    categories v3 has but the sheet has no column for (CONSTRUCTION, RUBBER) are
    folded into `general waste` exactly as they are there, so the two agree —
    summing a `[Origin]` tab over the origins of one เขต reproduces that เขต's
    column.
"""

import logging
import os
from collections import defaultdict
from datetime import date, datetime

from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
    _BANGKOK_TZ,
    CATEGORY_TO_COLUMN,
    DEFAULT_SHEET_ID,
    ORG_ID,
    UNMAPPED_CATEGORIES_GO_TO,
    BMAGSheetService,
)

_logger = logging.getLogger(__name__)

#: `All data-GEPP` column name -> the tab that holds its per-origin detail.
TAB_PREFIX = '[Origin] '

#: The seven tabs, in the order the categories appear in `All data-GEPP`.
CATEGORY_COLUMNS = [
    'organic waste', 'recycled materials', 'energy waste', 'hazardous waste',
    'infectious waste', 'electronic waste', 'general waste',
]
TAB_FOR_COLUMN = {col: TAB_PREFIX + col for col in CATEGORY_COLUMNS}

FIXED_COLUMNS = ['location id', 'location parent', 'location name', 'baseline']

#: 1-based, because that is how Sheets counts and how `column_letter` reads.
#: Column D is named so the one place that may write it — the header, once —
#: can say so, and so the tests can assert it appears in no other range.
COL_BASELINE = 4
FIRST_MONTH_COL = 5

#: One header row, then data. The older tabs in this workbook carry two (Thai
#: then English) because they were typed by hand; these are generated, are not
#: read by the bound Apps Script, and a single row keeps "sheet row = data row +
#: 1" simple for the formulas in column D.
HEADER_ROW = 1
START_ROW = 2

#: History starts here — ops' choice. Earlier data exists (org 67 goes back to
#: 2020) but was collected under a different project and is not comparable.
START_YEAR = 2023
START_MONTH = 1

#: Room to grow without a resize on every run: ~10 years of columns and enough
#: rows for several times the current 293 origins.
NEW_TAB_ROWS = 2000
NEW_TAB_COLS = FIRST_MONTH_COL + 120


def month_key(d):
    """A `date` (or datetime) -> the 'YYYY-MM' label used in the header."""
    return f'{d.year:04d}-{d.month:02d}'


def months_between(start, end):
    """Inclusive list of 'YYYY-MM' labels from `start` to `end`."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class BMAOriginMonthlyService(BMAGSheetService):
    """The seven `[Origin] <category>` tabs.

    Subclasses `BMAGSheetService` for its plumbing rather than duplicating it:
    the visible-origins CTE (which is what pulls in locations shared *into* the
    org), the dual SQLAlchemy/psycopg2 `_rows`, the org-chart edge reader and
    the credential loader are all the same integration, just aimed at a
    different grain.
    """

    # ── Extraction ───────────────────────────────────────────────────────

    def fetch_origin_month_category(self, org_id=ORG_ID, start=None,
                                    include_shared_history=False):
        """Rows of (origin_id, month_date, category_code, kg) from `start` on."""
        start = start or date(START_YEAR, START_MONTH, 1)
        window_clause = '' if include_shared_history else self._SHARE_WINDOW_PREDICATE
        return self._rows(self._VISIBLE_ORIGINS_CTE + f"""
            SELECT t.origin_id,
                   date_trunc('month', tr.transaction_date)::date AS month,
                   mc.code                                        AS category_code,
                   SUM(tr.origin_weight_kg)                       AS kg
            FROM visible v
            JOIN transactions t ON t.origin_id = v.id
            JOIN transaction_records tr ON tr.created_transaction_id = t.id
            LEFT JOIN material_categories mc ON mc.id = tr.category_id
            WHERE t.deleted_date  IS NULL
              AND tr.deleted_date IS NULL
              AND tr.transaction_date IS NOT NULL
              AND tr.transaction_date >= %(start)s
              {window_clause}
            GROUP BY 1, 2, 3
        """, {'org': org_id, 'start': start})

    def location_directory(self, org_id=ORG_ID):
        """``{id: (name, parent_path)}`` for every location the org can see.

        `parent_path` is the ancestor chain, root first, joined with ' > ' —
        'ธพส. > อาคารธนพิพัฒน์ > ชั้น 6' for a room on that floor — and '' for a
        node with no parent.

        Ancestors come from `organization_setup.root_nodes`, the org-chart JSON
        the web app edits, with `user_locations.parent_location_id` as a
        fallback. Reading only the column is the mistake that made org 67's tree
        look flat: nodes created through the chart editor leave it NULL, and 221
        of the real edges live only in the JSON.

        **Deleted locations are loaded too**, and only as names. The chart keeps
        pointing at a node after it is soft-deleted — org 67's grouping nodes
        `BMA เขตปทุมวัน (โรงเรียนสังกัดกทม.)` and its sibling both are — so
        filtering them out does not shorten the path, it breaks it: the chain
        stops at the deleted node and renders its raw id. They can never become
        rows, because the origin list is built from `visible`, which excludes
        them.
        """
        rows = self._rows(self._VISIBLE_ORIGINS_CTE + """
            SELECT ul.id, ul.parent_location_id,
                   COALESCE(ul.name_th, ul.name_en, ul.display_name,
                            ul.company_name, '')
            FROM user_locations ul
            WHERE ul.organization_id = %(org)s
            UNION
            SELECT ul.id, ul.parent_location_id,
                   COALESCE(ul.name_th, ul.name_en, ul.display_name,
                            ul.company_name, '')
            FROM visible v
            JOIN user_locations ul ON ul.id = v.id
        """, {'org': org_id})

        name, parent = {}, {}
        for loc_id, parent_id, nm in rows:
            loc_id = int(loc_id)
            name[loc_id] = (nm or '').strip()
            if parent_id is not None:
                parent[loc_id] = int(parent_id)

        # The chart wins where the column is silent; where both speak they
        # agree, and the column is the older of the two.
        for child_id, parent_id in self._chart_edges(org_id).items():
            if child_id in name and child_id not in parent:
                parent[child_id] = parent_id

        # A location shared in from another organization is shown as a root.
        # Its real parents live in THAT organization's chart — publishing them
        # would leak a structure we were given one node of, and the ancestors
        # are not even visible to us, so the names would come out as bare ids.
        _collapse, shared_roots = self.shared_root_map(org_id)

        def path(loc_id):
            if loc_id in shared_roots:
                return ''
            chain, seen, cur, depth = [], set(), parent.get(loc_id), 0
            while cur is not None and cur not in seen and depth < 20:
                if cur in shared_roots:
                    chain.append(name.get(cur) or str(cur))
                    break
                chain.append(name.get(cur) or str(cur))
                seen.add(cur)
                cur, depth = parent.get(cur), depth + 1
            return ' > '.join(reversed(chain))

        return {loc_id: (name[loc_id], path(loc_id)) for loc_id in name}

    # ── Aggregation ──────────────────────────────────────────────────────

    def build(self, org_id=ORG_ID, include_shared_history=False, as_of=None):
        """Everything the seven tabs need, in one pass.

        Returns ``(months, origins, totals, stats)``:

        * `months`  — 'YYYY-MM' labels, 2023-01 through the current month;
        * `origins` — ``{id: (name, parent_path)}`` for origins WITH data;
        * `totals`  — ``{column: {id: {month: kg}}}``, sparse;
        * `stats`   — counts for the cron log.

        The current month is included even though it is still accumulating.
        This is a weekly job whose whole point is that last week's numbers get
        corrected, so a partial month that fills in over four runs is the
        expected behaviour rather than a flaw — unlike the baseline column on
        the `Origin` tab, nothing here divides by a month count.
        """
        as_of = as_of or datetime.now(_BANGKOK_TZ).date()
        start = date(START_YEAR, START_MONTH, 1)
        months = months_between(start, as_of)
        month_set = set(months)

        raw = self.fetch_origin_month_category(org_id, start, include_shared_history)
        directory = self.location_directory(org_id)
        # A location shared in from another organization reports as the node
        # that was shared. Its children are summed into it and never get rows
        # of their own — see `BMAGSheetService.shared_root_map`. Without this,
        # UOB's 115 floors would each become a row here, publishing another
        # organization's internal breakdown.
        collapse, _shared_roots = self.shared_root_map(org_id)

        totals = {col: defaultdict(lambda: defaultdict(float))
                  for col in CATEGORY_COLUMNS}
        seen_ids, unknown_ids, dropped_months = set(), set(), 0

        for origin_id, month, cat_code, kg in raw:
            label = month_key(month)
            if label not in month_set:
                # Only possible for a record dated in the future.
                dropped_months += 1
                continue
            origin_id = collapse.get(int(origin_id), int(origin_id))
            column = CATEGORY_TO_COLUMN.get(cat_code, UNMAPPED_CATEGORIES_GO_TO)
            totals[column][origin_id][label] += float(kg or 0)
            seen_ids.add(origin_id)
            if origin_id not in directory:
                unknown_ids.add(origin_id)

        # The directory covers every location in the org plus everything shared
        # into it, so a miss here means a transaction points at a row that is
        # gone entirely. Give it a row anyway rather than dropping it: a
        # disappearing row renumbers everything below it and re-points the
        # baseline formulas.
        origins = {}
        for origin_id in sorted(seen_ids):
            origins[origin_id] = directory.get(
                origin_id, (f'(unknown location {origin_id})', ''))

        stats = {
            'origins': len(origins),
            'months': len(months),
            'month_from': months[0] if months else None,
            'month_to': months[-1] if months else None,
            'kg_total': round(sum(v
                                  for col in totals.values()
                                  for by_month in col.values()
                                  for v in by_month.values()), 2),
            'origins_missing_from_directory': len(unknown_ids),
            'shared_descendants_folded': len(collapse),
            'records_outside_month_window': dropped_months,
        }
        return months, origins, totals, stats

    # ── Sheet layout ─────────────────────────────────────────────────────

    @staticmethod
    def merge_order(existing_first_column, origins):
        """Decide the row order for one tab. Append-only, by construction.

        `existing_first_column` is column A as the sheet has it today, top to
        bottom, data rows only. Returns ``(order, stats)`` where `order` is one
        entry per sheet row:

        * an ``int`` — a location id this service maintains;
        * ``None``   — a row it does not recognise, which is skipped entirely
          rather than overwritten.

        Rows already present keep their index, whatever happens to them in the
        database. New origins are appended in id order so a tab created today
        ends up in the same order as one created a year ago plus its additions.
        A duplicate id in the sheet is honoured at its first position and the
        later copy left alone, because rewriting it would put the same numbers
        against someone's formula twice.
        """
        order, seen, foreign = [], set(), 0
        for cell in existing_first_column:
            text = str(cell).strip()
            if text.isdigit() and int(text) not in seen:
                loc_id = int(text)
                seen.add(loc_id)
                order.append(loc_id)
            else:
                foreign += 1
                order.append(None)

        appended = [i for i in sorted(origins) if i not in seen]
        order.extend(appended)
        return order, {'rows_existing': len(existing_first_column),
                       'rows_appended': len(appended),
                       'rows_unrecognised': foreign,
                       'rows_total': len(order)}

    @staticmethod
    def _runs(order):
        """Contiguous stretches of maintained rows, as (start_index, ids).

        Unrecognised rows split the block. Writing straight through them would
        mean sending a value for a row this service knows nothing about, and the
        only safe value — leaving the cell as it is — cannot be expressed in a
        rectangular write. So the rectangle stops instead.
        """
        runs, start, current = [], 0, []
        for i, loc_id in enumerate(order):
            if loc_id is None:
                if current:
                    runs.append((start, current))
                    current = []
                continue
            if not current:
                start = i
            current.append(loc_id)
        if current:
            runs.append((start, current))
        return runs

    @classmethod
    def tab_writes(cls, tab, months, origins, by_origin, order):
        """The ranges to PUT for one tab: A:C and E:…, never D.

        Returns ``[(a1_range, values), …]``. Column D is absent from every range
        here; the header cell D1 is written only by `_create_tab`, once, when
        the tab does not exist yet.

        Pure on purpose — no connection, no client — because the two rules that
        matter (append-only rows, column D untouched) are properties of the
        ranges alone and are worth testing without a database or a sheet.
        """
        from GEPPPlatform.libs.google_sa_auth import column_letter

        last_col = column_letter(FIRST_MONTH_COL + len(months) - 1)
        writes = [
            (f"'{tab}'!A{HEADER_ROW}:C{HEADER_ROW}", [FIXED_COLUMNS[:3]]),
            (f"'{tab}'!E{HEADER_ROW}:{last_col}{HEADER_ROW}", [months]),
        ]

        for start_index, ids in cls._runs(order):
            top = START_ROW + start_index
            bottom = top + len(ids) - 1
            fixed, monthly = [], []
            for loc_id in ids:
                name, parent = origins.get(loc_id, ('', ''))
                fixed.append([loc_id, parent, name])
                row = by_origin.get(loc_id) or {}
                # 0, not blank: ops asked for an explicit zero so a gap in
                # collection is visibly a zero rather than an empty cell that
                # could equally mean "not calculated".
                monthly.append([round(row.get(m, 0.0), 3) for m in months])
            writes.append((f"'{tab}'!A{top}:C{bottom}", fixed))
            writes.append((f"'{tab}'!E{top}:{last_col}{bottom}", monthly))

        return writes

    # ── Google Sheets ────────────────────────────────────────────────────

    @staticmethod
    def _create_tab(client, sheet_id, tab, months, row_count):
        """Create the tab. Returns its properties."""
        need_cols = max(FIRST_MONTH_COL + len(months) - 1, len(FIXED_COLUMNS))
        return client.add_tab(sheet_id, tab,
                              rows=max(NEW_TAB_ROWS, START_ROW + row_count),
                              cols=max(NEW_TAB_COLS, need_cols))

    @staticmethod
    def _needs_header(header_row):
        """True when D1 is still blank, so the `baseline` label can be written.

        The test is on D1 specifically, not on "is the tab empty". All seven
        tabs were created by hand before this service existed and arrived empty,
        so "the tab exists" cannot stand in for "the header is there" — and the
        opposite mistake, rewriting the header every run, would put a write on
        column D every week just to set a label that never changes.
        """
        first = header_row[0] if header_row else []
        return not (len(first) >= COL_BASELINE
                    and str(first[COL_BASELINE - 1]).strip())

    @staticmethod
    def _grow_tab(client, sheet_id, info, months, row_count):
        """Widen/lengthen the grid if the months or origins outgrew it."""
        need_cols = max(FIRST_MONTH_COL + len(months) - 1, len(FIXED_COLUMNS))
        need_rows = START_ROW + row_count
        if info['rows'] >= need_rows and info['cols'] >= need_cols:
            return False
        rows, cols = max(info['rows'], need_rows), max(info['cols'], need_cols)
        client.resize_tab(sheet_id, info['sheet_id'], rows=rows, cols=cols)
        info.update(rows=rows, cols=cols)
        return True

    def sync(self, org_id=ORG_ID, sheet_id=None, dry_run=False,
             include_shared_history=False, as_of=None, columns=None):
        """Build the seven tabs and write them.

        `columns` limits the run to some of the seven (by `All data-GEPP`
        column name) — useful for a targeted re-run, never used by the cron.
        """
        from GEPPPlatform.libs.google_sa_auth import SheetsClient

        sheet_id = sheet_id or os.environ.get('BMA_GSHEET_ID', DEFAULT_SHEET_ID)
        wanted = list(columns or CATEGORY_COLUMNS)
        unknown = [c for c in wanted if c not in TAB_FOR_COLUMN]
        if unknown:
            raise ValueError(f'unknown category column(s): {unknown}')

        months, origins, totals, stats = self.build(
            org_id, include_shared_history, as_of)
        result = {'sheet_id': sheet_id, 'tabs': {}, **stats}

        if dry_run:
            # Report what each tab would carry without opening a Sheets session,
            # so a dry run needs no credentials at all.
            for col in wanted:
                by_origin = totals[col]
                result['tabs'][TAB_FOR_COLUMN[col]] = {
                    'origins_with_data': len(by_origin),
                    'kg': round(sum(v for m in by_origin.values()
                                    for v in m.values()), 2),
                }
            return {'dry_run': True, **result}

        client = SheetsClient(self._load_service_account())
        props = client.tab_properties(sheet_id)
        for col in wanted:
            tab = TAB_FOR_COLUMN[col]
            by_origin = totals[col]

            created = tab not in props
            if created:
                # Nothing to read back from a tab that did not exist a moment
                # ago — and asking would only cost a round trip.
                props[tab] = self._create_tab(
                    client, sheet_id, tab, months, len(origins))
                header_row, first_column = [], []
            else:
                header_row, id_column = client.batch_get(sheet_id, [
                    f"'{tab}'!A{HEADER_ROW}:D{HEADER_ROW}",
                    f"'{tab}'!A{START_ROW}:A",
                ])
                first_column = [(r[0] if r else '') for r in id_column]

            # The one write in this service that touches column D, and only
            # while D1 is still blank.
            header_written = self._needs_header(header_row)
            if header_written:
                client.update(sheet_id, f"'{tab}'!A{HEADER_ROW}", [FIXED_COLUMNS])

            order, tab_stats = self.merge_order(first_column, origins)
            self._grow_tab(client, sheet_id, props[tab], months, len(order))

            writes = self.tab_writes(tab, months, origins, by_origin, order)
            client.batch_update_values(sheet_id, writes)

            tab_stats.update({
                'created': created,
                'header_initialised': header_written,
                'origins_with_data': len(by_origin),
                'kg': round(sum(v for m in by_origin.values()
                                for v in m.values()), 2),
            })
            result['tabs'][tab] = tab_stats
            _logger.info('BMA origin tabs: %s — %s rows (+%s new), %s kg',
                         tab, tab_stats['rows_total'],
                         tab_stats['rows_appended'], tab_stats['kg'])

        return {'dry_run': False, **result}
