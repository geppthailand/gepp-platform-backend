#!/usr/bin/env python3
"""Repair the `GEPP Location ID` columns in the BMA workbook.

WHY
    Two defects accumulated in the provenance columns, both of which make the
    published ids point at the wrong thing:

    1. **v2 ids.** Rows written by hand before the v3 cron existed carry the
       OLD business platform's location ids. They are not merely stale: most
       are also valid v3 ids belonging to *other organizations*, so the sheet
       silently resolves to strangers — `13363` reads as `Floor 3` in org 14
       when it means `CentralGroup & CentralWorld` in org 67. The bridge is
       `user_locations.migration_id`, which holds each v3 row's v2 id.

    2. **Shared subtrees.** A location shared in from another organization is
       shared as ONE node, but the recursive visibility walk made each of its
       children an origin in its own right. UOB's three buildings carry 115
       floors between them, and those floors were listed individually — more
       than half of every id in `All data-GEPP`. Ops' rule is that a share of
       `A` reports as `A` alone, with `B, C, D` summed into it.

    Both are repaired in place: only the id column is written, the "A,B,C"
    format is preserved, and nothing else on either tab is touched. The cron
    itself was fixed at the same time (`shared_root_map`, `origin_column_map`),
    so this script is a one-time backfill of rows the cron does not own —
    `All data-GEPP` before `MANAGED_FROM_YEAR` is never rewritten by it.

USAGE
    python scripts/bma_fix_origin_ids.py            # report only
    python scripts/bma_fix_origin_ids.py --apply    # write it
    python scripts/bma_fix_origin_ids.py --apply --clear-junk
                                                    # also blank cells that
                                                    # hold no id at all
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

from GEPPPlatform.libs.google_sa_auth import SheetsClient, column_letter
from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
    DEFAULT_SHEET_ID,
    DEFAULT_START_ROW,
    DEFAULT_TAB,
    ORG_ID,
    ORIGIN_HEADER_ROW,
    ORIGIN_LOCATION_ID,
    ORIGIN_TAB,
    BMAGSheetService,
)

#: `All data-GEPP`'s provenance column, by its English header name.
ALLDATA_ID_HEADER = 'GEPP Location ID'


def connect():
    cn = psycopg2.connect(
        host=os.environ['DB_HOST'], port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ['DB_NAME'], user=os.environ['DB_USER'],
        password=os.environ.get('DB_PASS') or os.environ.get('DB_PASSWORD', ''),
        connect_timeout=30,
    )
    # This script writes to Google, never to Postgres.
    cn.set_session(readonly=True)
    return cn


def build_maps(svc, org_id=ORG_ID):
    """``(visible, v2_to_v3, collapse, roots)``.

    `v2_to_v3` is built from org-67 rows only, and **includes soft-deleted
    ones**: `CJ Supermarket (สี่แยกหนองแขม)` was deleted in March but still
    owns 2.5 tonnes of 2023 transactions, and a 2023 row that refers to it is
    not wrong. Ambiguity is resolved towards a currently visible row, then
    towards the lowest id, so the mapping is deterministic.
    """
    visible = {int(r[0]) for r in
               svc._rows(svc._VISIBLE_ORIGINS_CTE + 'SELECT id FROM visible',
                         {'org': org_id})}
    candidates = {}
    for loc_id, mig in svc._rows(
            'SELECT id, migration_id FROM user_locations '
            'WHERE organization_id = %(org)s AND migration_id IS NOT NULL',
            {'org': org_id}):
        candidates.setdefault(int(mig), []).append(int(loc_id))
    v2_to_v3 = {}
    for mig, ids in candidates.items():
        live = [i for i in ids if i in visible]
        v2_to_v3[mig] = min(live) if live else min(ids)
    collapse, roots = svc.shared_root_map(org_id)
    return visible, v2_to_v3, collapse, roots


def repair_cell(raw, visible, v2_to_v3, collapse, report, clear_junk=False):
    """One `A,B,C` cell -> the repaired cell, counting what happened."""
    tokens = [t.strip() for t in str(raw or '').split(',') if t.strip()]
    if tokens and all(not t.isdigit() for t in tokens):
        # No id in the cell at all. `Origin` row 2153 holds the word `On`,
        # dragged one column too far from `Display (On/Off)` — it is the only
        # row on the tab where that happened, and the location it names
        # (`ชุมชนเลิศสุขสม`) does not exist in v3, so there is no id to put
        # there. Clearing restores it to match its 3,700 siblings on BMA's own
        # master list, every one of which leaves this column empty.
        report['junk'].append((raw, tokens))
        return '' if clear_junk else raw
    if any(not t.isdigit() for t in tokens):
        # Ids AND something else in one cell. Not a drag-fill slip, and not
        # safe to guess at — reported and left exactly as found.
        report['mixed'].append((raw, tokens))
        return raw
    out = []
    for token in tokens:
        i = int(token)
        # An id that is already a visible origin is never rewritten — that is
        # what keeps the script idempotent, and no visible id is also somebody
        # else's migration_id, so the two interpretations cannot collide.
        if i not in visible and i in v2_to_v3:
            report['v2_converted'] += 1
            i = v2_to_v3[i]
        elif i not in visible:
            report['unresolved'].append(i)
        if i in collapse:
            report['collapsed'] += 1
            i = collapse[i]
        out.append(i)
    # Sorted and de-duplicated, which is the shape the cron writes: collapsing
    # 115 floors onto 3 buildings creates duplicates by construction.
    return ','.join(str(i) for i in sorted(set(out)))


def header_index(client, sheet_id, tab, row, name, grid_cols):
    end = column_letter(max(grid_cols, 1))
    head = client.get(sheet_id, f"'{tab}'!A{row}:{end}{row}").get('values', []) or []
    cells = head[0] if head else []
    want = ' '.join(name.split()).strip().lower()
    for idx, cell in enumerate(cells):
        if ' '.join(str(cell or '').split()).strip().lower() == want:
            return idx, cells
    raise RuntimeError(f"'{tab}' row {row} has no column named {name!r}: {cells}")


def main():
    apply = '--apply' in sys.argv
    # Off by default: converting ids is not licence to tidy a column ops
    # maintains, so clearing a cell that holds no id is asked for explicitly.
    clear_junk = '--clear-junk' in sys.argv
    sheet_id = os.environ.get('BMA_GSHEET_ID', DEFAULT_SHEET_ID)

    cn = connect()
    svc = BMAGSheetService(cn)
    visible, v2_to_v3, collapse, roots = build_maps(svc)
    print(f'org {ORG_ID}: {len(visible)} visible origins, '
          f'{len(v2_to_v3)} v2->v3 mappings, '
          f'{len(collapse)} shared descendants under {len(roots)} shared roots')

    client = SheetsClient(BMAGSheetService._load_service_account())
    props = client.tab_properties(sheet_id)

    for tab, header_row in ((DEFAULT_TAB, 2), (ORIGIN_TAB, ORIGIN_HEADER_ROW)):
        grid = props.get(tab) or {}
        cols, rows_n = grid.get('cols') or 26, grid.get('rows') or 100000
        name = ALLDATA_ID_HEADER if tab == DEFAULT_TAB else ORIGIN_LOCATION_ID
        idx, header = header_index(client, sheet_id, tab, header_row, name, cols)
        letter = column_letter(idx + 1)
        start = DEFAULT_START_ROW

        values = client.get(
            sheet_id, f"'{tab}'!{letter}{start}:{letter}{rows_n}"
        ).get('values', []) or []
        report = {'v2_converted': 0, 'collapsed': 0,
                  'unresolved': [], 'junk': [], 'mixed': []}
        new_col, changed = [], []
        for offset, row in enumerate(values):
            raw = str(row[0]).strip() if row else ''
            fixed = (repair_cell(raw, visible, v2_to_v3, collapse, report,
                                 clear_junk)
                     if raw else '')
            new_col.append([fixed])
            if fixed != raw:
                changed.append((start + offset, raw, fixed))

        print(f'\n=== {tab}  column {letter} ({name})')
        print(f'    {len(values)} cells read, {len(changed)} would change')
        print(f'    v2 ids converted: {report["v2_converted"]}   '
              f'shared descendants collapsed: {report["collapsed"]}')
        if report['unresolved']:
            u = sorted(set(report['unresolved']))
            print(f'    UNRESOLVED (left as-is): {len(u)} -> {u[:15]}')
        if report['junk']:
            verb = 'CLEARED' if clear_junk else 'left alone (pass --clear-junk)'
            print(f'    holds no id at all: {len(report["junk"])} cell(s) '
                  f'{verb} -> {[r for r, _ in report["junk"]][:6]}')
        if report['mixed']:
            print(f'    MIXED ids and text, left alone: {len(report["mixed"])} '
                  f'cell(s) -> {[r for r, _ in report["mixed"]][:6]}')
        for r, a, b in changed[:6]:
            print(f'      row {r}: {a[:70]}\n            -> {b[:70]}')
        if len(changed) > 6:
            print(f'      ... and {len(changed) - 6} more')

        if apply and changed:
            client.update(sheet_id,
                          f"'{tab}'!{letter}{start}:{letter}{start + len(new_col) - 1}",
                          new_col)
            print(f'    WRITTEN: {letter}{start}:{letter}{start + len(new_col) - 1}')
        elif apply:
            print('    nothing to write')

    if not apply:
        print('\n(dry run — pass --apply to write)')


if __name__ == '__main__':
    main()
