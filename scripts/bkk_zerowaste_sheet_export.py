#!/usr/bin/env python3
"""
Build the `All data-GEPP` rows for the ไม่เทรวม (BKK Zero Waste) Google Sheet
straight from the v3 database, and optionally push them to the sheet.

WHY THIS EXISTS
    The sheet used to be maintained by hand (its numbers stop in mid-2024 while
    production kept receiving data). The Apps Script bound to the sheet only
    READS it — `doGet` serves the tabs as JSON to the public site. So the sheet
    is a data-entry surface, and this script replaces the data entry.

WHAT IT WRITES
    One row per (Month, Year, County), 20 columns, matching the sheet's own
    layout exactly. Only NINE of those columns are real inputs; the other eight
    are arithmetic. The formulas below were reverse-engineered from the 468 rows
    already in the sheet and reproduce them to floating-point exactness:

        all_waste       = Σ(the 7 category weights)              (diff 0)
        recycling_waste = recycled_materials + organic_waste     (diff 0)
        recyclable_rate = recycling_waste / all_waste * 100      (diff 1e-14)
        equal_tree      = ghg / 9.5                              (diff 0)
        equal_driving   = ghg * 3.86                             (diff 0)
        equal_bus       = ghg / 18000                            (diff 2e-15)
        reduce_landfill = all_waste - general_waste              (diff 0)
        food_waste      = organic_waste   (the sheet duplicates the column)

    `equal_tree`'s 9.5 kgCO2e/tree/year is the T-VER figure already hard-coded in
    v2 (`src/report/report.utils.ts`), which is a useful independent confirmation
    that the recovered constants are the real ones and not a curve fit.

COUNTY (เขต) — THE ONE UNSOLVED JOIN
    v3 does not know which เขต a location sits in: `user_locations.district_id`
    is NULL for all 862 org-67 locations, the 28 เขต rows in
    `user_location_tags` are attached to almost nothing, and
    `transactions.location_tag_id` is set on 1 record out of 7322.

    So County is resolved by name against the sheet's own `Origin` tab, which is
    maintained by the BMA side and does carry Name -> County. That covers 79.2%
    of the weight; the rest is reported in the `_unmapped` output for a human to
    map once. Ancestor-chain fallback was tried and adds nothing — the
    unmatched locations are all top-level with generic names ("อาคาร A").

SAFETY
    The DB session is opened read-only. This script never writes to Postgres.

USAGE
    # produce CSV + XLSX only (no Google credentials needed)
    python3 bkk_zerowaste_sheet_export.py --origin-xlsx "Data-ไม่เทรวม.xlsx"

    # also push to the sheet (needs a service-account key, see --help)
    python3 bkk_zerowaste_sheet_export.py --origin-xlsx "…" \
        --sheet-id 1Heb-AzHQlIce-08HrkZBCDDGamKJhM4QNhA35IfwEB8 \
        --service-account /path/to/key.json
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

# ── Recovered constants ───────────────────────────────────────────────────
# Each was derived from the sheet's existing rows with zero variance across
# all 62 populated rows, so they are exact, not fitted.
KG_CO2_PER_TREE_YEAR = 9.5      # T-VER; matches v2 report.utils.ts
DRIVING_KM_PER_KG_CO2 = 3.86
KG_CO2_PER_BUS = 18000.0

ORG_ID = 67                      # โครงการไม่เทรวม (BKK Zero Waste)
ACCOUNT_EMAIL = 'bmadatabase@gepp.me'

# Sheet column order for `All data-GEPP`, row 2 onward.
SHEET_COLUMNS = [
    'Month', 'Year', 'County',
    'organic waste', 'recycled materials', 'energy waste', 'hazardous waste',
    'infectious waste', 'electronic waste', 'general waste',
    'all waste', 'recycling waste', 'Recyclable rate',
    'Reduce greenhouse gas emissions', 'comparable to a tree',
    'Equal driving distance', 'Reduce landfill area compared to bus size.',
    'Reduce landfilling', 'food waste management', 'origin',
]

# v3 material_categories.code -> the sheet's column
CATEGORY_TO_COLUMN = {
    'ORGANIC':         'organic waste',
    'RECYCLABLE':      'recycled materials',
    'WASTE_TO_ENERGY': 'energy waste',
    'HAZARDOUS':       'hazardous waste',
    'BIO_HAZARDOUS':   'infectious waste',
    'ELECTRONIC':      'electronic waste',
    'GENERAL':         'general waste',
}
# Categories v3 has that the sheet has no column for. Folded into
# `general waste` so `all waste` still equals the true total collected —
# dropping them would silently understate the headline number.
UNMAPPED_CATEGORIES_GO_TO = 'general waste'


def load_db_env(env_path):
    """Read DB credentials from the migrations .env (never printed)."""
    with open(env_path, encoding='utf-8') as fh:
        kv = dict(re.findall(r'^(\w+)=(.*)$', fh.read(), re.M))
    missing = [k for k in ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
               if not kv.get(k)]
    if missing:
        sys.exit(f'{env_path} is missing: {", ".join(missing)}')
    return kv


def build_county_map(origin_xlsx):
    """Name -> County, from the sheet's own `Origin` tab (BMA-maintained)."""
    import pandas as pd
    df = pd.read_excel(origin_xlsx, sheet_name='Origin', header=1)
    df = df[df['Name'].notna()]
    out = {}
    for name, county in zip(df['Name'], df['County']):
        key = str(name).strip().lower()
        # First occurrence wins: the tab has duplicate names across years and
        # the County is stable, so later rows add nothing but can be blank.
        if key and key not in out and county:
            out[key] = str(county).strip()
    return out


def fetch_rows(kv, county_map, year_from=None):
    import psycopg2
    cn = psycopg2.connect(
        host=kv['DB_HOST'], port=kv['DB_PORT'], dbname=kv['DB_NAME'],
        user=kv['DB_USER'], password=kv['DB_PASSWORD'], connect_timeout=30,
    )
    # Belt and braces: this script must never mutate production.
    cn.set_session(readonly=True)
    cu = cn.cursor()

    where_year = ''
    params = {'org': ORG_ID}
    if year_from:
        where_year = ' AND EXTRACT(YEAR FROM tr.transaction_date) >= %(yr)s'
        params['yr'] = year_from

    # `origin_weight_kg` is the weight as recorded at the origin, which is what
    # the sheet's "ประมาณขยะที่เก็บได้" counts. GHG comes off the material's
    # own factor (materials.calc_ghg, kgCO2e per kg) — NOT a per-category
    # constant, so a row with no material_id contributes weight but no GHG.
    cu.execute(f"""
        SELECT EXTRACT(MONTH FROM tr.transaction_date)::int      AS month,
               EXTRACT(YEAR  FROM tr.transaction_date)::int      AS year,
               t.origin_id,
               COALESCE(ul.name_th, ul.name_en, ul.display_name,
                        ul.company_name)                         AS origin_name,
               mc.code                                          AS category_code,
               SUM(tr.origin_weight_kg)                          AS kg,
               SUM(tr.origin_weight_kg * COALESCE(m.calc_ghg, 0)) AS ghg
        FROM transaction_records tr
        JOIN transactions t   ON t.id  = tr.created_transaction_id
        LEFT JOIN user_locations      ul ON ul.id = t.origin_id
        LEFT JOIN material_categories mc ON mc.id = tr.category_id
        LEFT JOIN materials           m  ON m.id  = tr.material_id
        WHERE t.organization_id = %(org)s
          AND t.deleted_date  IS NULL
          AND tr.deleted_date IS NULL
          AND tr.transaction_date IS NOT NULL
          {where_year}
        GROUP BY 1, 2, 3, 4, 5
    """, params)
    raw = cu.fetchall()
    cu.close()
    cn.close()
    return raw


def aggregate(raw, county_map):
    """Fold the per-origin rows into one row per (month, year, county)."""
    buckets = defaultdict(lambda: {c: 0.0 for c in SHEET_COLUMNS[3:19]})
    origins = defaultdict(set)
    unmapped = defaultdict(float)

    for month, year, origin_id, origin_name, cat_code, kg, ghg in raw:
        kg = float(kg or 0)
        ghg = float(ghg or 0)
        key_name = str(origin_name).strip().lower() if origin_name else ''
        county = county_map.get(key_name)
        if not county:
            unmapped[(origin_id, origin_name)] += kg
            continue

        key = (month, year, county)
        col = CATEGORY_TO_COLUMN.get(cat_code, UNMAPPED_CATEGORIES_GO_TO)
        buckets[key][col] += kg
        buckets[key]['Reduce greenhouse gas emissions'] += ghg
        if origin_id is not None:
            origins[key].add(int(origin_id))

    rows = []
    for (month, year, county), vals in sorted(buckets.items()):
        cats = [vals[CATEGORY_TO_COLUMN[c]] for c in
                ('ORGANIC', 'RECYCLABLE', 'WASTE_TO_ENERGY', 'HAZARDOUS',
                 'BIO_HAZARDOUS', 'ELECTRONIC', 'GENERAL')]
        organic, recyclable, energy, hazardous, bio, electronic, general = cats

        # ── the eight derived columns, exactly as the sheet computes them ──
        all_waste = sum(cats)
        recycling_waste = recyclable + organic
        recyclable_rate = (recycling_waste / all_waste * 100) if all_waste else 0.0
        ghg = vals['Reduce greenhouse gas emissions']
        rows.append({
            'Month': month, 'Year': year, 'County': county,
            'organic waste': organic, 'recycled materials': recyclable,
            'energy waste': energy, 'hazardous waste': hazardous,
            'infectious waste': bio, 'electronic waste': electronic,
            'general waste': general,
            'all waste': all_waste,
            'recycling waste': recycling_waste,
            'Recyclable rate': recyclable_rate,
            'Reduce greenhouse gas emissions': ghg,
            'comparable to a tree': ghg / KG_CO2_PER_TREE_YEAR,
            'Equal driving distance': ghg * DRIVING_KM_PER_KG_CO2,
            'Reduce landfill area compared to bus size.': ghg / KG_CO2_PER_BUS,
            'Reduce landfilling': all_waste - general,
            'food waste management': organic,
            'origin': ','.join(str(i) for i in sorted(origins[(month, year, county)])),
        })
    return rows, unmapped


def write_csv(rows, path):
    with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def write_xlsx(rows, path):
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'All data-GEPP'
    ws.append(SHEET_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(name='Arial', bold=True)
    for r in rows:
        ws.append([r[c] for c in SHEET_COLUMNS])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name='Arial')
    wb.save(path)


def push_to_sheet(rows, sheet_id, sa_path, tab='All data-GEPP', start_row=3):
    """Overwrite the tab's data rows in place, leaving the two header rows."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        sa_path, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    svc = build('sheets', 'v4', credentials=creds)
    values = [[r[c] for c in SHEET_COLUMNS] for r in rows]
    rng = f"'{tab}'!A{start_row}"
    # Clear first: a shorter new dataset must not leave stale rows behind.
    svc.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"'{tab}'!A{start_row}:T100000").execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=rng,
        valueInputOption='RAW', body={'values': values}).execute()
    return len(values)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--env', default=os.path.join(
        os.path.dirname(__file__), '..', 'migrations', '.env'),
        help='path to the .env holding DB_* credentials')
    ap.add_argument('--origin-xlsx', required=True,
                    help='the existing workbook — its `Origin` tab supplies Name->County')
    ap.add_argument('--year-from', type=int, default=None,
                    help='only export from this year onward')
    ap.add_argument('--out-prefix', default='all_data_gepp')
    ap.add_argument('--sheet-id', default=None,
                    help='Google Sheet id to push to (omit to only write files)')
    ap.add_argument('--service-account', default=None,
                    help='service-account JSON key; the sheet must be shared '
                         'with that key\'s client_email as Editor')
    args = ap.parse_args()

    kv = load_db_env(args.env)
    print(f'DB   : {kv["DB_USER"]}@{kv["DB_HOST"]}/{kv["DB_NAME"]} (read-only)')
    print(f'Org  : {ORG_ID} — account {ACCOUNT_EMAIL}')

    county_map = build_county_map(args.origin_xlsx)
    print(f'County map from `Origin` tab: {len(county_map)} names')

    raw = fetch_rows(kv, county_map, args.year_from)
    print(f'DB rows fetched: {len(raw)}')

    rows, unmapped = aggregate(raw, county_map)
    mapped_kg = sum(r['all waste'] for r in rows)
    unmapped_kg = sum(unmapped.values())
    total = mapped_kg + unmapped_kg
    print(f'Output rows: {len(rows)}  '
          f'(months {min(r["Year"] for r in rows) if rows else "-"}'
          f'..{max(r["Year"] for r in rows) if rows else "-"})')
    print(f'Weight mapped to a County: {mapped_kg:,.0f} / {total:,.0f} kg '
          f'({mapped_kg / total * 100:.1f}%)' if total else 'no weight')

    write_csv(rows, f'{args.out_prefix}.csv')
    write_xlsx(rows, f'{args.out_prefix}.xlsx')
    print(f'Wrote {args.out_prefix}.csv and {args.out_prefix}.xlsx')

    if unmapped:
        with open(f'{args.out_prefix}_unmapped.csv', 'w', newline='',
                  encoding='utf-8-sig') as fh:
            w = csv.writer(fh)
            w.writerow(['origin_id', 'origin_name', 'kg_excluded'])
            for (oid, nm), kg in sorted(unmapped.items(), key=lambda x: -x[1]):
                w.writerow([oid, nm, round(kg, 2)])
        print(f'Wrote {args.out_prefix}_unmapped.csv '
              f'({len(unmapped)} origins, {unmapped_kg:,.0f} kg with no County)')

    if args.sheet_id:
        if not args.service_account:
            sys.exit('--sheet-id needs --service-account')
        n = push_to_sheet(rows, args.sheet_id, args.service_account)
        print(f'Pushed {n} rows to sheet {args.sheet_id}')


if __name__ == '__main__':
    main()
