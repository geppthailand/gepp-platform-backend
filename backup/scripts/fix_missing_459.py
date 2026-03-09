"""
Fix org 459/141: Insert 53 missing records (27 transactions) from old biz_unit 14036.
These were skipped during migration. All from biz_unit 14036, origin_id=9898 in new DB.

Follows the same migration pattern from migrate_legacy_insert.py:
- Transaction: status, transaction_method='origin', organization_id, origin_id, etc.
- Record: origin_quantity=abs(qty), origin_weight_kg=qty, migration_id=old_rec_id
"""

import pymysql
import psycopg2
import psycopg2.extras
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
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
NEW_ORIGIN_ID = 9898  # biz_unit 14036 maps to origin_id 9898
DRY_RUN = "--apply" not in sys.argv

# The 27 old transaction IDs with missing records
MISSING_OLD_TX_IDS = [
    25881, 26048, 26164, 26354, 26413, 26629, 26805, 26875, 27088,
    27727, 27729, 27887, 28635, 28636, 28637, 29149, 29150,
    30832, 30834, 30835, 30837, 30839, 30841, 30843, 30845, 30847, 30957,
]


def safe_decimal(val):
    if val is None:
        return Decimal("0")
    try:
        return abs(Decimal(str(val)))
    except Exception:
        return Decimal("0")


def main():
    if DRY_RUN:
        print("*** DRY RUN — pass --apply to actually fix ***\n")

    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # 1. Get a sample created_by_id from existing migrated records for this org
    pg_cur.execute("""
        SELECT DISTINCT tr.created_by_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        WHERE t.organization_id = %s AND tr.migration_id IS NOT NULL
          AND tr.created_by_id IS NOT NULL
        LIMIT 1
    """, (NEW_ORG,))
    sample = pg_cur.fetchone()
    created_by_id = sample["created_by_id"] if sample else None
    print(f"Using created_by_id: {created_by_id}")

    # 2. Get old transactions and their records
    placeholders = ",".join(["%s"] * len(MISSING_OLD_TX_IDS))
    mysql_cur.execute(f"""
        SELECT t.id AS tx_id, t.transaction_date, t.status AS tx_status,
               t.total_quantity, t.note AS tx_note,
               t.created_date AS tx_created, t.updated_date AS tx_updated
        FROM transactions t
        WHERE t.id IN ({placeholders})
        ORDER BY t.id
    """, MISSING_OLD_TX_IDS)
    old_txs = mysql_cur.fetchall()
    print(f"Found {len(old_txs)} old transactions")

    mysql_cur.execute(f"""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.price,
               tr.status AS rec_status, tr.material, tr.note AS rec_note,
               tr.created_date AS rec_created, tr.updated_date AS rec_updated,
               m.material_category_id, m.material_main_id, m.unit_name_en
        FROM transaction_records tr
        JOIN materials m ON tr.material = m.id
        WHERE tr.transaction_id IN ({placeholders})
          AND tr.is_active = 1
          AND tr.deleted_date IS NULL
        ORDER BY tr.transaction_id, tr.id
    """, MISSING_OLD_TX_IDS)
    old_recs = mysql_cur.fetchall()
    print(f"Found {len(old_recs)} old records")

    # Group records by transaction
    recs_by_tx = defaultdict(list)
    for r in old_recs:
        recs_by_tx[r["transaction_id"]].append(r)

    # 3. Check that none of these records are already migrated
    all_rec_ids = [r["rec_id"] for r in old_recs]
    rec_placeholders = ",".join(["%s"] * len(all_rec_ids))
    pg_cur.execute(f"""
        SELECT migration_id FROM transaction_records
        WHERE migration_id IN ({rec_placeholders})
    """, all_rec_ids)
    already_migrated = {r["migration_id"] for r in pg_cur.fetchall()}
    if already_migrated:
        print(f"WARNING: {len(already_migrated)} records already migrated: {already_migrated}")
        # Remove already migrated
        for tx_id in list(recs_by_tx.keys()):
            recs_by_tx[tx_id] = [r for r in recs_by_tx[tx_id] if r["rec_id"] not in already_migrated]
            if not recs_by_tx[tx_id]:
                del recs_by_tx[tx_id]
    else:
        print("No records already migrated — safe to proceed")

    # 4. Check that material IDs exist in new DB
    mat_ids = list({r["material"] for r in old_recs})
    mat_placeholders = ",".join(["%s"] * len(mat_ids))
    pg_cur.execute(f"SELECT id FROM materials WHERE id IN ({mat_placeholders})", mat_ids)
    existing_mats = {r["id"] for r in pg_cur.fetchall()}
    missing_mats = set(mat_ids) - existing_mats
    if missing_mats:
        print(f"WARNING: Material IDs not in new DB: {missing_mats}")
    else:
        print(f"All {len(mat_ids)} material IDs exist in new DB")

    # 5. Show before total
    pg_cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2020-01-01'
          AND tr.transaction_date <= '2025-12-31 23:59:59'
    """, (NEW_ORG,))
    before_total = float(pg_cur.fetchone()["total_weight"] or 0)
    print(f"\nBefore total (2020-2025): {before_total:.2f} kg")

    status_map = {"pending": "pending", "approved": "approved", "rejected": "rejected", "completed": "completed"}

    # 6. Insert transactions and records
    total_recs_inserted = 0
    total_txs_inserted = 0
    total_weight_added = 0.0

    for tx in old_txs:
        tx_id = tx["tx_id"]
        recs = recs_by_tx.get(tx_id, [])
        if not recs:
            continue

        tx_status = status_map.get(tx["tx_status"], "pending")

        print(f"\n  Old tx_id={tx_id}, date={tx['transaction_date']}, status={tx_status}, {len(recs)} records")

        if not DRY_RUN:
            pg_cur.execute("""
                INSERT INTO transactions (
                    status, transaction_method,
                    organization_id, origin_id,
                    weight_kg, total_amount,
                    transaction_date, notes,
                    created_by_id,
                    created_date, updated_date, is_active,
                    transaction_records, destination_ids,
                    migration_id
                ) VALUES (
                    %s, 'origin',
                    %s, %s,
                    %s, 0,
                    %s, %s,
                    %s,
                    %s, %s, TRUE,
                    '{}'::bigint[], '{}'::bigint[],
                    %s
                )
                RETURNING id
            """, (
                tx_status,
                NEW_ORG, NEW_ORIGIN_ID,
                safe_decimal(tx.get("total_quantity")),
                tx["transaction_date"],
                tx.get("tx_note"),
                created_by_id,
                tx.get("tx_created"), tx.get("tx_updated"),
                tx_id,
            ))
            new_tx_id = pg_cur.fetchone()["id"]
            total_txs_inserted += 1
        else:
            new_tx_id = "DRY"

        new_rec_ids = []
        for rec in recs:
            qty = safe_decimal(rec["quantity"])
            price = safe_decimal(rec["price"])
            total_amount = qty * price
            rec_status = status_map.get(rec["rec_status"], "pending")

            weight = float(qty) * 1.0  # unit_weight is 1.0 for all these records
            total_weight_added += weight

            print(f"    rec_id={rec['rec_id']}, mat={rec['material']}, qty={qty}, "
                  f"weight={weight:.2f}, status={rec_status}")

            if not DRY_RUN:
                pg_cur.execute("""
                    INSERT INTO transaction_records (
                        is_active, status,
                        created_transaction_id, traceability,
                        transaction_type,
                        material_id, main_material_id, category_id,
                        tags, unit,
                        origin_quantity, origin_weight_kg,
                        origin_price_per_unit, total_amount,
                        currency_id,
                        notes, images,
                        hazardous_level,
                        created_by_id,
                        transaction_date,
                        created_date, updated_date,
                        migration_id
                    ) VALUES (
                        TRUE, %s,
                        %s, '{}'::bigint[],
                        'manual_input',
                        %s, %s, %s,
                        '[]'::jsonb, %s,
                        %s, %s,
                        %s, %s,
                        12,
                        %s, '[]',
                        0,
                        %s,
                        %s,
                        %s, %s,
                        %s
                    )
                    RETURNING id
                """, (
                    rec_status,
                    new_tx_id,
                    rec["material"], rec["material_main_id"], rec["material_category_id"],
                    rec.get("unit_name_en"),
                    qty, qty,  # origin_weight_kg = quantity (same as migration)
                    price, total_amount,
                    rec.get("rec_note"),
                    created_by_id,
                    tx["transaction_date"],  # use parent tx date (same as migration)
                    rec.get("rec_created"), rec.get("rec_updated"),
                    rec["rec_id"],
                ))
                new_rec_id = pg_cur.fetchone()["id"]
                new_rec_ids.append(new_rec_id)
                total_recs_inserted += 1

        # Update transaction with record IDs array
        if not DRY_RUN and new_rec_ids:
            pg_cur.execute("""
                UPDATE transactions SET transaction_records = %s WHERE id = %s
            """, (new_rec_ids, new_tx_id))

    if not DRY_RUN:
        pg_conn.commit()
        print(f"\n{'='*60}")
        print(f"COMMITTED: {total_txs_inserted} transactions, {total_recs_inserted} records")
        print(f"Weight added: {total_weight_added:.2f} kg")

        # Verify
        pg_cur.execute("""
            SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight
            FROM transaction_records tr
            JOIN transactions t ON tr.created_transaction_id = t.id
            LEFT JOIN materials m ON tr.material_id = m.id
            WHERE t.organization_id = %s
              AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
              AND (tr.status != 'rejected' OR tr.status IS NULL)
              AND tr.transaction_date >= '2020-01-01'
              AND tr.transaction_date <= '2025-12-31 23:59:59'
        """, (NEW_ORG,))
        after_total = float(pg_cur.fetchone()["total_weight"] or 0)
        expected = before_total + total_weight_added

        print(f"\nBefore: {before_total:.2f} kg")
        print(f"After:  {after_total:.2f} kg")
        print(f"Added:  {after_total - before_total:.2f} kg")
        print(f"Expected add: {total_weight_added:.2f} kg")
        print(f"Old total (all biz-units, 2020-2025): 353,989.56 kg")
        print(f"Match: {'YES' if abs(after_total - 353989.56) < 1 else 'NO'} (diff={after_total - 353989.56:+.2f})")
    else:
        print(f"\n{'='*60}")
        print(f"DRY RUN: would insert {len([tx for tx in old_txs if recs_by_tx.get(tx['tx_id'])])} transactions, "
              f"{sum(len(recs_by_tx.get(tx['tx_id'], [])) for tx in old_txs)} records")
        print(f"Weight to add: {total_weight_added:.2f} kg")
        print(f"Expected new total: {before_total + total_weight_added:.2f} kg")
        print(f"Old total: 353,989.56 kg")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
