#!/usr/bin/env python3
"""
Check for 'อาคารปทุมวัน' (Pathumwan building) in new PostgreSQL database for org 133
"""

import psycopg2
import psycopg2.extras

LOCAL_PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "geppsa-ard",
    "password": "",
}

def main():
    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        print("Checking for 'อาคารปทุมวัน' building in org 133...")
        pg_cur.execute("""
            SELECT
                id,
                name_th,
                name_en,
                display_name,
                type,
                functions,
                parent_location_id,
                migration_id,
                is_active
            FROM user_locations
            WHERE organization_id = 133
              AND (name_th LIKE '%ปทุมวัน%' OR name_en LIKE '%ปทุมวัน%' OR display_name LIKE '%ปทุมวัน%')
              AND deleted_date IS NULL
            ORDER BY id
        """)

        buildings = pg_cur.fetchall()

        if buildings:
            print(f"\nFound {len(buildings)} location(s) matching 'ปทุมวัน' in org 133:")
            print(f"\n{'ID':<8} {'Name TH':<30} {'Name EN':<30} {'Type':<10} {'Parent':<8} {'Migration ID':<12} {'Active':<8}")
            print("-" * 130)
            for b in buildings:
                print(f"{b['id']:<8} {b['name_th'] or 'N/A':<30} {b['name_en'] or 'N/A':<30} {b['type'] or 'N/A':<10} {b['parent_location_id'] or 'N/A':<8} {b['migration_id'] or 'N/A':<12} {b['is_active']}")
        else:
            print("\n❌ No building matching 'ปทุมวัน' found in org 133")
            print("\nSearching for ALL buildings in org 133...")
            pg_cur.execute("""
                SELECT
                    id,
                    name_th,
                    name_en,
                    display_name,
                    type,
                    parent_location_id,
                    migration_id
                FROM user_locations
                WHERE organization_id = 133
                  AND type = 'building'
                  AND is_active = TRUE
                  AND deleted_date IS NULL
                ORDER BY name_th
            """)

            all_buildings = pg_cur.fetchall()
            if all_buildings:
                print(f"\nFound {len(all_buildings)} buildings in org 133:")
                print(f"\n{'ID':<8} {'Name TH':<40} {'Name EN':<40} {'Type':<10} {'Parent':<8}")
                print("-" * 110)
                for b in all_buildings:
                    print(f"{b['id']:<8} {b['name_th'] or 'N/A':<40} {b['name_en'] or 'N/A':<40} {b['type'] or 'N/A':<10} {b['parent_location_id'] or 'N/A':<8}")
            else:
                print("\n❌ No buildings found in org 133 at all")

        # Also check business_unit id 13952 migration
        print("\n" + "=" * 130)
        print("Checking if business_unit 13952 was migrated...")
        pg_cur.execute("""
            SELECT
                id,
                name_th,
                name_en,
                display_name,
                type,
                migration_id
            FROM user_locations
            WHERE organization_id = 133
              AND migration_id = '13952'
              AND deleted_date IS NULL
        """)

        migrated = pg_cur.fetchone()
        if migrated:
            print(f"\n✓ Business unit 13952 ('อาคารปทุมวัน') was migrated to user_location:")
            print(f"  ID: {migrated['id']}")
            print(f"  Name TH: {migrated['name_th']}")
            print(f"  Name EN: {migrated['name_en']}")
            print(f"  Type: {migrated['type']}")
        else:
            print("\n❌ Business unit 13952 has NOT been migrated yet")

    finally:
        pg_cur.close()
        pg_conn.close()

if __name__ == "__main__":
    main()
