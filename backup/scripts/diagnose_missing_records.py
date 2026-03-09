#!/usr/bin/env python3
"""
Diagnose why transaction_records are missing after migration.
Checks which records were skipped and why.

Usage:
  python3 diagnose_missing_records.py
"""

import json
import mysql.connector
import psycopg2
import psycopg2.extras

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
}

LOCAL_PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "geppsa-ard",
    "password": "",
}


def main():
    # Connect
    mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor(dictionary=True)

    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ====================================================================
    # 1. Check how many transaction_records exist in MySQL (total)
    # ====================================================================
    mysql_cur.execute("SELECT COUNT(*) as cnt FROM transaction_records")
    total_records = mysql_cur.fetchone()["cnt"]

    mysql_cur.execute("SELECT COUNT(*) as cnt FROM transaction_records WHERE is_active = 1 AND deleted_date IS NULL")
    active_records = mysql_cur.fetchone()["cnt"]
    print(f"MySQL transaction_records: {total_records} total, {active_records} active (is_active=1 AND deleted_date IS NULL)")

    # ====================================================================
    # 2. Check transactions
    # ====================================================================
    mysql_cur.execute("SELECT COUNT(*) as cnt FROM transactions")
    total_tx = mysql_cur.fetchone()["cnt"]

    mysql_cur.execute("SELECT COUNT(*) as cnt FROM transactions WHERE is_active = 1 AND deleted_date IS NULL")
    active_tx = mysql_cur.fetchone()["cnt"]

    mysql_cur.execute("SELECT COUNT(*) as cnt FROM transactions WHERE is_active = 0 OR deleted_date IS NOT NULL")
    inactive_tx = mysql_cur.fetchone()["cnt"]
    print(f"\nMySQL transactions: {total_tx} total, {active_tx} active, {inactive_tx} inactive/deleted")

    # ====================================================================
    # 3. How many active records reference inactive/deleted transactions?
    # ====================================================================
    mysql_cur.execute("""
        SELECT COUNT(*) as cnt
        FROM transaction_records tr
        WHERE tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.transaction_id NOT IN (
              SELECT id FROM transactions WHERE is_active = 1 AND deleted_date IS NULL
          )
    """)
    orphan_records = mysql_cur.fetchone()["cnt"]
    print(f"\nActive records pointing to inactive/deleted transactions: {orphan_records}")

    # ====================================================================
    # 4. Check organizations
    # ====================================================================
    mysql_cur.execute("""
        SELECT COUNT(DISTINCT t.organization) as cnt
        FROM transactions t
        WHERE t.is_active = 1 AND t.deleted_date IS NULL
    """)
    tx_org_count = mysql_cur.fetchone()["cnt"]

    mysql_cur.execute("SELECT COUNT(*) as cnt FROM organization WHERE is_active = 1 AND deleted_date IS NULL")
    active_orgs = mysql_cur.fetchone()["cnt"]
    print(f"\nMySQL active orgs: {active_orgs}, orgs referenced by active transactions: {tx_org_count}")

    # How many active transactions have org NOT in active orgs?
    mysql_cur.execute("""
        SELECT COUNT(*) as cnt
        FROM transactions t
        WHERE t.is_active = 1 AND t.deleted_date IS NULL
          AND t.organization NOT IN (
              SELECT id FROM organization WHERE is_active = 1 AND deleted_date IS NULL
          )
    """)
    orphan_tx_org = mysql_cur.fetchone()["cnt"]
    print(f"Active transactions with inactive/deleted org: {orphan_tx_org}")

    # ====================================================================
    # 5. Check material matching
    # ====================================================================
    # Get old materials
    mysql_cur.execute("""
        SELECT id, name_en, name_th FROM materials
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    old_materials = mysql_cur.fetchall()

    # Get new materials
    pg_cur.execute("""
        SELECT id, name_en, name_th FROM materials
        WHERE is_active = TRUE AND deleted_date IS NULL
    """)
    new_materials = pg_cur.fetchall()

    new_by_name = {}
    for m in new_materials:
        name = (m["name_en"] or "").strip().lower()
        if name:
            new_by_name[name] = m

    matched_mat_ids = set()
    unmatched_mats = []
    for om in old_materials:
        old_name = (om["name_en"] or "").strip().lower()
        if old_name in new_by_name:
            matched_mat_ids.add(om["id"])
        else:
            unmatched_mats.append(om)

    print(f"\nMaterial matching: {len(matched_mat_ids)} matched, {len(unmatched_mats)} unmatched")
    if unmatched_mats:
        print("  Unmatched materials:")
        for m in unmatched_mats:
            print(f"    ID {m['id']}: {m['name_en']} / {m['name_th']}")

    # How many active records use unmatched materials?
    if unmatched_mats:
        unmatched_ids = [m["id"] for m in unmatched_mats]
        placeholders = ",".join(["%s"] * len(unmatched_ids))
        mysql_cur.execute(f"""
            SELECT COUNT(*) as cnt
            FROM transaction_records tr
            WHERE tr.is_active = 1 AND tr.deleted_date IS NULL
              AND tr.material IN ({placeholders})
        """, unmatched_ids)
        records_with_unmatched_mat = mysql_cur.fetchone()["cnt"]
        print(f"  Active records using unmatched materials: {records_with_unmatched_mat}")

    # ====================================================================
    # 6. Check deduplication impact
    # ====================================================================
    mysql_cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT CONCAT(transaction_id, '_', journey_id)) as distinct_keys
        FROM transaction_records
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    dedup = mysql_cur.fetchone()
    print(f"\nDeduplication: {dedup['total']} total → {dedup['distinct_keys']} unique (transaction_id, journey_id)")
    print(f"  Records lost to dedup: {dedup['total'] - dedup['distinct_keys']}")

    # ====================================================================
    # 7. Summary of what actually gets migrated
    # ====================================================================
    # Records that pass ALL filters:
    # - record is active
    # - parent transaction is active
    # - transaction's org is active
    # - material is matched
    matched_mat_list = list(matched_mat_ids)
    if matched_mat_list:
        mat_placeholders = ",".join(["%s"] * len(matched_mat_list))
        mysql_cur.execute(f"""
            SELECT COUNT(DISTINCT CONCAT(tr.transaction_id, '_', tr.journey_id)) as cnt
            FROM transaction_records tr
            JOIN transactions t ON tr.transaction_id = t.id
            JOIN organization o ON t.organization = o.id
            WHERE tr.is_active = 1 AND tr.deleted_date IS NULL
              AND t.is_active = 1 AND t.deleted_date IS NULL
              AND o.is_active = 1 AND o.deleted_date IS NULL
              AND tr.material IN ({mat_placeholders})
        """, matched_mat_list)
        would_migrate = mysql_cur.fetchone()["cnt"]
    else:
        would_migrate = 0

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total active records in MySQL: {active_records}")
    print(f"Would actually migrate:        {would_migrate}")
    print(f"Lost records:                  {active_records - would_migrate}")
    print(f"  - Due to inactive/deleted transactions:  {orphan_records}")
    print(f"  - Due to unmatched materials:            {records_with_unmatched_mat if unmatched_mats else 0}")
    print(f"  - Due to deduplication:                  {dedup['total'] - dedup['distinct_keys']}")

    # ====================================================================
    # 8. Check in new PG DB how many were actually migrated
    # ====================================================================
    pg_cur.execute("SELECT COUNT(*) as cnt FROM transaction_records WHERE migration_id IS NOT NULL")
    pg_migrated = pg_cur.fetchone()["cnt"]
    print(f"\nActual migrated records in PG: {pg_migrated}")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
