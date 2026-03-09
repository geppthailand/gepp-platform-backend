#!/usr/bin/env python3
"""
Update transaction origins from building 9828 to floors based on location_tag_id
"""

import psycopg2
import psycopg2.extras
from datetime import datetime

LOCAL_PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "geppsa-ard",
    "password": "",
}

ORG_ID = 133
BUILDING_ID = 9828

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

try:
    # Get tag → location mapping
    log("Getting location_tag to user_location mapping...")
    pg_cur.execute("""
        SELECT id, migration_id, name_th
        FROM user_locations
        WHERE organization_id = %s
          AND migration_id IN (396, 397, 398, 399, 400, 401, 402)
        ORDER BY migration_id
    """, (ORG_ID,))

    tag_to_location = {}
    for row in pg_cur.fetchall():
        tag_id = int(row['migration_id'])
        loc_id = row['id']
        tag_to_location[tag_id] = loc_id
        log(f"  Tag {tag_id} ({row['name_th']}) → location {loc_id}")

    # Find transactions to update
    log(f"\nFinding transactions with origin={BUILDING_ID} and location_tag_id set...")
    pg_cur.execute("""
        SELECT
            t.id,
            t.origin_id,
            t.location_tag_id,
            ul.name_th as origin_name
        FROM transactions t
        LEFT JOIN user_locations ul ON t.origin_id = ul.id
        WHERE t.organization_id = %s
          AND t.origin_id = %s
          AND t.location_tag_id IS NOT NULL
          AND t.deleted_date IS NULL
    """, (ORG_ID, BUILDING_ID))

    transactions = pg_cur.fetchall()
    log(f"  Found {len(transactions)} transactions to update\n")

    updated = 0
    skipped_no_mapping = 0
    skipped_already_correct = 0

    for tx in transactions:
        tx_id = tx['id']
        old_origin = tx['origin_id']
        location_tag_id = tx['location_tag_id']

        # location_tag_id IS the new floor user_location id
        # So origin_id should be the same as location_tag_id
        new_origin = location_tag_id

        if old_origin == new_origin:
            skipped_already_correct += 1
            continue

        # Update transaction
        pg_cur.execute("""
            UPDATE transactions
            SET origin_id = %s,
                updated_date = NOW()
            WHERE id = %s
        """, (new_origin, tx_id))

        log(f"  [UPDATE] tx {tx_id}: origin {old_origin} → {new_origin} (location_tag {location_tag_id})")
        updated += 1

    pg_conn.commit()

    log(f"\n{'=' * 80}")
    log("Update Complete!")
    log(f"  Updated: {updated}")
    log(f"  Skipped (no mapping): {skipped_no_mapping}")
    log(f"  Skipped (already correct): {skipped_already_correct}")
    log(f"{'=' * 80}")

except Exception as e:
    pg_conn.rollback()
    log(f"\nERROR: {e}")
    raise
finally:
    pg_cur.close()
    pg_conn.close()
