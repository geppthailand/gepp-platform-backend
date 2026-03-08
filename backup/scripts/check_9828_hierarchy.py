#!/usr/bin/env python3
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

# Check 9828 and its parent
pg_cur.execute("""
    SELECT id, name_th, name_en, type, parent_location_id, migration_id, organization_id
    FROM user_locations
    WHERE id = 9828
""")
loc_9828 = pg_cur.fetchone()

print("User Location 9828 (อาคารปทุมวัน):")
print(f"  ID: {loc_9828['id']}")
print(f"  Name TH: {loc_9828['name_th']}")
print(f"  Type: {loc_9828['type']}")
print(f"  Parent ID: {loc_9828['parent_location_id']}")
print(f"  Migration ID: {loc_9828['migration_id']}")
print(f"  Org ID: {loc_9828['organization_id']}")

# Check if it has children
pg_cur.execute("""
    SELECT id, name_th, name_en, type, migration_id
    FROM user_locations
    WHERE parent_location_id = 9828
      AND deleted_date IS NULL
    ORDER BY id
""")
children = pg_cur.fetchall()

if children:
    print(f"\nChildren of 9828: ({len(children)} found)")
    for child in children:
        print(f"  - {child['id']}: {child['name_th']} (type={child['type']}, mig_id={child['migration_id']})")
else:
    print("\nNo children found for 9828")

# Check what org 113 actually is
pg_cur.execute("SELECT id, name_th, name_en, migration_id FROM organizations WHERE id = 113")
org_113 = pg_cur.fetchone()
if org_113:
    print(f"\nOrganization 113:")
    print(f"  Name TH: {org_113['name_th']}")
    print(f"  Name EN: {org_113['name_en']}")
    print(f"  Migration ID: {org_113['migration_id']}")

# Check what org 133 actually is
pg_cur.execute("SELECT id, name_th, name_en, migration_id FROM organizations WHERE id = 133")
org_133 = pg_cur.fetchone()
if org_133:
    print(f"\nOrganization 133:")
    print(f"  Name TH: {org_133['name_th']}")
    print(f"  Name EN: {org_133['name_en']}")
    print(f"  Migration ID: {org_133['migration_id']}")

pg_cur.close()
pg_conn.close()
