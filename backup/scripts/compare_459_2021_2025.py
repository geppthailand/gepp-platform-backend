"""
Compare old MySQL (production) vs new PostgreSQL for org 459/141, years 2021-2025.
Find total and category differences.
"""

import pymysql
import psycopg2
import psycopg2.extras
from collections import defaultdict

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310,
    "user": "admin",
    "password": "GeppThailand123456$",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

OLD_ORG = 459
NEW_ORG = 141


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    DATE_FROM = "2021-01-01"
    DATE_TO = "2025-12-31 23:59:59"

    # ===== OLD DB =====
    mysql_cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (OLD_ORG,))
    biz_ids = [r['id'] for r in mysql_cur.fetchall()]
    biz_ids_str = ",".join([str(b) for b in biz_ids])

    mysql_cur.execute(f"""
        SELECT t.id FROM transactions t
        WHERE t.transaction_date BETWEEN %s AND %s
          AND t.transaction_type = 1
          AND t.`business-unit` IN ({biz_ids_str})
          AND t.deleted_date IS NULL
    """, (DATE_FROM, DATE_TO))
    old_tx_ids = [r['id'] for r in mysql_cur.fetchall()]

    if old_tx_ids:
        tx_ids_str = ",".join([str(t) for t in old_tx_ids])
        mysql_cur.execute(f"""
            SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status,
                   tr.material, tr.journey_id,
                   m.unit_weight, m.name_en AS mat_name, m.material_category_id AS cat_id,
                   mc.name_en AS cat_name,
                   t.transaction_date
            FROM transaction_records tr
            JOIN materials m ON tr.material = m.id
            LEFT JOIN material_categories mc ON m.material_category_id = mc.id
            JOIN transactions t ON tr.transaction_id = t.id
            WHERE tr.transaction_id IN ({tx_ids_str})
              AND tr.deleted_date IS NULL
        """)
        old_records = mysql_cur.fetchall()
    else:
        old_records = []

    # Dedup
    old_hops = {}
    for r in old_records:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        old_hops[key] = r
    old_non_rej = {k: v for k, v in old_hops.items() if v['status'] != 'rejected'}

    old_total = sum(float(v['quantity'] or 0) * float(v['unit_weight'] or 0) for v in old_non_rej.values())
    print(f"OLD DB: {len(old_non_rej)} records, total={old_total:.2f} kg")

    # Old by category
    old_by_cat = defaultdict(float)
    old_by_cat_count = defaultdict(int)
    for v in old_non_rej.values():
        w = float(v['quantity'] or 0) * float(v['unit_weight'] or 0)
        cat = v['cat_name'] or f"cat_{v['cat_id']}"
        old_by_cat[cat] += w
        old_by_cat_count[cat] += 1

    print("\nOLD by category:")
    for cat in sorted(old_by_cat, key=lambda c: -old_by_cat[c]):
        print(f"  {cat}: {old_by_cat_count[cat]} recs, {old_by_cat[cat]:.2f} kg")

    # Old by year
    old_by_year = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for v in old_non_rej.values():
        w = float(v['quantity'] or 0) * float(v['unit_weight'] or 0)
        year = v['transaction_date'].year if v['transaction_date'] else '?'
        old_by_year[year]["count"] += 1
        old_by_year[year]["weight"] += w

    print("\nOLD by year:")
    for y in sorted(old_by_year):
        print(f"  {y}: {old_by_year[y]['count']} recs, {old_by_year[y]['weight']:.2f} kg")

    # ===== NEW DB =====
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity AS qty,
               tr.status, tr.transaction_date,
               m.unit_weight, m.name_en AS mat_name,
               m.category_id AS mat_cat_id,
               mc.name_en AS cat_name
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        LEFT JOIN material_categories mc ON m.category_id = mc.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    new_records = pg_cur.fetchall()

    new_total = sum(float(r['qty'] or 0) * float(r['unit_weight'] or 0) for r in new_records)
    print(f"\nNEW DB: {len(new_records)} records, total={new_total:.2f} kg")

    # New by category
    new_by_cat = defaultdict(float)
    new_by_cat_count = defaultdict(int)
    for r in new_records:
        w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
        cat = r['cat_name'] or f"cat_{r['mat_cat_id']}"
        new_by_cat[cat] += w
        new_by_cat_count[cat] += 1

    print("\nNEW by category:")
    for cat in sorted(new_by_cat, key=lambda c: -new_by_cat[c]):
        print(f"  {cat}: {new_by_cat_count[cat]} recs, {new_by_cat[cat]:.2f} kg")

    # New by year
    new_by_year = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in new_records:
        if r['transaction_date']:
            year = r['transaction_date'].year
        else:
            year = '?'
        w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
        new_by_year[year]["count"] += 1
        new_by_year[year]["weight"] += w

    print("\nNEW by year:")
    for y in sorted(new_by_year):
        print(f"  {y}: {new_by_year[y]['count']} recs, {new_by_year[y]['weight']:.2f} kg")

    # ===== COMPARE BY YEAR =====
    print(f"\n{'='*70}")
    print("YEAR-BY-YEAR COMPARISON:")
    all_years = sorted(set(list(old_by_year.keys()) + list(new_by_year.keys())))
    for y in all_years:
        oc = old_by_year.get(y, {}).get("count", 0)
        ow = old_by_year.get(y, {}).get("weight", 0.0)
        nc = new_by_year.get(y, {}).get("count", 0)
        nw = new_by_year.get(y, {}).get("weight", 0.0)
        diff = nw - ow
        marker = "" if abs(diff) < 0.1 else f" *** diff={diff:+.2f}"
        print(f"  {y}: old={oc} recs/{ow:.2f} kg, new={nc} recs/{nw:.2f} kg{marker}")

    # ===== COMPARE RECORDS =====
    print(f"\n{'='*70}")
    print("RECORD-LEVEL COMPARISON (by migration_id):")

    old_rec_ids = set(v['rec_id'] for v in old_non_rej.values())
    new_by_mig = {}
    for r in new_records:
        if r['migration_id']:
            new_by_mig[int(r['migration_id'])] = r

    # Records in OLD but not in NEW
    old_only = []
    for v in old_non_rej.values():
        if v['rec_id'] not in new_by_mig:
            old_only.append(v)

    old_only_weight = sum(float(r['quantity'] or 0) * float(r['unit_weight'] or 0) for r in old_only)
    print(f"\nRecords in OLD but NOT in NEW: {len(old_only)}, weight: {old_only_weight:.2f} kg")
    # Group by year
    old_only_by_year = defaultdict(lambda: {"count": 0, "weight": 0.0, "records": []})
    for r in old_only:
        y = r['transaction_date'].year if r['transaction_date'] else '?'
        w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
        old_only_by_year[y]["count"] += 1
        old_only_by_year[y]["weight"] += w
        old_only_by_year[y]["records"].append(r)
    for y in sorted(old_only_by_year):
        d = old_only_by_year[y]
        print(f"  {y}: {d['count']} recs, {d['weight']:.2f} kg")
        for r in sorted(d["records"], key=lambda x: -abs(float(x['quantity'] or 0) * float(x['unit_weight'] or 0)))[:5]:
            w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
            print(f"    rec_id={r['rec_id']}, tx_id={r['transaction_id']}, w={w:.2f}, mat={r['mat_name']}, cat={r['cat_name']}, date={r['transaction_date']}")

    # Records in NEW but not in OLD
    new_only = []
    for r in new_records:
        mid = int(r['migration_id']) if r['migration_id'] else None
        if mid and mid not in old_rec_ids:
            new_only.append(r)
        elif not mid:
            new_only.append(r)

    new_only_weight = sum(float(r['qty'] or 0) * float(r['unit_weight'] or 0) for r in new_only)
    print(f"\nRecords in NEW but NOT in OLD: {len(new_only)}, weight: {new_only_weight:.2f} kg")
    new_only_by_year = defaultdict(lambda: {"count": 0, "weight": 0.0, "records": []})
    for r in new_only:
        y = r['transaction_date'].year if r['transaction_date'] else '?'
        w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
        new_only_by_year[y]["count"] += 1
        new_only_by_year[y]["weight"] += w
        new_only_by_year[y]["records"].append(r)
    for y in sorted(new_only_by_year):
        d = new_only_by_year[y]
        print(f"  {y}: {d['count']} recs, {d['weight']:.2f} kg")
        for r in sorted(d["records"], key=lambda x: -abs(float(x['qty'] or 0) * float(x['unit_weight'] or 0)))[:5]:
            w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
            print(f"    rec_id={r['rec_id']}, mig_id={r['migration_id']}, w={w:.2f}, mat={r['mat_name']}, cat={r['cat_name']}, date={r['transaction_date']}")

    # Weight diffs in matched records
    weight_diffs = []
    for v in old_non_rej.values():
        if v['rec_id'] in new_by_mig:
            nr = new_by_mig[v['rec_id']]
            old_w = float(v['quantity'] or 0) * float(v['unit_weight'] or 0)
            new_w = float(nr['qty'] or 0) * float(nr['unit_weight'] or 0)
            if abs(old_w - new_w) > 0.01:
                weight_diffs.append((v, nr, old_w, new_w))

    if weight_diffs:
        total_diff = sum(ow - nw for _, _, ow, nw in weight_diffs)
        print(f"\nWeight differences in matched records: {len(weight_diffs)}, net diff: {total_diff:+.2f} kg")
        for v, nr, ow, nw in sorted(weight_diffs, key=lambda x: -abs(x[2]-x[3]))[:10]:
            print(f"  rec_id={v['rec_id']}: old={ow:.2f}, new={nw:.2f}, diff={ow-nw:+.2f}, mat={v['mat_name']}")

    # ===== SUMMARY =====
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"  OLD total: {old_total:.2f} kg ({len(old_non_rej)} records)")
    print(f"  NEW total: {new_total:.2f} kg ({len(new_records)} records)")
    print(f"  Diff: {new_total - old_total:+.2f} kg")
    print(f"  Old-only: {old_only_weight:.2f} kg ({len(old_only)} records)")
    print(f"  New-only: {new_only_weight:.2f} kg ({len(new_only)} records)")

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
