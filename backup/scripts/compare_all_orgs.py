"""
Compare ALL transactions between old MySQL (production) and new PostgreSQL
for years 2020-2025. No org filter — just compare by record migration_id.
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

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}


def main():
    print("Connecting to databases...", flush=True)
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
    pg_cur = pg_conn.cursor()

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        start = f"{year}-01-01"
        end = f"{year}-12-31 23:59:59"
        print(f"\n{'='*80}", flush=True)
        print(f"YEAR {year}", flush=True)
        print(f"{'='*80}", flush=True)

        # ===== OLD DB: All transactions for this year =====
        print(f"  Querying old MySQL...", flush=True)
        mysql_cur.execute("""
            SELECT t.id AS tx_id, t.organization
            FROM transactions t
            WHERE t.transaction_date BETWEEN %s AND %s
              AND t.transaction_type = 1
              AND t.deleted_date IS NULL
        """, (start, end))
        old_txs = mysql_cur.fetchall()
        old_tx_ids = [t['tx_id'] for t in old_txs]
        old_tx_orgs = {t['tx_id']: t['organization'] for t in old_txs}

        if not old_tx_ids:
            print(f"  OLD: 0 transactions", flush=True)
        else:
            # Batch query records
            batch_size = 5000
            old_records = []
            for i in range(0, len(old_tx_ids), batch_size):
                batch = old_tx_ids[i:i+batch_size]
                ids_str = ",".join([str(t) for t in batch])
                mysql_cur.execute(f"""
                    SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity,
                           tr.status, tr.journey_id, tr.material,
                           m.unit_weight
                    FROM transaction_records tr
                    JOIN materials m ON tr.material = m.id
                    WHERE tr.transaction_id IN ({ids_str})
                      AND tr.deleted_date IS NULL
                """)
                old_records.extend(mysql_cur.fetchall())

            # Dedup by journey_id
            old_hops = {}
            for r in old_records:
                key = f"{r['transaction_id']}_{r['journey_id']}"
                old_hops[key] = r
            old_non_rej = {k: v for k, v in old_hops.items() if v['status'] != 'rejected'}

            old_total = sum(float(v['quantity'] or 0) * float(v['unit_weight'] or 0) for v in old_non_rej.values())
            old_rec_data = {}
            for v in old_non_rej.values():
                w = float(v['quantity'] or 0) * float(v['unit_weight'] or 0)
                old_rec_data[v['rec_id']] = {
                    'weight': w,
                    'org': old_tx_orgs.get(v['transaction_id']),
                    'tx_id': v['transaction_id'],
                    'mat_id': v['material'],
                }
            print(f"  OLD: {len(old_non_rej)} records, {old_total:.2f} kg", flush=True)

        # ===== NEW DB: All records for this year =====
        print(f"  Querying new PostgreSQL...", flush=True)
        pg_cur.execute("""
            SELECT tr.id AS rec_id, tr.migration_id,
                   tr.origin_quantity AS qty,
                   tr.status,
                   m.unit_weight,
                   t.organization_id,
                   t.migration_id AS tx_mig_id
            FROM transaction_records tr
            JOIN transactions t ON tr.created_transaction_id = t.id
            LEFT JOIN materials m ON tr.material_id = m.id
            WHERE t.deleted_date IS NULL AND tr.deleted_date IS NULL
              AND (tr.status != 'rejected' OR tr.status IS NULL)
              AND tr.transaction_date >= %s AND tr.transaction_date <= %s
        """, (start, end))
        new_records = pg_cur.fetchall()
        new_total = sum(float(r['qty'] or 0) * float(r['unit_weight'] or 0) for r in new_records)
        new_by_mig = {}
        for r in new_records:
            if r['migration_id']:
                new_by_mig[int(r['migration_id'])] = r
        print(f"  NEW: {len(new_records)} records, {new_total:.2f} kg", flush=True)

        if not old_tx_ids and not new_records:
            print(f"  No data for {year}", flush=True)
            continue

        # ===== COMPARE =====
        diff = new_total - old_total if old_tx_ids else new_total
        print(f"  DIFF: {diff:+.2f} kg", flush=True)

        if abs(diff) < 0.1:
            print(f"  ✓ MATCH", flush=True)
            continue

        # Find records in OLD but not in NEW
        old_only = []
        if old_tx_ids:
            for rec_id, data in old_rec_data.items():
                if rec_id not in new_by_mig:
                    old_only.append((rec_id, data))

        old_only_weight = sum(d['weight'] for _, d in old_only)
        if old_only:
            # Group by org
            by_org = defaultdict(lambda: {"count": 0, "weight": 0.0, "recs": []})
            for rec_id, data in old_only:
                org = data['org']
                by_org[org]["count"] += 1
                by_org[org]["weight"] += data['weight']
                by_org[org]["recs"].append((rec_id, data))

            print(f"\n  Records in OLD but NOT in NEW: {len(old_only)}, weight: {old_only_weight:.2f} kg", flush=True)
            for org in sorted(by_org, key=lambda o: -by_org[o]["weight"]):
                d = by_org[org]
                print(f"    org={org}: {d['count']} recs, {d['weight']:.2f} kg", flush=True)

        # Find records in NEW but not in OLD
        new_rec_ids = set(old_rec_data.keys()) if old_tx_ids else set()
        new_only = []
        for r in new_records:
            mid = int(r['migration_id']) if r['migration_id'] else None
            if mid and mid not in new_rec_ids:
                new_only.append(r)
            elif not mid:
                new_only.append(r)

        new_only_weight = sum(float(r['qty'] or 0) * float(r['unit_weight'] or 0) for r in new_only)
        if new_only:
            by_org = defaultdict(lambda: {"count": 0, "weight": 0.0})
            for r in new_only:
                org = r['organization_id']
                w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
                by_org[org]["count"] += 1
                by_org[org]["weight"] += w

            print(f"\n  Records in NEW but NOT in OLD: {len(new_only)}, weight: {new_only_weight:.2f} kg", flush=True)
            for org in sorted(by_org, key=lambda o: -by_org[o]["weight"]):
                d = by_org[org]
                # Look up org name
                pg_cur.execute("SELECT name, migration_id FROM organizations WHERE id = %s", (org,))
                org_info = pg_cur.fetchone()
                org_name = org_info['name'] if org_info else '?'
                old_org = org_info['migration_id'] if org_info else '?'
                print(f"    new_org={org} (old={old_org}, {org_name}): {d['count']} recs, {d['weight']:.2f} kg", flush=True)

        # Weight diffs in matched records
        if old_tx_ids:
            weight_diffs = []
            for rec_id, data in old_rec_data.items():
                if rec_id in new_by_mig:
                    nr = new_by_mig[rec_id]
                    new_w = float(nr['qty'] or 0) * float(nr['unit_weight'] or 0)
                    if abs(data['weight'] - new_w) > 0.01:
                        weight_diffs.append((rec_id, data, new_w))
            if weight_diffs:
                total_wdiff = sum(d['weight'] - nw for _, d, nw in weight_diffs)
                print(f"\n  Weight diffs in matched records: {len(weight_diffs)}, net: {total_wdiff:+.2f} kg", flush=True)
                for rec_id, data, nw in sorted(weight_diffs, key=lambda x: -abs(x[1]['weight']-x[2]))[:10]:
                    print(f"    rec_id={rec_id}, old={data['weight']:.2f}, new={nw:.2f}, diff={data['weight']-nw:+.2f}, org={data['org']}", flush=True)

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
