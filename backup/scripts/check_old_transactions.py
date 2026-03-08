#!/usr/bin/env python3
"""
Check old MySQL transactions that have location_tag_id
for business_unit "อาคารปทุมวัน" (id 13952)
"""

import pymysql

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()

try:
    # Check transactions with location_tag_id in F1-F7 (396-402)
    print("=" * 80)
    print("Old MySQL: Transactions with location_tag_id for F1-F7 (tags 396-402):")
    print("=" * 80)

    mysql_cur.execute("""
        SELECT
            t.id,
            t.organization,
            t.location_tag_id,
            t.created_date,
            lt.name_th as tag_name,
            lt.business_unit
        FROM transactions t
        LEFT JOIN location_tags lt ON t.location_tag_id = lt.id
        WHERE t.organization = 451
          AND t.location_tag_id IN (396, 397, 398, 399, 400, 401, 402)
          AND t.is_active = 1
          AND t.deleted_date IS NULL
        ORDER BY t.created_date DESC
        LIMIT 30
    """)

    old_txs = mysql_cur.fetchall()
    print(f"\nFound {len(old_txs)} old transactions with location_tag_id for F1-F7\n")

    if old_txs:
        print(f"{'TX ID':<10} {'Date':<20} {'Tag Name':<15} {'Business Unit':<15}")
        print("-" * 65)
        for tx in old_txs:
            print(f"{tx['id']:<10} {str(tx['created_date']):<20} {tx['tag_name'] or 'N/A':<15} {tx['business_unit'] or 'N/A':<15}")

    # Check if these transactions were migrated to new database
    print("\n" + "=" * 80)
    print("Checking if these transactions were migrated to new PostgreSQL...")
    print("=" * 80)

    if old_txs:
        old_tx_ids = [tx['id'] for tx in old_txs]
        print(f"Old transaction IDs: {old_tx_ids[:10]}... (showing first 10)")

        # Connect to PostgreSQL
        import psycopg2
        import psycopg2.extras

        LOCAL_PG_CONFIG = {
            "host": "localhost",
            "port": 5432,
            "dbname": "postgres",
            "user": "geppsa-ard",
            "password": "",
        }

        pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
        pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check which old transaction IDs were migrated
        placeholders = ','.join(['%s'] * len(old_tx_ids))
        pg_cur.execute(f"""
            SELECT
                id,
                migration_id,
                origin_id,
                location_tag_id,
                transaction_date
            FROM transactions
            WHERE organization_id = 133
              AND migration_id IN ({placeholders})
              AND deleted_date IS NULL
        """, old_tx_ids)

        migrated_txs = pg_cur.fetchall()
        print(f"\nFound {len(migrated_txs)} migrated transactions in new database")

        if migrated_txs:
            print(f"\n{'New TX ID':<12} {'Old TX ID (mig)':<18} {'Origin ID':<12} {'Location Tag ID':<18}")
            print("-" * 65)
            for tx in migrated_txs[:20]:
                print(f"{tx['id']:<12} {tx['migration_id']:<18} {tx['origin_id']:<12} {str(tx['location_tag_id']) if tx['location_tag_id'] else 'NULL':<18}")

        pg_cur.close()
        pg_conn.close()

finally:
    mysql_cur.close()
    mysql_conn.close()
