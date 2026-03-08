#!/usr/bin/env python3
"""
Check transactions that need to be updated after migration
"""

import psycopg2
import psycopg2.extras
import json

LOCAL_PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "geppsa-ard",
    "password": "",
}

BUILDING_ID = 9828
ORG_ID = 133

pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

try:
    # Check transactions with origin = building 9828
    print("=" * 80)
    print("Transactions with ORIGIN = building 9828 (อาคารปทุมวัน):")
    print("=" * 80)
    pg_cur.execute("""
        SELECT
            t.id,
            t.origin_id,
            t.destination_ids,
            t.location_tag_id,
            t.migration_id,
            t.transaction_date,
            ul_origin.name_th as origin_name
        FROM transactions t
        LEFT JOIN user_locations ul_origin ON t.origin_id = ul_origin.id
        WHERE t.organization_id = %s
          AND t.origin_id = %s
          AND t.deleted_date IS NULL
        ORDER BY t.transaction_date DESC
        LIMIT 20
    """, (ORG_ID, BUILDING_ID))

    origin_txs = pg_cur.fetchall()
    print(f"\nFound {len(origin_txs)} transactions with origin={BUILDING_ID}\n")

    if origin_txs:
        print(f"{'TX ID':<10} {'Date':<12} {'Origin':<30} {'Dest IDs':<15} {'Tag ID':<8}")
        print("-" * 90)
        for tx in origin_txs:
            dest_ids = tx['destination_ids'] if tx['destination_ids'] else []
            print(f"{tx['id']:<10} {str(tx['transaction_date']):<12} {tx['origin_name'] or 'N/A':<30} {str(dest_ids):<15} {tx['location_tag_id'] or 'N/A':<8}")

    # Check transactions with destination = building 9828
    print("\n" + "=" * 80)
    print("Transactions with DESTINATION including building 9828 (อาคารปทุมวัน):")
    print("=" * 80)
    pg_cur.execute("""
        SELECT
            t.id,
            t.origin_id,
            t.destination_ids,
            t.location_tag_id,
            t.migration_id,
            t.transaction_date,
            ul_origin.name_th as origin_name
        FROM transactions t
        LEFT JOIN user_locations ul_origin ON t.origin_id = ul_origin.id
        WHERE t.organization_id = %s
          AND %s = ANY(t.destination_ids)
          AND t.deleted_date IS NULL
        ORDER BY t.transaction_date DESC
        LIMIT 20
    """, (ORG_ID, BUILDING_ID))

    dest_txs = pg_cur.fetchall()
    print(f"\nFound {len(dest_txs)} transactions with destination including {BUILDING_ID}\n")

    if dest_txs:
        print(f"{'TX ID':<10} {'Date':<12} {'Origin':<30} {'Dest IDs':<15} {'Tag ID':<8}")
        print("-" * 90)
        for tx in dest_txs:
            dest_ids = tx['destination_ids'] if tx['destination_ids'] else []
            print(f"{tx['id']:<10} {str(tx['transaction_date']):<12} {tx['origin_name'] or 'N/A':<30} {str(dest_ids):<15} {tx['location_tag_id'] or 'N/A':<8}")

    # Check transactions with location_tag_id set (these will be updated)
    print("\n" + "=" * 80)
    print("Transactions that will be UPDATED (have location_tag_id AND origin = 9828):")
    print("=" * 80)
    pg_cur.execute("""
        SELECT
            t.id,
            t.origin_id,
            t.destination_ids,
            t.location_tag_id,
            t.transaction_date,
            ul_origin.name_th as origin_name
        FROM transactions t
        LEFT JOIN user_locations ul_origin ON t.origin_id = ul_origin.id
        WHERE t.organization_id = %s
          AND t.origin_id = %s
          AND t.location_tag_id IS NOT NULL
          AND t.deleted_date IS NULL
        ORDER BY t.transaction_date DESC
    """, (ORG_ID, BUILDING_ID))

    update_txs = pg_cur.fetchall()
    print(f"\nFound {len(update_txs)} transactions that will be updated\n")

    if update_txs:
        print(f"{'TX ID':<10} {'Date':<12} {'Origin':<30} {'Dest IDs':<15} {'Tag ID':<8}")
        print("-" * 90)
        for tx in update_txs:
            dest_ids = tx['destination_ids'] if tx['destination_ids'] else []
            print(f"{tx['id']:<10} {str(tx['transaction_date']):<12} {tx['origin_name'] or 'N/A':<30} {str(dest_ids):<15} {tx['location_tag_id']:<8}")

    print("\n" + "=" * 80)
    print("Summary:")
    print("=" * 80)
    print(f"  Transactions with origin=9828: {len(origin_txs)}")
    print(f"  Transactions with destination=9828: {len(dest_txs)}")
    print(f"  Transactions to be updated: {len(update_txs)}")
    print("=" * 80)

finally:
    pg_cur.close()
    pg_conn.close()
