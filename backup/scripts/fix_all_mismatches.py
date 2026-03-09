"""
Fix ALL mismatches found between old MySQL and new PostgreSQL.

Issues to fix:
1. tx type=2 records in new PG (10,247 recs, org 401/83) -> soft-delete
2. tx deleted in old (5 recs, org 459/141, 2020) -> soft-delete
3. biz-unit filtered records (1,066 recs, multiple orgs) -> soft-delete
4. org 384/67 missing 5 records (25,818 kg) -> insert
"""

import sys
import pymysql
import psycopg2
import psycopg2.extras
from collections import defaultdict
from datetime import datetime

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

NOW = "2026-03-07 00:00:00+07"


def collect_ids_to_delete(pg_cur, mysql_cur):
    """Collect all new PG record IDs that need to be soft-deleted."""
    all_delete_ids = []  # (new_rec_id, reason, new_org, old_org, year)

    cases = [
        (141, 459, 2020),
        (83, 401, 2023), (83, 401, 2024),
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

    for new_org, old_org, year in cases:
        start = f"{year}-01-01"
        end = f"{year}-12-31 23:59:59"

        # Get active biz units for old org
        mysql_cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (old_org,))
        biz_ids = set(r['id'] for r in mysql_cur.fetchall())
        biz_str = ",".join(str(b) for b in biz_ids) if biz_ids else "0"

        # Get new PG records with migration_id
        pg_cur.execute("""
            SELECT tr.id, tr.migration_id
            FROM transaction_records tr
            JOIN transactions t ON tr.created_transaction_id = t.id
            WHERE t.organization_id = %s
              AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
              AND (tr.status != 'rejected' OR tr.status IS NULL)
              AND tr.transaction_date >= %s AND tr.transaction_date <= %s
              AND tr.migration_id IS NOT NULL
        """, (new_org, start, end))
        new_recs = {int(r['migration_id']): r['id'] for r in pg_cur.fetchall()}

        if not new_recs:
            continue

        # Get old MySQL records (same logic as old report)
        if biz_ids:
            mysql_cur.execute(f"""
                SELECT t.id FROM transactions t
                WHERE t.transaction_date BETWEEN %s AND %s
                  AND t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
                  AND t.deleted_date IS NULL
            """, (start, end))
            old_tx_ids = set(r['id'] for r in mysql_cur.fetchall())
        else:
            old_tx_ids = set()

        old_rec_ids = set()
        if old_tx_ids:
            for i in range(0, len(list(old_tx_ids)), 5000):
                batch = list(old_tx_ids)[i:i+5000]
                tx_str = ",".join(str(t) for t in batch)
                mysql_cur.execute(f"""
                    SELECT tr.id AS rec_id, tr.transaction_id, tr.journey_id, tr.status
                    FROM transaction_records tr
                    WHERE tr.transaction_id IN ({tx_str}) AND tr.deleted_date IS NULL
                """)
                hops = {}
                for r in mysql_cur.fetchall():
                    key = f"{r['transaction_id']}_{r['journey_id']}"
                    hops[key] = r
                for v in hops.values():
                    if v['status'] != 'rejected':
                        old_rec_ids.add(v['rec_id'])

        # Find new records not in old
        for mig_id, new_id in new_recs.items():
            if mig_id not in old_rec_ids:
                all_delete_ids.append(new_id)

        count = sum(1 for mid in new_recs if mid not in old_rec_ids)
        if count > 0:
            print(f"  old={old_org}/new={new_org} {year}: {count} to delete", flush=True)

    return all_delete_ids


def insert_missing_384(pg_cur, mysql_cur):
    """Insert 5 missing records for org 384/67."""
    old_rec_ids = [153456, 153457, 153458, 153461, 153464]

    # Get old data
    for rid in old_rec_ids:
        mysql_cur.execute("""
            SELECT tr.id, tr.transaction_id, tr.quantity, tr.status, tr.journey_id,
                   tr.material, tr.created_date AS tr_created,
                   t.transaction_date, t.`business-unit` AS biz, t.organization,
                   t.created_date AS tx_created, t.status AS tx_status,
                   m.unit_weight
            FROM transaction_records tr
            JOIN transactions t ON tr.transaction_id = t.id
            JOIN materials m ON tr.material = m.id
            WHERE tr.id = %s
        """, (rid,))
        old = mysql_cur.fetchone()

        # Check if transaction exists in new PG
        pg_cur.execute("SELECT id FROM transactions WHERE migration_id = %s", (str(old['transaction_id']),))
        existing_tx = pg_cur.fetchone()

        if not existing_tx:
            # Need to create transaction first
            # Find the business_unit mapping
            pg_cur.execute("SELECT id FROM business_units WHERE migration_id = %s", (str(old['biz']),))
            new_biz = pg_cur.fetchone()
            biz_id = new_biz['id'] if new_biz else None

            pg_cur.execute("SELECT id FROM organizations WHERE migration_id = %s", (str(old['organization']),))
            new_org = pg_cur.fetchone()
            org_id = new_org['id'] if new_org else None

            if not org_id:
                print(f"  SKIP rec={rid}: org {old['organization']} not found in new DB", flush=True)
                continue

            pg_cur.execute("""
                INSERT INTO transactions (
                    organization_id, transaction_date, status,
                    created_date, migration_id, transaction_type
                ) VALUES (%s, %s, %s, %s, %s, 1)
                RETURNING id
            """, (org_id, old['transaction_date'], old['tx_status'],
                  old['tx_created'], str(old['transaction_id'])))
            new_tx_id = pg_cur.fetchone()['id']
            print(f"  Created tx: old={old['transaction_id']} -> new={new_tx_id}", flush=True)
        else:
            new_tx_id = existing_tx['id']

        # Find material mapping
        pg_cur.execute("SELECT id FROM materials WHERE id = %s", (old['material'],))
        mat = pg_cur.fetchone()
        mat_id = mat['id'] if mat else old['material']

        # Insert record
        w = float(old['quantity']) * float(old['unit_weight'])
        pg_cur.execute("""
            INSERT INTO transaction_records (
                created_transaction_id, origin_quantity, status,
                material_id, transaction_date, journey_id,
                origin_weight_kg, migration_id, created_date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (new_tx_id, old['quantity'], old['status'],
              mat_id, old['transaction_date'], old['journey_id'],
              w, str(rid), old['tr_created']))
        new_rec_id = pg_cur.fetchone()['id']
        print(f"  Created rec: old={rid} -> new={new_rec_id}, w={w:.2f} kg", flush=True)


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
    pg_cur = pg_conn.cursor()

    # ===== STEP 1: Collect IDs to soft-delete =====
    print("STEP 1: Collecting records to soft-delete...", flush=True)
    delete_ids = collect_ids_to_delete(pg_cur, mysql_cur)
    print(f"\nTotal records to soft-delete: {len(delete_ids)}", flush=True)

    # ===== STEP 2: Soft-delete in batches =====
    if delete_ids:
        print("\nSTEP 2: Soft-deleting records...", flush=True)
        for i in range(0, len(delete_ids), 500):
            batch = delete_ids[i:i+500]
            placeholders = ",".join(["%s"] * len(batch))
            pg_cur.execute(f"""
                UPDATE transaction_records SET deleted_date = %s
                WHERE id IN ({placeholders}) AND deleted_date IS NULL
            """, [NOW] + batch)
            print(f"  Batch {i//500+1}: soft-deleted {pg_cur.rowcount} records", flush=True)
        pg_conn.commit()
        print(f"  Done. Total soft-deleted: {len(delete_ids)}", flush=True)

    # ===== STEP 3: Insert missing records for org 384/67 =====
    print("\nSTEP 3: Inserting missing records for org 384/67...", flush=True)
    insert_missing_384(pg_cur, mysql_cur)
    pg_conn.commit()

    # ===== STEP 4: Verify =====
    print("\nSTEP 4: Verifying totals...", flush=True)
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        start = f"{year}-01-01"
        end = f"{year}-12-31 23:59:59"

        # Old total
        mysql_cur.execute("""
            SELECT SUM(tr.quantity * m.unit_weight) AS total, COUNT(*) AS cnt
            FROM transaction_records tr
            JOIN materials m ON tr.material = m.id
            JOIN transactions t ON tr.transaction_id = t.id
            WHERE t.transaction_date BETWEEN %s AND %s
              AND t.transaction_type = 1
              AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
        """, (start, end))
        old = mysql_cur.fetchone()
        old_total = float(old['total'] or 0)

        # New total (only records with migration_id to exclude test data)
        pg_cur.execute("""
            SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total, COUNT(*) AS cnt
            FROM transaction_records tr
            JOIN transactions t ON tr.created_transaction_id = t.id
            LEFT JOIN materials m ON tr.material_id = m.id
            WHERE t.deleted_date IS NULL AND tr.deleted_date IS NULL
              AND (tr.status != 'rejected' OR tr.status IS NULL)
              AND tr.transaction_date >= %s AND tr.transaction_date <= %s
              AND t.migration_id IS NOT NULL
        """, (start, end))
        new = pg_cur.fetchone()
        new_total = float(new['total'] or 0)

        diff = new_total - old_total
        status = "OK" if abs(diff) < 1.0 else f"DIFF {diff:+.2f}"
        print(f"  {year}: old={old_total:.2f} ({old['cnt']}), new={new_total:.2f} ({new['cnt']}), {status}", flush=True)

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()
    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
