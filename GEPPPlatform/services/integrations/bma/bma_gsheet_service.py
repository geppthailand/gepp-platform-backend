"""Push the ไม่เทรวม (BKK Zero Waste) monthly figures into the BMA Google Sheet.

WHY THIS EXISTS
    The `All data-GEPP` tab of the BMA workbook used to be typed in by hand and
    stopped being updated in mid-2024. An Apps Script bound to the sheet exposes
    the tabs as JSON (`doGet`) to the public site, so the sheet is a data-entry
    surface, not an integration — replacing the data entry is the whole job.

WHAT IT WRITES
    One row per (Month, Year, County) with the tab's own 20 columns. Only nine
    are inputs; the other eight are arithmetic. Those formulas were recovered by
    regression against the 468 rows already in the sheet and reproduce them
    exactly (worst case 2e-15 across the 62 populated rows):

        all_waste       = Σ(the 7 category weights)
        recycling_waste = recycled_materials + organic_waste
        recyclable_rate = recycling_waste / all_waste * 100
        equal_tree      = ghg / 9.5
        equal_driving   = ghg * 3.86
        equal_bus       = ghg / 18000
        reduce_landfill = all_waste - general_waste
        food_waste      = organic_waste          (the tab duplicates the column)

    The 9.5 kgCO2e/tree/year that fell out of the regression is the same T-VER
    figure hard-coded in v2's `report/report.utils.ts`, which is independent
    confirmation the constants are the real ones and not a curve fit.

COUNTY (เขต)
    Resolved from `user_locations.district_id`, which the Location Setup panel
    populates. `DISTRICT_TO_COUNTY` below maps เขต name to the sheet's own
    `CountyNN` code — Bangkok's 50 districts are fixed, so it is a constant
    rather than a lookup table.

    The rule is "the topmost node with a เขต wins":

      * a node with no เขต anywhere up its chain is left OUT of the sheet — the
        service never guesses one from siblings or descendants;
      * when an ancestor has a เขต, the whole subtree reports under it, and a
        เขต set on a descendant is ignored (and reported, since it is usually a
        mis-tagged floor).

    The hierarchy comes from `organization_setup.root_nodes` — the org-chart
    JSON the web app edits — NOT from `user_locations.parent_location_id`, which
    that editor leaves NULL. Reading the column instead made org 67's 862
    locations look like 746 roots and silently dropped 879 tonnes.

CREDENTIALS
    A Google service-account key, from (in order) `BMA_GSHEET_SA_JSON` (raw
    JSON), `BMA_GSHEET_SA_SECRET_ID` (AWS Secrets Manager), or
    `BMA_GSHEET_SA_FILE` (path, local dev only). The target sheet must be shared
    with the key's `client_email` as an Editor — a service account has no access
    to anything until it is invited like any other user.

    Talking to Google goes through `libs.google_sa_auth`, which is standard
    library only, so this cron runs on the existing `platform` Lambda layer with
    no additions. `google-api-python-client` + `google-auth` would have pulled in
    httplib2, uritemplate, rsa, pyasn1(-modules) and cachetools for what amounts
    to two HTTPS calls.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_logger = logging.getLogger(__name__)

#: Reporting is on Bangkok dates — matches `_BANGKOK_TZ` in audit_scripts.py.
_BANGKOK_TZ = timezone(timedelta(hours=7))

#: Passed as `replace_years` to mean "yes, really overwrite the whole tab".
REPLACE_ALL = 'all'

#: The first year this cron owns. Earlier years in the tab were curated by hand
#: and carry BMA-sourced 'general waste' rows for all 50 เขต that v3 cannot
#: reproduce, so the cron refuses to write them even if asked. `REPLACE_ALL` is
#: the one deliberate override.
MANAGED_FROM_YEAR = 2025


def current_year():
    """The year in Bangkok, which is what a Thai monthly report means."""
    return datetime.now(_BANGKOK_TZ).year


def default_managed_years():
    """Years the scheduled run maintains: this year and last.

    Two, not one, because data lands late — a run in January still has to close
    out December. Rolls forward on its own, and never reaches back past
    `MANAGED_FROM_YEAR`.
    """
    y = current_year()
    return [n for n in (y - 1, y) if n >= MANAGED_FROM_YEAR]

# ── Constants recovered from the sheet's own rows (zero variance) ─────────
KG_CO2_PER_TREE_YEAR = 9.5        # T-VER; matches v2 report.utils.ts
DRIVING_KM_PER_KG_CO2 = 3.86
KG_CO2_PER_BUS = 18000.0

#: โครงการไม่เทรวม (BKK Zero Waste) — the org whose data feeds the sheet.
ORG_ID = 67

DEFAULT_SHEET_ID = '1Heb-AzHQlIce-08HrkZBCDDGamKJhM4QNhA35IfwEB8'
DEFAULT_TAB = 'All data-GEPP'
#: Every tab keeps two header rows (Thai, then English); data starts at row 3.
DEFAULT_START_ROW = 3

ORIGIN_TAB = 'Origin'
OVERALL_TAB = 'Overall Project'

#: `Origin`'s existing columns A–J, then the two we add.
ORIGIN_COLUMNS = [
    'Name', 'County', 'Baseline Data',
    'Landfill Waste Reduction\n(Monthly Average)',
    'Recyclable Material\n(Monthly Average)',
    'Organic Material\n(Monthly Average)',
    'Greenhouse Gas Reduction\n(Monthly Average)',
    'Latitude', 'Longitude', 'Google Map Link',
    # Added by this service. The ID is the load-bearing one: `Origin` has 195
    # duplicate names, so matching on name alone would update the wrong row or
    # append duplicates on every run.
    'GEPP Location ID', 'Added On',
]
ORIGIN_COL = {name: i for i, name in enumerate(ORIGIN_COLUMNS)}

#: Columns this service owns on an EXISTING row. Everything else is left alone —
#: `Baseline Data` and `Landfill Waste Reduction` are surveyed on site (the
#: latter is baseline-minus-current and goes negative, so it cannot come from
#: our transactions), and `Greenhouse Gas Reduction` on existing rows is pinned
#: to the emission factors in force when the row was written, so the published
#: series stays comparable.
ORIGIN_UPDATABLE_EXISTING = [
    'Recyclable Material\n(Monthly Average)',
    'Organic Material\n(Monthly Average)',
]

SHEET_COLUMNS = [
    'Month', 'Year', 'County',
    'organic waste', 'recycled materials', 'energy waste', 'hazardous waste',
    'infectious waste', 'electronic waste', 'general waste',
    'all waste', 'recycling waste', 'Recyclable rate',
    'Reduce greenhouse gas emissions', 'comparable to a tree',
    'Equal driving distance', 'Reduce landfill area compared to bus size.',
    'Reduce landfilling', 'food waste management', 'origin',
]

#: v3 material_categories.code -> the sheet's column.
CATEGORY_TO_COLUMN = {
    'ORGANIC':         'organic waste',
    'RECYCLABLE':      'recycled materials',
    'WASTE_TO_ENERGY': 'energy waste',
    'HAZARDOUS':       'hazardous waste',
    'BIO_HAZARDOUS':   'infectious waste',
    'ELECTRONIC':      'electronic waste',
    'GENERAL':         'general waste',
}
#: Categories v3 has that the sheet has no column for (CONSTRUCTION, RUBBER)
#: are folded in here so `all waste` still equals the true total collected.
#: Dropping them would understate the headline number without any signal.
UNMAPPED_CATEGORIES_GO_TO = 'general waste'

#: Bangkok's 50 เขต -> the sheet's CountyNN code, taken from its `Index` tab.
#: Keys are the bare `location_districts.name_th`; the "เขต"-prefixed spelling
#: is accepted too (see `_county_for_district`).
DISTRICT_TO_COUNTY = {
    'พระนคร': 'County01', 'ดุสิต': 'County02', 'หนองจอก': 'County03',
    'บางรัก': 'County04', 'บางเขน': 'County05', 'บางกะปิ': 'County06',
    'ปทุมวัน': 'County07', 'ป้อมปราบศัตรูพ่าย': 'County08', 'พระโขนง': 'County09',
    'มีนบุรี': 'County10', 'ลาดกระบัง': 'County11', 'ยานนาวา': 'County12',
    'สัมพันธวงศ์': 'County13', 'พญาไท': 'County14', 'ธนบุรี': 'County15',
    'บางกอกใหญ่': 'County16', 'ห้วยขวาง': 'County17', 'คลองสาน': 'County18',
    'ตลิ่งชัน': 'County19', 'บางกอกน้อย': 'County20', 'บางขุนเทียน': 'County21',
    'ภาษีเจริญ': 'County22', 'หนองแขม': 'County23', 'ราษฎร์บูรณะ': 'County24',
    'บางพลัด': 'County25', 'ดินแดง': 'County26', 'บึงกุ่ม': 'County27',
    'สาทร': 'County28', 'บางซื่อ': 'County29', 'จตุจักร': 'County30',
    'บางคอแหลม': 'County31', 'ประเวศ': 'County32', 'คลองเตย': 'County33',
    'สวนหลวง': 'County34', 'จอมทอง': 'County35', 'ดอนเมือง': 'County36',
    'ราชเทวี': 'County37', 'ลาดพร้าว': 'County38', 'วัฒนา': 'County39',
    'บางแค': 'County40', 'หลักสี่': 'County41', 'สายไหม': 'County42',
    'คันนายาว': 'County43', 'สะพานสูง': 'County44', 'วังทองหลาง': 'County45',
    'คลองสามวา': 'County46', 'บางนา': 'County47', 'ทวีวัฒนา': 'County48',
    'ทุ่งครุ': 'County49', 'บางบอน': 'County50',
}


def _county_for_district(name):
    """เขต name -> CountyNN, tolerating the optional 'เขต' prefix."""
    if not name:
        return None
    n = str(name).strip()
    return (DISTRICT_TO_COUNTY.get(n)
            or DISTRICT_TO_COUNTY.get(n.replace('เขต', '', 1)))


class BMAGSheetService:
    """Builds the `All data-GEPP` rows and (optionally) pushes them.

    Accepts either a SQLAlchemy ``Session`` (how the platform Lambda calls it)
    or a bare psycopg2 connection (how the cron does, to keep its layer small).
    Every query here is raw SQL with no ORM involvement, so the only thing that
    differs is how rows are fetched — see `_rows`.

    SQL is written in psycopg2's ``%(name)s`` paramstyle rather than
    SQLAlchemy's ``:name``, because `exec_driver_sql` hands the statement
    straight to the driver. One string, both callers, no translation layer.
    """

    def __init__(self, db):
        self.db = db

    # ── Which origins belong to this report ──────────────────────────────

    #: Origins the org can report on: its own locations, plus locations another
    #: org shared *into* it (`shared_user_locations`) and everything beneath
    #: them. Filtering transactions on `t.organization_id` alone misses the
    #: shared ones entirely — their transactions still belong to the SOURCE
    #: org — which silently dropped 2.3 M kg across 5 sites.
    #:
    #: `share_start` / `share_end` come along so the caller can decide whether
    #: to count a shared site's history from before the share existed.
    _VISIBLE_ORIGINS_CTE = """
        WITH RECURSIVE shared_roots AS (
            SELECT s.source_user_location_id AS id,
                   s.start_date AS share_start,
                   s.end_date   AS share_end,
                   0 AS depth
            FROM shared_user_locations s
            WHERE s.deleted_date IS NULL
              AND s.target_organization_id = %(org)s
              AND s.is_active
              AND s.is_valid
              AND NOT s.is_rejected
            UNION ALL
            SELECT c.id, sr.share_start, sr.share_end, sr.depth + 1
            FROM shared_roots sr
            JOIN user_locations c ON c.parent_location_id = sr.id
            WHERE sr.depth < 6 AND c.deleted_date IS NULL
        ),
        visible AS (
            SELECT ul.id,
                   NULL::timestamptz AS share_start,
                   NULL::timestamptz AS share_end,
                   FALSE AS is_shared
            FROM user_locations ul
            WHERE ul.organization_id = %(org)s AND ul.deleted_date IS NULL
            UNION
            SELECT sr.id, sr.share_start, sr.share_end, TRUE
            FROM shared_roots sr
        )
    """

    #: Applied to a shared origin's records. `include_shared_history` turns it
    #: off, which counts a site's whole past against the project even though the
    #: project only gained access on `start_date`.
    _SHARE_WINDOW_PREDICATE = """
          AND (v.is_shared = FALSE
               OR ((v.share_start IS NULL OR tr.transaction_date >= v.share_start)
               AND (v.share_end   IS NULL OR tr.transaction_date <= v.share_end)))
    """

    def _rows(self, sql, params=None):
        """Run a SELECT and return the rows, whichever connection we hold."""
        params = params or {}
        execute = getattr(self.db, 'exec_driver_sql', None)
        if execute is None:
            # SQLAlchemy Session: reach its Connection, which has the method.
            conn = getattr(self.db, 'connection', None)
            if callable(conn):
                execute = conn().exec_driver_sql
        if execute is not None:
            return execute(sql, params).fetchall()

        # psycopg2 connection.
        with self.db.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # ── County resolution ────────────────────────────────────────────────

    def resolve_districts(self, org_id=ORG_ID):
        """location_id -> CountyNN for every location in the org.

        Returns ``(resolved, info)``. `info['overridden_by_ancestor']` names
        nodes whose own district is being ignored because an ancestor sets one —
        usually a mis-tagged floor, and worth seeing rather than swallowing.
        """
        # Shared-in locations are included so their เขต resolves the moment
        # someone fills it in — today all 5 of them have district_id NULL.
        rows = self._rows(self._VISIBLE_ORIGINS_CTE + """
            SELECT ul.id, ul.parent_location_id, d.name_th
            FROM visible v
            JOIN user_locations ul ON ul.id = v.id
            LEFT JOIN location_districts d ON d.id = ul.district_id
            WHERE ul.deleted_date IS NULL
        """, {'org': org_id})

        parent, own = {}, {}
        children = defaultdict(list)
        for loc_id, parent_id, dname in rows:
            parent[loc_id] = parent_id
            if parent_id is not None:
                children[parent_id].append(loc_id)
            code = _county_for_district(dname)
            if code:
                own[loc_id] = code

        # `parent_location_id` is NOT where the org chart lives. The hierarchy
        # the web app draws is JSON in `organization_setup.root_nodes`, and the
        # column is left NULL on nodes created through that editor — so reading
        # only the column makes a deeply nested org look flat. It made org 67's
        # 862 locations read as 746 roots with a single real parent, which in
        # turn made the ancestor/descendant walks below dead code.
        for child_id, parent_id in self._chart_edges(org_id).items():
            if child_id in parent and parent.get(child_id) is None:
                parent[child_id] = parent_id
                children[parent_id].append(child_id)

        def topmost_district(loc_id):
            """The district of the HIGHEST node in this branch that has one.

            The rule, as the ops team defines it:

              * only a node with an explicitly set เขต counts;
              * when such a node has children, the whole subtree reports under
                its เขต — a เขต on a descendant is ignored, not merged;
              * nothing set anywhere up the chain means the origin is left out
                of the sheet rather than guessed at.

            So the authority is the topmost ancestor with a district, not the
            nearest one. That also dissolves the "children straddle two
            districts" case by construction: the parent decides.
            """
            chain, seen, cur, depth = [], set(), loc_id, 0
            while cur is not None and cur not in seen and depth < 20:
                chain.append(cur)
                seen.add(cur)
                cur, depth = parent.get(cur), depth + 1
            # Walk from the root end downwards and take the first district seen.
            for node in reversed(chain):
                if node in own:
                    return own[node], node
            return None, None

        resolved, authority, overridden = {}, {}, {}
        for loc_id in parent:
            code, src = topmost_district(loc_id)
            if not code:
                continue
            resolved[loc_id] = code
            authority[loc_id] = src
            # A district set on this node that its ancestor overrules. Worth
            # surfacing: it usually means someone tagged a floor with the wrong
            # เขต, and it is silently not being used.
            if loc_id in own and src != loc_id and own[loc_id] != code:
                overridden[loc_id] = (own[loc_id], code)

        return resolved, {'overridden_by_ancestor': overridden,
                          'authority': authority}

    # ── Extraction ───────────────────────────────────────────────────────

    def fetch_raw(self, org_id=ORG_ID, year_from=None, include_shared_history=False):
        """Per (month, year, origin, category) weight + GHG."""
        params = {'org': org_id}
        year_clause = ''
        if year_from:
            year_clause = ' AND EXTRACT(YEAR FROM tr.transaction_date) >= %(yr)s'
            params['yr'] = year_from
        window_clause = '' if include_shared_history else self._SHARE_WINDOW_PREDICATE

        # `origin_weight_kg` is the weight as recorded at the origin, which is
        # what the tab's "ประมาณขยะที่เก็บได้" counts. GHG comes off the
        # material's own factor (materials.calc_ghg, kgCO2e per kg) rather than
        # a per-category constant, so a record with no material contributes
        # weight but no GHG — matching how the sheet's numbers were produced.
        return self._rows(self._VISIBLE_ORIGINS_CTE + f"""
            SELECT EXTRACT(MONTH FROM tr.transaction_date)::int  AS month,
                   EXTRACT(YEAR  FROM tr.transaction_date)::int  AS year,
                   t.origin_id,
                   mc.code                                       AS category_code,
                   SUM(tr.origin_weight_kg)                      AS kg,
                   SUM(tr.origin_weight_kg * COALESCE(m.calc_ghg, 0)) AS ghg
            FROM visible v
            JOIN transactions t ON t.origin_id = v.id
            JOIN transaction_records tr ON tr.created_transaction_id = t.id
            LEFT JOIN material_categories mc ON mc.id = tr.category_id
            LEFT JOIN materials           m  ON m.id  = tr.material_id
            WHERE t.deleted_date  IS NULL
              AND tr.deleted_date IS NULL
              AND tr.transaction_date IS NOT NULL
              {year_clause}
              {window_clause}
            GROUP BY 1, 2, 3, 4
        """, params)

    # ── Aggregation ──────────────────────────────────────────────────────

    def build_rows(self, org_id=ORG_ID, year_from=None,
                   include_shared_history=False):
        """Return ``(rows, stats)`` ready for the sheet."""
        district_of, resolve_info = self.resolve_districts(org_id)
        raw = self.fetch_raw(org_id, year_from, include_shared_history)

        buckets = defaultdict(lambda: {c: 0.0 for c in SHEET_COLUMNS[3:19]})
        origins = defaultdict(set)
        unmapped_kg = defaultdict(float)
        mapped_kg = 0.0

        for month, year, origin_id, cat_code, kg, ghg in raw:
            kg = float(kg or 0)
            ghg = float(ghg or 0)
            county = district_of.get(origin_id)
            if not county:
                unmapped_kg[origin_id] += kg
                continue
            mapped_kg += kg
            key = (month, year, county)
            buckets[key][CATEGORY_TO_COLUMN.get(cat_code, UNMAPPED_CATEGORIES_GO_TO)] += kg
            buckets[key]['Reduce greenhouse gas emissions'] += ghg
            if origin_id is not None:
                origins[key].add(int(origin_id))

        rows = []
        for (month, year, county), vals in sorted(buckets.items()):
            organic = vals['organic waste']
            recyclable = vals['recycled materials']
            general = vals['general waste']
            all_waste = sum(vals[CATEGORY_TO_COLUMN[c]] for c in CATEGORY_TO_COLUMN)
            recycling = recyclable + organic
            ghg = vals['Reduce greenhouse gas emissions']
            rows.append({
                'Month': month, 'Year': year, 'County': county,
                'organic waste': organic,
                'recycled materials': recyclable,
                'energy waste': vals['energy waste'],
                'hazardous waste': vals['hazardous waste'],
                'infectious waste': vals['infectious waste'],
                'electronic waste': vals['electronic waste'],
                'general waste': general,
                'all waste': all_waste,
                'recycling waste': recycling,
                'Recyclable rate': (recycling / all_waste * 100) if all_waste else 0.0,
                'Reduce greenhouse gas emissions': ghg,
                'comparable to a tree': ghg / KG_CO2_PER_TREE_YEAR,
                'Equal driving distance': ghg * DRIVING_KM_PER_KG_CO2,
                'Reduce landfill area compared to bus size.': ghg / KG_CO2_PER_BUS,
                'Reduce landfilling': all_waste - general,
                'food waste management': organic,
                'origin': ','.join(str(i) for i in sorted(origins[(month, year, county)])),
            })

        total_kg = mapped_kg + sum(unmapped_kg.values())
        stats = {
            'rows': len(rows),
            'locations_with_district': len(district_of),
            'districts_overridden_by_ancestor': len(
                resolve_info['overridden_by_ancestor']),
            'mapped_kg': round(mapped_kg, 2),
            'unmapped_kg': round(sum(unmapped_kg.values()), 2),
            'coverage_pct': round(mapped_kg / total_kg * 100, 2) if total_kg else 0.0,
            'unmapped_origin_ids': sorted(unmapped_kg, key=unmapped_kg.get, reverse=True)[:20],
        }
        return rows, stats

    # ── Origin tab ───────────────────────────────────────────────────────

    def _chart_edges(self, org_id=ORG_ID):
        """child id -> parent id, from the active org chart JSON.

        `organization_setup` keeps one row per saved revision — 904 of them for
        org 67 — so the `is_active` row is the only one that means anything.
        Node ids can be temporary client-side strings on unsaved nodes, hence
        `to_node_id` rather than `int()`.
        """
        from GEPPPlatform.libs.node_ids import to_node_id

        rows = self._rows("""
            SELECT root_nodes
            FROM organization_setup
            WHERE organization_id = %(org)s
              AND deleted_date IS NULL
              AND is_active
            ORDER BY version DESC NULLS LAST, updated_date DESC
            LIMIT 1
        """, {'org': org_id})
        if not rows or not rows[0][0]:
            return {}

        tree = rows[0][0]
        if isinstance(tree, str):
            tree = json.loads(tree)

        edges = {}

        def walk(nodes, parent_id):
            for node in nodes or []:
                if not isinstance(node, dict):
                    continue
                nid = to_node_id(node.get('nodeId') or node.get('id'))
                if nid is not None and parent_id is not None:
                    edges[nid] = parent_id
                walk(node.get('children'), nid if nid is not None else parent_id)

        walk(tree if isinstance(tree, list) else tree.get('children'), None)
        return edges

    def origin_metrics(self, org_id=ORG_ID, include_shared_history=False):
        """Per-origin monthly averages, keyed by user_location id.

        "Monthly average" is the sheet's own definition, recovered by matching
        71 of its rows against the database: the total divided by the number of
        DISTINCT MONTHS that actually have data — not by the months elapsed. A
        site that reported in 5 months is divided by 5.
        """
        district_of, _ = self.resolve_districts(org_id)
        window_clause = '' if include_shared_history else self._SHARE_WINDOW_PREDICATE
        rows = self._rows(self._VISIBLE_ORIGINS_CTE + f"""
            SELECT t.origin_id,
                   COALESCE(ul.name_th, ul.name_en, ul.display_name,
                            ul.company_name)                        AS name,
                   ul.migration_id,
                   COUNT(DISTINCT date_trunc('month', tr.transaction_date)) AS months,
                   SUM(CASE WHEN mc.code = 'RECYCLABLE' THEN tr.origin_weight_kg
                            ELSE 0 END)                             AS recyclable,
                   SUM(CASE WHEN mc.code = 'ORGANIC' THEN tr.origin_weight_kg
                            ELSE 0 END)                             AS organic,
                   SUM(tr.origin_weight_kg * COALESCE(m.calc_ghg, 0)) AS ghg
            FROM visible v
            JOIN transactions t ON t.origin_id = v.id
            JOIN transaction_records tr ON tr.created_transaction_id = t.id
            JOIN user_locations ul ON ul.id = t.origin_id
            LEFT JOIN material_categories mc ON mc.id = tr.category_id
            LEFT JOIN materials           m  ON m.id  = tr.material_id
            WHERE t.deleted_date  IS NULL
              AND tr.deleted_date IS NULL
              AND tr.transaction_date IS NOT NULL
              {window_clause}
            GROUP BY 1, 2, 3
        """, {'org': org_id})

        out = {}
        for origin_id, name, migration_id, months, rec, org, ghg in rows:
            county = district_of.get(origin_id)
            if not county:
                # No เขต means the row cannot be placed in the sheet at all.
                continue
            months = int(months or 0) or 1
            out[int(origin_id)] = {
                'id': int(origin_id),
                'migration_id': int(migration_id) if migration_id else None,
                'name': (name or '').strip(),
                'county': county,
                'recyclable': float(rec or 0) / months,
                'organic': float(org or 0) / months,
                'ghg': float(ghg or 0) / months,
                'months': months,
            }
        return out

    def build_origin_rows(self, existing, org_id=ORG_ID, added_on=None,
                          include_shared_history=False):
        """Merge computed metrics into the tab's rows.

        Returns ``(rows, stats)``. Existing rows keep every column this service
        does not own; unknown origins are appended and stamped with `Added On`.
        Rows the database says nothing about (the ~3,700 all-zero master-list
        entries) pass through untouched.
        """
        added_on = added_on or datetime.now(_BANGKOK_TZ).strftime('%Y-%m-%d')
        metrics = self.origin_metrics(org_id, include_shared_history)
        width = len(ORIGIN_COLUMNS)

        def pad(row):
            row = list(row)
            return row + [''] * (width - len(row)) if len(row) < width else row[:width]

        rows = [pad(r) for r in existing]

        # Index the sheet: by id first (authoritative), then by name for rows
        # written before the ID column existed. First name wins — later
        # duplicates are left alone rather than being fought over.
        by_id, by_name = {}, {}
        for i, r in enumerate(rows):
            rid = str(r[ORIGIN_COL['GEPP Location ID']]).strip()
            if rid.isdigit():
                by_id.setdefault(int(rid), i)
            key = str(r[ORIGIN_COL['Name']]).strip().lower()
            if key:
                by_name.setdefault(key, i)

        updated = appended = 0
        for m in sorted(metrics.values(), key=lambda x: x['name'].lower()):
            idx = by_id.get(m['id'])
            if idx is None:
                idx = by_name.get(m['name'].lower())
            if idx is not None:
                row = rows[idx]
                for col in ORIGIN_UPDATABLE_EXISTING:
                    key = 'recyclable' if col.startswith('Recyclable') else 'organic'
                    row[ORIGIN_COL[col]] = round(m[key], 5)
                row[ORIGIN_COL['County']] = m['county']
                # Backfill the id so the next run matches on it, not on a name.
                row[ORIGIN_COL['GEPP Location ID']] = m['id']
                by_id.setdefault(m['id'], idx)
                updated += 1
            else:
                row = [''] * width
                row[ORIGIN_COL['Name']] = m['name']
                row[ORIGIN_COL['County']] = m['county']
                # Baseline / Landfill are surveyed on site — left blank rather
                # than zero, so a missing survey never reads as "no waste".
                row[ORIGIN_COL['Recyclable Material\n(Monthly Average)']] = round(m['recyclable'], 5)
                row[ORIGIN_COL['Organic Material\n(Monthly Average)']] = round(m['organic'], 5)
                row[ORIGIN_COL['Greenhouse Gas Reduction\n(Monthly Average)']] = round(m['ghg'], 5)
                row[ORIGIN_COL['GEPP Location ID']] = m['id']
                row[ORIGIN_COL['Added On']] = added_on
                rows.append(row)
                by_id[m['id']] = len(rows) - 1
                appended += 1

        return rows, {'origins_with_county': len(metrics),
                      'origin_rows_updated': updated,
                      'origin_rows_appended': appended,
                      'origin_rows_total': len(rows)}

    @staticmethod
    def overall_from_origin(rows):
        """`Overall Project` = Σ(Origin) / 1000, in tonnes.

        Proven against the published values: the tab's Baseline of 829.540 and
        Landfill Reduction of 132.023 are exactly the Origin column sums
        (829,540.390 kg and 132,022.570 kg) divided by 1000.
        """
        def total(col):
            s = 0.0
            for r in rows:
                i = ORIGIN_COL[col]
                if len(r) > i:
                    try:
                        s += float(str(r[i]).replace(',', '') or 0)
                    except ValueError:
                        pass
            return s
        return (round(total('Baseline Data') / 1000, 3),
                round(total('Landfill Waste Reduction\n(Monthly Average)') / 1000, 3))

    def sync_origin_and_overall(self, org_id=ORG_ID, sheet_id=None, dry_run=False,
                                include_shared_history=False):
        """Update the `Origin` tab, then re-total `Overall Project` from it."""
        from GEPPPlatform.libs.google_sa_auth import SheetsClient

        sheet_id = sheet_id or os.environ.get('BMA_GSHEET_ID', DEFAULT_SHEET_ID)
        client = SheetsClient(self._load_service_account())
        start = DEFAULT_START_ROW

        raw = client.get(
            sheet_id, f"'{ORIGIN_TAB}'!A{start}:Z100000").get('values', []) or []
        existing = [r for r in raw if r and str(r[0]).strip()]
        rows, stats = self.build_origin_rows(
            existing, org_id, include_shared_history=include_shared_history)
        baseline_t, landfill_t = self.overall_from_origin(rows)
        stats.update({'overall_baseline_tonne': baseline_t,
                      'overall_landfill_reduction_tonne': landfill_t})
        if dry_run:
            return {'dry_run': True, **stats}

        end_col = 'L'      # 12 columns
        client.clear(sheet_id, f"'{ORIGIN_TAB}'!A{start}:{end_col}100000")
        client.update(sheet_id, f"'{ORIGIN_TAB}'!A{start}", rows)
        # Label the two columns we added, on the English header row.
        client.update(sheet_id, f"'{ORIGIN_TAB}'!K2",
                      [[ORIGIN_COLUMNS[10], ORIGIN_COLUMNS[11]]])
        # `Overall Project` data sits on its single row 3.
        client.update(sheet_id, f"'{OVERALL_TAB}'!A{start}",
                      [[baseline_t, landfill_t]])
        return {'dry_run': False, **stats}

    # ── Google Sheets ────────────────────────────────────────────────────

    @staticmethod
    def _load_service_account():
        """The service-account key JSON, as a dict."""
        raw = os.environ.get('BMA_GSHEET_SA_JSON')
        if raw:
            return json.loads(raw)

        secret_id = os.environ.get('BMA_GSHEET_SA_SECRET_ID')
        if secret_id:
            # boto3 ships with the Lambda runtime, so this needs no layer entry.
            import boto3
            sm = boto3.client('secretsmanager')
            return json.loads(sm.get_secret_value(SecretId=secret_id)['SecretString'])

        path = os.environ.get('BMA_GSHEET_SA_FILE')
        if path:
            with open(path, encoding='utf-8') as fh:
                return json.load(fh)

        raise RuntimeError(
            'No Google credentials. Set BMA_GSHEET_SA_JSON, '
            'BMA_GSHEET_SA_SECRET_ID or BMA_GSHEET_SA_FILE.'
        )

    @staticmethod
    def _row_year(raw_row):
        """Year out of a raw sheet row, or None if the row isn't data."""
        if len(raw_row) < 2:
            return None
        try:
            return int(float(str(raw_row[1]).strip()))
        except (TypeError, ValueError):
            return None

    def push(self, rows, sheet_id=None, tab=DEFAULT_TAB,
             start_row=DEFAULT_START_ROW, replace_years=None):
        """Write rows into the tab, leaving its two header rows intact.

        `replace_years` scopes the write: only rows for those years are touched,
        and every other existing row is read back and rewritten unchanged. That
        matters here because this tab carries a second data set we cannot
        reproduce — 'general waste'-only rows for all 50 เขต, sourced from BMA
        rather than from our transactions. A blanket overwrite would silently
        delete ~450 tonnes of it. Pass None to replace the whole tab.
        """
        from GEPPPlatform.libs.google_sa_auth import SheetsClient

        sheet_id = sheet_id or os.environ.get('BMA_GSHEET_ID', DEFAULT_SHEET_ID)
        client = SheetsClient(self._load_service_account())
        ncols = len(SHEET_COLUMNS)

        if replace_years:
            years = {int(y) for y in replace_years}
            existing = client.get(
                sheet_id, f"'{tab}'!A{start_row}:T100000").get('values', []) or []
            kept = [r for r in existing
                    if r and any(str(c).strip() for c in r)
                    and self._row_year(r) not in years]
            fresh = [[r[c] for c in SHEET_COLUMNS]
                     for r in rows if r['Year'] in years]
            # Pad the rows we read back: the API right-trims empty trailing
            # cells, and a short row would shift nothing but reads as ragged.
            kept = [list(r) + [''] * (ncols - len(r)) if len(r) < ncols else list(r)
                    for r in kept]
            values = kept + fresh
            summary = {'rows_kept': len(kept), 'rows_written': len(fresh),
                       'replaced_years': sorted(years)}
        else:
            values = [[r[c] for c in SHEET_COLUMNS] for r in rows]
            summary = {'rows_kept': 0, 'rows_written': len(values),
                       'replaced_years': 'all'}

        # Clear before writing: a shorter dataset must not leave stale rows
        # below it, which would be double-counted by the Master-* pivots.
        client.clear(sheet_id, f"'{tab}'!A{start_row}:T100000")
        if values:
            client.update(sheet_id, f"'{tab}'!A{start_row}", values)
        return {'sheet_id': sheet_id, 'tab': tab,
                'total_rows_in_tab': len(values), **summary}

    # ── Orchestration ────────────────────────────────────────────────────

    def run(self, org_id=ORG_ID, year_from=None, dry_run=False,
            sheet_id=None, tab=DEFAULT_TAB, replace_years=None,
            include_shared_history=False):
        """Build and push.

        `replace_years` defaults to `default_managed_years()` — this year and
        last. Years before `MANAGED_FROM_YEAR` are dropped from any request:
        the tab's earlier rows hold BMA-sourced 'general waste' for all 50 เขต
        that v3 cannot regenerate, plus hand-curated history, and a scheduled
        job must not be one wrong parameter away from deleting them.
        `REPLACE_ALL` is the single deliberate override.
        """
        if replace_years == REPLACE_ALL:
            replace_years = None            # the push() sentinel for "all"
        else:
            if replace_years is None:
                replace_years = default_managed_years()
            requested = {int(y) for y in replace_years}
            replace_years = sorted(y for y in requested if y >= MANAGED_FROM_YEAR)
            refused = sorted(requested - set(replace_years))
            if refused:
                _logger.warning(
                    'BMA gsheet: refusing to write %s — this cron only manages '
                    '%s onward. Use replace_years="all" to override.',
                    refused, MANAGED_FROM_YEAR)
            if not replace_years:
                return {'skipped': 'no writable years requested',
                        'refused_years': refused,
                        'managed_from_year': MANAGED_FROM_YEAR}

        rows, stats = self.build_rows(org_id, year_from, include_shared_history)
        if replace_years:
            years = {int(y) for y in replace_years}
            scoped = [r for r in rows if r['Year'] in years]
            stats['rows_in_scope'] = len(scoped)
            stats['scope_kg'] = round(sum(r['all waste'] for r in scoped), 2)
            if not scoped:
                # Better a loud no-op than clearing the year's rows because a
                # month's data has not landed yet.
                _logger.warning(
                    'BMA gsheet: nothing built for %s — skipping the write so '
                    'existing rows are left alone', sorted(years))
                return {'dry_run': dry_run, 'skipped': 'no rows in scope',
                        **stats}
        _logger.info('BMA gsheet: built %s rows, coverage %.1f%%%s',
                     stats['rows'], stats['coverage_pct'],
                     f", {stats['rows_in_scope']} in scope" if replace_years else '')
        if dry_run:
            return {'dry_run': True, **stats}
        push = self.push(rows, sheet_id=sheet_id, tab=tab,
                         replace_years=replace_years)
        return {'dry_run': False, **stats, **push}
