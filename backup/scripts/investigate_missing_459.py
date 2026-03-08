"""
Investigate the 53 missing records from old org=459, biz_unit=14036.
Check if their parent transactions were partially migrated or entirely skipped.
"""

import pymysql
import psycopg2
import psycopg2.extras

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
DATE_FROM = "2020-01-01"
DATE_TO = "2025-12-31 23:59:59"


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # 1. Get ALL old records for org 459, biz_unit 14036, in date range
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.price,
               tr.status AS rec_status, tr.material, tr.`journey_id`,
               tr.is_active, tr.deleted_date AS rec_deleted,
               m.unit_weight, m.calc_ghg, m.name_en AS mat_name, m.material_category_id,
               m.material_main_id,
               t.status AS tx_status, t.`business-unit` AS biz_unit,
               t.transaction_date, t.transaction_type
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.`business-unit` = 14036
          AND t.transaction_type = 1
          AND tr.is_active = 1
          AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s
          AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    all_14036 = mysql_cur.fetchall()
    print(f"All old records from biz_unit 14036: {len(all_14036)}")

    # 2. Get migrated IDs
    pg_cur.execute("""
        SELECT tr.migration_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        WHERE t.organization_id = %s AND tr.migration_id IS NOT NULL
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
    """, (NEW_ORG,))
    migrated_ids = {r["migration_id"] for r in pg_cur.fetchall()}

    # 3. Identify missing records
    missing = [r for r in all_14036 if r["rec_id"] not in migrated_ids]
    migrated = [r for r in all_14036 if r["rec_id"] in migrated_ids]
    print(f"Migrated: {len(migrated)}, Missing: {len(missing)}")

    # 4. Group missing by transaction_id
    missing_by_tx = {}
    for r in missing:
        tx_id = r["transaction_id"]
        if tx_id not in missing_by_tx:
            missing_by_tx[tx_id] = []
        missing_by_tx[tx_id].append(r)

    # 5. Check if any siblings from same transaction were migrated
    print(f"\nMissing records grouped by old transaction_id:")
    print(f"{'old_tx_id':>10} | {'missing':>7} | {'migrated_siblings':>17} | details")
    print("-" * 100)

    fully_missing_txs = []
    partially_missing_txs = []

    for tx_id, recs in sorted(missing_by_tx.items()):
        # Check if any other records from this transaction were migrated
        mysql_cur.execute("""
            SELECT tr.id AS rec_id
            FROM transaction_records tr
            WHERE tr.transaction_id = %s AND tr.is_active = 1 AND tr.deleted_date IS NULL
        """, (tx_id,))
        all_tx_recs = [r["rec_id"] for r in mysql_cur.fetchall()]
        migrated_siblings = [rid for rid in all_tx_recs if rid in migrated_ids]
        missing_count = len(recs)

        details = ", ".join(
            f"rec={r['rec_id']}({r['mat_name'][:20]},{abs(float(r['quantity'] or 0)) * float(r['unit_weight'] or 0):.1f}kg)"
            for r in recs
        )
        print(f"{tx_id:>10} | {missing_count:>7} | {len(migrated_siblings):>17} | {details[:120]}")

        if len(migrated_siblings) == 0:
            fully_missing_txs.append(tx_id)
        else:
            partially_missing_txs.append(tx_id)

    print(f"\nFully missing transactions (no records migrated): {len(fully_missing_txs)}")
    print(f"Partially missing (some siblings migrated): {len(partially_missing_txs)}")

    # 6. For partially missing, check what the new transaction looks like
    if partially_missing_txs:
        print(f"\n{'='*60}")
        print("PARTIALLY MIGRATED TRANSACTIONS — detail:")
        print(f"{'='*60}")
        for tx_id in partially_missing_txs:
            # Get migrated sibling's new transaction
            mysql_cur.execute("""
                SELECT tr.id FROM transaction_records tr
                WHERE tr.transaction_id = %s AND tr.is_active = 1 AND tr.deleted_date IS NULL
            """, (tx_id,))
            all_sibling_ids = [r["id"] for r in mysql_cur.fetchall()]
            migrated_sibling_ids = [rid for rid in all_sibling_ids if rid in migrated_ids]

            if migrated_sibling_ids:
                placeholders = ",".join(["%s"] * len(migrated_sibling_ids))
                pg_cur.execute(f"""
                    SELECT tr.id, tr.migration_id, tr.created_transaction_id, tr.origin_quantity,
                           m.name_en AS mat_name
                    FROM transaction_records tr
                    LEFT JOIN materials m ON tr.material_id = m.id
                    WHERE tr.migration_id IN ({placeholders})
                """, migrated_sibling_ids)
                new_siblings = pg_cur.fetchall()
                new_tx_ids = {r["created_transaction_id"] for r in new_siblings}
                print(f"\n  Old tx_id={tx_id} -> New tx_ids={list(new_tx_ids)}")
                for ns in new_siblings:
                    print(f"    new_rec={ns['id']}, migration_id={ns['migration_id']}, "
                          f"qty={ns['origin_quantity']}, mat={ns['mat_name']}")

                # Show missing records for this tx
                for r in missing_by_tx[tx_id]:
                    qty = abs(float(r["quantity"] or 0))
                    uw = float(r["unit_weight"] or 0)
                    print(f"    MISSING: old_rec={r['rec_id']}, qty={qty}, uw={uw}, "
                          f"weight={qty*uw:.2f}, mat={r['mat_name']}")

    # 7. For fully missing, show what needs to be created
    if fully_missing_txs:
        print(f"\n{'='*60}")
        print("FULLY MISSING TRANSACTIONS — need new transaction + records:")
        print(f"{'='*60}")
        for tx_id in fully_missing_txs:
            mysql_cur.execute("""
                SELECT t.id, t.transaction_date, t.status, t.`business-unit`
                FROM transactions t WHERE t.id = %s
            """, (tx_id,))
            tx = mysql_cur.fetchone()
            print(f"\n  Old tx_id={tx_id}, date={tx['transaction_date']}, status={tx['status']}, "
                  f"biz_unit={tx['business-unit']}")
            for r in missing_by_tx[tx_id]:
                qty = abs(float(r["quantity"] or 0))
                uw = float(r["unit_weight"] or 0)
                print(f"    rec_id={r['rec_id']}, qty={qty}, uw={uw}, weight={qty*uw:.2f}, "
                      f"mat_id={r['material']}, mat={r['mat_name']}, cat_id={r['material_category_id']}, "
                      f"main_mat={r['material_main_id']}, status={r['rec_status']}")

    # 8. Check origin mapping: what origin_id does biz_unit 14036 map to in new DB?
    print(f"\n{'='*60}")
    print("ORIGIN MAPPING CHECK")
    print(f"{'='*60}")
    # Check existing migrated records from biz_unit 14036 to find origin_id
    sample_migrated = [r for r in migrated if r["biz_unit"] == 14036][:5]
    if sample_migrated:
        sample_ids = [r["rec_id"] for r in sample_migrated]
        placeholders = ",".join(["%s"] * len(sample_ids))
        pg_cur.execute(f"""
            SELECT tr.migration_id, tr.created_transaction_id, t.origin_id,
                   t.location_tag_id, t.tenant_id
            FROM transaction_records tr
            JOIN transactions t ON tr.created_transaction_id = t.id
            WHERE tr.migration_id IN ({placeholders})
        """, sample_ids)
        for r in pg_cur.fetchall():
            print(f"  migration_id={r['migration_id']} -> tx origin_id={r['origin_id']}, "
                  f"tag={r['location_tag_id']}, tenant={r['tenant_id']}")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
