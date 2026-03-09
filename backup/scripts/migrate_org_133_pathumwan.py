#!/usr/bin/env python3
"""
Migrate organization structure for org 133 (from org 451 legacy)
and update transactions that have destination from "อาคารปทุมวัน" building

This script:
1. Runs migrate_org_structure.py for org 113.csv (org 133)
2. Updates transactions where origin = "อาคารปทุมวัน" (user_location 9828)
   to point to the migrated floors (F1-F7) based on location_tag_id
3. Prevents duplicate user_locations by checking name_en in old org 451 vs new org 133

Usage:
    python migrate_org_133_pathumwan.py
    python migrate_org_133_pathumwan.py --dry-run
"""

import sys
import psycopg2
import psycopg2.extras
import pymysql
from datetime import datetime

# ============================================================================
# CONFIG
# ============================================================================

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

LOCAL_PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "geppsa-ard",
    "password": "",
}

ORG_ID_NEW = 133  # New PostgreSQL org_id
ORG_ID_OLD = 451  # Old MySQL org_id
BUILDING_NAME = "อาคารปทุมวัน"
BUILDING_USER_LOCATION_ID = 9828  # In new database
BUILDING_MIGRATION_ID = 13952  # Old business_unit id

# Location tag IDs from old database (F1-F7)
LOCATION_TAG_IDS = [396, 397, 398, 399, 400, 401, 402]

# ============================================================================
# HELPERS
# ============================================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_tag_to_location_mapping(pg_cur):
    """
    Get mapping of old location_tag_id to new user_location_id
    for migrated floors (F1-F7)

    Returns: {396: new_ul_id, 397: new_ul_id, ...}
    """
    pg_cur.execute("""
        SELECT id, migration_id, name_th, name_en
        FROM user_locations
        WHERE organization_id = %s
          AND migration_id = ANY(%s)
          AND deleted_date IS NULL
          AND is_active = TRUE
    """, (ORG_ID_NEW, LOCATION_TAG_IDS))

    mapping = {}
    for row in pg_cur.fetchall():
        old_tag_id = int(row["migration_id"])
        new_ul_id = row["id"]
        mapping[old_tag_id] = new_ul_id
        log(f"  Tag {old_tag_id} ({row['name_th']}) → user_location {new_ul_id}")

    return mapping


def update_transactions_origin(pg_cur, pg_conn, tag_to_location_map, dry_run=False):
    """
    Update transactions where:
    - origin_id = BUILDING_USER_LOCATION_ID (9828 = อาคารปทุมวัน building)
    - location_tag_id is set (points to old location_tag)

    Change origin_id to point to the migrated floor user_location instead.

    This fixes transactions that were created with origin = building level,
    but should actually point to floor level (F1-F7).
    """
    log(f"\nUpdating transaction origins from building {BUILDING_USER_LOCATION_ID} to floors...")

    # Find transactions with origin = building and location_tag_id set
    pg_cur.execute("""
        SELECT
            t.id,
            t.origin_id,
            t.destination_ids,
            t.location_tag_id,
            t.migration_id,
            ul_origin.name_th as origin_name
        FROM transactions t
        LEFT JOIN user_locations ul_origin ON t.origin_id = ul_origin.id
        WHERE t.organization_id = %s
          AND t.origin_id = %s
          AND t.location_tag_id IS NOT NULL
          AND t.deleted_date IS NULL
    """, (ORG_ID_NEW, BUILDING_USER_LOCATION_ID))

    transactions = pg_cur.fetchall()
    log(f"  Found {len(transactions)} transactions with origin={BUILDING_USER_LOCATION_ID} and location_tag_id set")

    if not transactions:
        log("  No transactions to update")
        return 0

    updated = 0
    skipped_no_mapping = 0
    skipped_already_correct = 0

    for tx in transactions:
        tx_id = tx["id"]
        old_origin = tx["origin_id"]
        location_tag_id = tx["location_tag_id"]

        # Get new floor user_location from mapping
        new_origin = tag_to_location_map.get(location_tag_id)

        if not new_origin:
            skipped_no_mapping += 1
            log(f"    [SKIP] tx {tx_id}: No mapping for location_tag {location_tag_id}")
            continue

        if old_origin == new_origin:
            skipped_already_correct += 1
            continue

        if dry_run:
            log(f"    [DRY-RUN] Would update tx {tx_id}: origin {old_origin} → {new_origin} (tag {location_tag_id})")
        else:
            pg_cur.execute("""
                UPDATE transactions
                SET origin_id = %s,
                    updated_date = NOW()
                WHERE id = %s
            """, (new_origin, tx_id))
            log(f"    [UPDATE] tx {tx_id}: origin {old_origin} → {new_origin} ({tx['origin_name']} → migrated floor)")

        updated += 1

    if not dry_run:
        pg_conn.commit()

    log(f"\n  Transaction origin update summary:")
    log(f"    Updated: {updated}")
    log(f"    Skipped (no mapping): {skipped_no_mapping}")
    log(f"    Skipped (already correct): {skipped_already_correct}")

    return updated


def update_transactions_destination(pg_cur, pg_conn, tag_to_location_map, dry_run=False):
    """
    Update transactions where:
    - destination_id = BUILDING_USER_LOCATION_ID (9828 = อาคารปทุมวัน building)
    - location_tag_id is set (points to old location_tag)

    Change destination_id to point to the migrated floor user_location instead.
    """
    log(f"\nUpdating transaction destinations from building {BUILDING_USER_LOCATION_ID} to floors...")

    pg_cur.execute("""
        SELECT
            t.id,
            t.origin_id,
            t.destination_ids,
            t.location_tag_id,
            t.migration_id,
            ul_origin.name_th as origin_name
        FROM transactions t
        LEFT JOIN user_locations ul_origin ON t.origin_id = ul_origin.id
        WHERE t.organization_id = %s
          AND %s = ANY(t.destination_ids)
          AND t.location_tag_id IS NOT NULL
          AND t.deleted_date IS NULL
    """, (ORG_ID_NEW, BUILDING_USER_LOCATION_ID))

    transactions = pg_cur.fetchall()
    log(f"  Found {len(transactions)} transactions with destination={BUILDING_USER_LOCATION_ID} and location_tag_id set")

    if not transactions:
        log("  No transactions to update")
        return 0

    updated = 0
    skipped_no_mapping = 0
    skipped_already_correct = 0

    for tx in transactions:
        tx_id = tx["id"]
        old_dest = tx["destination_id"]
        location_tag_id = tx["location_tag_id"]

        new_dest = tag_to_location_map.get(location_tag_id)

        if not new_dest:
            skipped_no_mapping += 1
            log(f"    [SKIP] tx {tx_id}: No mapping for location_tag {location_tag_id}")
            continue

        if old_dest == new_dest:
            skipped_already_correct += 1
            continue

        if dry_run:
            log(f"    [DRY-RUN] Would update tx {tx_id}: destination {old_dest} → {new_dest} (tag {location_tag_id})")
        else:
            pg_cur.execute("""
                UPDATE transactions
                SET destination_id = %s,
                    updated_date = NOW()
                WHERE id = %s
            """, (new_dest, tx_id))
            log(f"    [UPDATE] tx {tx_id}: destination {old_dest} → {new_dest} ({tx['dest_name']} → migrated floor)")

        updated += 1

    if not dry_run:
        pg_conn.commit()

    log(f"\n  Transaction destination update summary:")
    log(f"    Updated: {updated}")
    log(f"    Skipped (no mapping): {skipped_no_mapping}")
    log(f"    Skipped (already correct): {skipped_already_correct}")

    return updated


def main():
    dry_run = "--dry-run" in sys.argv

    log("=" * 80)
    log("Organization 133 (Pathumwan) Migration Script")
    log(f"  New org_id: {ORG_ID_NEW}")
    log(f"  Old org_id: {ORG_ID_OLD}")
    log(f"  Building: {BUILDING_NAME} (id={BUILDING_USER_LOCATION_ID})")
    log(f"  Dry run: {dry_run}")
    log("=" * 80)

    # Step 1: Run migrate_org_structure.py for 133.csv
    log("\nStep 1: Running migrate_org_structure.py for 133.csv...")
    import subprocess
    cmd = ["python3", "migrate_org_structure.py", "133.csv"]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        log(f"ERROR: migrate_org_structure.py failed with return code {result.returncode}")
        sys.exit(1)

    log("\n✓ migrate_org_structure.py completed successfully")

    # Step 2: Connect to databases and update transactions
    log("\nStep 2: Connecting to databases...")
    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get mapping of location_tag_id → new user_location_id
        log("\nStep 3: Getting location_tag to user_location mapping...")
        tag_to_location_map = get_tag_to_location_mapping(pg_cur)

        if not tag_to_location_map:
            log("\n⚠️  WARNING: No migrated floors found!")
            log("   This might mean the migration hasn't run yet, or floors already existed.")
            log("   Skipping transaction updates.")
        else:
            log(f"\n✓ Found {len(tag_to_location_map)} migrated floors")

            # Update transaction origins
            log("\nStep 4: Updating transaction origins...")
            origin_updated = update_transactions_origin(pg_cur, pg_conn, tag_to_location_map, dry_run)

            # Update transaction destinations
            log("\nStep 5: Updating transaction destinations...")
            dest_updated = update_transactions_destination(pg_cur, pg_conn, tag_to_location_map, dry_run)

            log("\n" + "=" * 80)
            log("Migration Complete!")
            log(f"  Origins updated: {origin_updated}")
            log(f"  Destinations updated: {dest_updated}")
            log("=" * 80)

    except Exception as e:
        if not dry_run:
            pg_conn.rollback()
        log(f"\nERROR: {e}")
        raise
    finally:
        pg_cur.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
