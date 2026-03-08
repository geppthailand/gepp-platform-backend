#!/usr/bin/env python3
"""
Query location_tags from old MySQL database for organization_id = 451
and prepare data for migration to org_structures/113.csv
"""

import pymysql
import json

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

def main():
    # Connect to MySQL
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()

    try:
        # First, get business_unit IDs for org 451
        print("Querying business_units for org 451...")
        mysql_cur.execute("""
            SELECT id
            FROM business_units
            WHERE organization = %s
              AND is_active = 1
              AND deleted_date IS NULL
        """, (451,))

        business_unit_ids = [row['id'] for row in mysql_cur.fetchall()]
        print(f"Found {len(business_unit_ids)} business_units for org 451")

        if not business_unit_ids:
            print("No business_units found for org 451. Exiting.")
            return

        # Query location_tags for these business_units
        print("Querying location_tags from old database (org_id = 451)...")
        placeholders = ','.join(['%s'] * len(business_unit_ids))
        mysql_cur.execute(f"""
            SELECT
                lt.id,
                lt.name_th,
                lt.name_en,
                lt.business_unit,
                lt.is_active,
                lt.is_root,
                bu.name_th as business_unit_name,
                bu.name_en as business_unit_name_en
            FROM location_tags lt
            LEFT JOIN business_units bu ON lt.business_unit = bu.id
            WHERE lt.business_unit IN ({placeholders})
              AND lt.is_active = 1
              AND lt.deleted_date IS NULL
            ORDER BY lt.name_th, lt.name_en
        """, business_unit_ids)

        tags = mysql_cur.fetchall()

        print(f"\nFound {len(tags)} location_tags for organization 451:\n")
        print(f"{'ID':<6} {'Business Unit':<30} {'Name TH':<40} {'Name EN':<40}")
        print("-" * 120)

        floors = []
        for tag in tags:
            print(f"{tag['id']:<6} {tag['business_unit_name'] or 'N/A':<30} {tag['name_th'] or 'N/A':<40} {tag['name_en'] or 'N/A':<40}")

            # Collect floor entries for CSV
            if tag['name_th'] or tag['name_en']:
                name = tag['name_th'] or tag['name_en']
                floors.append({
                    'id': tag['id'],
                    'name': name,
                    'name_th': tag['name_th'],
                    'name_en': tag['name_en'],
                    'business_unit': tag['business_unit'],
                    'business_unit_name': tag['business_unit_name'],
                    'csv_entry': f"mig:{tag['id']}:{name}"
                })

        # Print CSV format suggestions
        print("\n" + "=" * 120)
        print("CSV Format for org_structures/113.csv (floors column):")
        print("=" * 120)
        for floor in floors:
            print(f"{floor['csv_entry']}")

        # Also check business_units to understand hierarchy
        print("\n" + "=" * 120)
        print("Business Units for org 451:")
        print("=" * 120)
        mysql_cur.execute("""
            SELECT
                id,
                name_th,
                name_en,
                organization
            FROM business_units
            WHERE organization = %s
              AND is_active = 1
              AND deleted_date IS NULL
            ORDER BY name_th
        """, (451,))

        business_units = mysql_cur.fetchall()
        print(f"\n{'ID':<6} {'Name TH':<40} {'Name EN':<40}")
        print("-" * 90)
        for bu in business_units:
            print(f"{bu['id']:<6} {bu['name_th'] or 'N/A':<40} {bu['name_en'] or 'N/A':<40}")

        # Save to JSON for reference
        output = {
            'organization_id': 451,
            'location_tags': tags,
            'business_units': business_units,
            'csv_entries': [f['csv_entry'] for f in floors]
        }

        with open('location_tags_451.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n✓ Data saved to location_tags_451.json")

    finally:
        mysql_cur.close()
        mysql_conn.close()

if __name__ == "__main__":
    main()
