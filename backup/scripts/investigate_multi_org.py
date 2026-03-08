"""
Investigate ALL mismatches - batch approach.
For each mismatched org/year, pull all migration_ids from both DBs and compare sets.
"""

import sys
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

PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}


def investigate_org_year(pg_cur, mysql_cur, new_org, old_org, year):
    """Batch compare records for a given org/year."""
    start = f"{year}-01-01"
    end = f"{year}-12-31 23:59:59"

    # NEW DB: get all active records with migration_id
    pg_cur.execute("""
        SELECT tr.id, tr.migration_id, tr.origin_quantity AS qty,
               m.unit_weight, m.name_en AS mat_name,
               tr.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
          AND tr.migration_id IS NOT NULL
    """, (new_org, start, end))
    new_recs = {int(r['migration_id']): r for r in pg_cur.fetchall()}

    # OLD DB: get all active records
    mysql_cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (old_org,))
    biz_ids = [r['id'] for r in mysql_cur.fetchall()]
    if not biz_ids:
        return {"new_only": new_recs, "old_only": {}, "matched": 0}

    biz_str = ",".join(str(b) for b in biz_ids)
    mysql_cur.execute(f"""
        SELECT t.id FROM transactions t
        WHERE t.transaction_date BETWEEN %s AND %s
          AND t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
          AND t.deleted_date IS NULL
    """, (start, end))
    tx_ids = [r['id'] for r in mysql_cur.fetchall()]

    old_recs = {}
    if tx_ids:
        # Batch in chunks
        for i in range(0, len(tx_ids), 5000):
            batch = tx_ids[i:i+5000]
            tx_str = ",".join(str(t) for t in batch)
            mysql_cur.execute(f"""
                SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status,
                       tr.journey_id, m.unit_weight, m.name_en AS mat_name,
                       t.transaction_date
                FROM transaction_records tr
                JOIN materials m ON tr.material = m.id
                JOIN transactions t ON tr.transaction_id = t.id
                WHERE tr.transaction_id IN ({tx_str}) AND tr.deleted_date IS NULL
            """)
            for r in mysql_cur.fetchall():
                key = f"{r['transaction_id']}_{r['journey_id']}"
                old_recs[key] = r

    # Dedup and filter rejected
    old_by_recid = {}
    for v in old_recs.values():
        if v['status'] != 'rejected':
            old_by_recid[v['rec_id']] = v

    # Compare
    new_mig_ids = set(new_recs.keys())
    old_rec_ids = set(old_by_recid.keys())

    only_in_new = new_mig_ids - old_rec_ids
    only_in_old = old_rec_ids - new_mig_ids
    matched = new_mig_ids & old_rec_ids

    return {
        "new_only_ids": only_in_new,
        "old_only_ids": only_in_old,
        "matched": len(matched),
        "new_recs": new_recs,
        "old_recs": old_by_recid,
    }


def diagnose_new_only(mysql_cur, migration_ids):
    """For records only in new DB, check WHY they're not in old report."""
    if not migration_ids:
        return {}

    reasons = defaultdict(list)
    ids_list = list(migration_ids)

    # Batch check in old DB
    for i in range(0, len(ids_list), 500):
        batch = ids_list[i:i+500]
        placeholders = ",".join(["%s"] * len(batch))

        mysql_cur.execute(f"""
            SELECT tr.id AS rec_id, tr.transaction_id, tr.deleted_date AS tr_del,
                   t.deleted_date AS tx_del, t.transaction_type, t.organization
            FROM transaction_records tr
            JOIN transactions t ON tr.transaction_id = t.id
            WHERE tr.id IN ({placeholders})
        """, batch)
        rows = mysql_cur.fetchall()
        found_ids = set()

        for r in rows:
            found_ids.add(r['rec_id'])
            if r['tr_del']:
                reasons["rec deleted in old"].append(r['rec_id'])
            elif r['tx_del']:
                reasons["tx deleted in old"].append(r['rec_id'])
            elif r['transaction_type'] != 1:
                reasons[f"tx type={r['transaction_type']}"].append(r['rec_id'])
            else:
                reasons["exists but filtered (biz-unit?)"].append(r['rec_id'])

        not_found = set(batch) - found_ids
        for nf in not_found:
            reasons["rec not found in old DB"].append(nf)

    return reasons


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
    pg_cur = pg_conn.cursor()

    cases = [
        # (new_org, old_org, year)
        (141, 459, 2020),
        (83, 401, 2023),
        (83, 401, 2024),
        (113, 431, 2023), (113, 431, 2024),
        (133, 451, 2023), (133, 451, 2024),
        (136, 454, 2023), (136, 454, 2024), (136, 454, 2025),
        (37, 353, 2023),
        (1783, 2105, 2024),
        (117, 435, 2024),
        (58, 375, 2024),
        (2130, 2452, 2025),
        (2215, 2537, 2025),
    ]

    # Also check old-only orgs
    old_only_orgs = [(443, 2023), (384, 2025)]
    for old_id, year in old_only_orgs:
        pg_cur.execute("SELECT id, name FROM organizations WHERE migration_id = %s", (str(old_id),))
        r = pg_cur.fetchone()
        if r:
            print(f"Old org {old_id} -> new org {r['id']} ({r['name']})", flush=True)
            cases.append((r['id'], old_id, year))

    all_to_delete = []  # (new_rec_id, ...)
    all_missing = []     # records in old but not new

    for new_org, old_org, year in cases:
        print(f"\n{'='*60}", flush=True)
        print(f"org old={old_org} / new={new_org}, year={year}", flush=True)
        print(f"{'='*60}", flush=True)

        result = investigate_org_year(pg_cur, mysql_cur, new_org, old_org, year)

        new_only = result['new_only_ids']
        old_only = result['old_only_ids']
        matched = result['matched']
        new_recs = result['new_recs']
        old_recs = result['old_recs']

        new_only_w = sum(
            float(new_recs[mid]['qty'] or 0) * float(new_recs[mid]['unit_weight'] or 0)
            for mid in new_only
        )
        old_only_w = sum(
            float(old_recs[rid]['quantity'] or 0) * float(old_recs[rid]['unit_weight'] or 0)
            for rid in old_only
        )

        print(f"  Matched: {matched}", flush=True)
        print(f"  Only in NEW: {len(new_only)}, {new_only_w:.2f} kg", flush=True)
        print(f"  Only in OLD: {len(old_only)}, {old_only_w:.2f} kg", flush=True)

        if new_only:
            reasons = diagnose_new_only(mysql_cur, new_only)
            for reason, ids in sorted(reasons.items(), key=lambda x: -len(x[1])):
                w = sum(float(new_recs[mid]['qty'] or 0) * float(new_recs[mid]['unit_weight'] or 0) for mid in ids)
                print(f"    -> {reason}: {len(ids)} recs, {w:.2f} kg", flush=True)
                for mid in ids:
                    all_to_delete.append((new_recs[mid]['id'], mid, reason, new_org, old_org, year,
                                         float(new_recs[mid]['qty'] or 0) * float(new_recs[mid]['unit_weight'] or 0)))

        if old_only:
            for rid in sorted(old_only)[:5]:
                r = old_recs[rid]
                w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
                print(f"    OLD rec={rid}, w={w:.2f}, mat={r['mat_name']}, date={r['transaction_date']}", flush=True)
                all_missing.append((rid, w, old_org, new_org, year))
            if len(old_only) > 5:
                print(f"    ... and {len(old_only)-5} more", flush=True)

    # ===== SUMMARY =====
    print(f"\n{'='*80}", flush=True)
    print("SUMMARY", flush=True)
    print(f"{'='*80}", flush=True)

    # Group deletions by org/year/reason
    del_by_group = defaultdict(lambda: {"count": 0, "weight": 0.0, "ids": []})
    for new_id, mig_id, reason, new_org, old_org, year, w in all_to_delete:
        key = f"old={old_org}/new={new_org} {year} [{reason}]"
        del_by_group[key]["count"] += 1
        del_by_group[key]["weight"] += w
        del_by_group[key]["ids"].append(new_id)

    total_del = len(all_to_delete)
    total_del_w = sum(x[6] for x in all_to_delete)
    print(f"\nTO SOFT-DELETE in new PG: {total_del} records, {total_del_w:.2f} kg", flush=True)
    for key in sorted(del_by_group):
        d = del_by_group[key]
        print(f"  {key}: {d['count']} recs, {d['weight']:.2f} kg", flush=True)

    if all_missing:
        total_miss = len(all_missing)
        total_miss_w = sum(x[1] for x in all_missing)
        print(f"\nMISSING from new PG (in old but not new): {total_miss} records, {total_miss_w:.2f} kg", flush=True)

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
