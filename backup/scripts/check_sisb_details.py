import pymysql
import psycopg2
import psycopg2.extras

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310, "user": "admin", "password": "GeppThailand123456$",
    "database": "Gepp_new", "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}
PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()
pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

new_org_id = 2404
old_org_id = 2726

# =====================================================
# 1. WRONGLY DELETED locations in new PG (active in old, deleted in new)
# =====================================================
wrongly_deleted_ids = []
pg_cur.execute("""
    SELECT id, migration_id, name_en, name_th, display_name, type, deleted_date
    FROM user_locations
    WHERE organization_id = %s AND is_location = true AND deleted_date IS NOT NULL AND migration_id IS NOT NULL
""", (new_org_id,))
for r in pg_cur.fetchall():
    old_id = int(r['migration_id'])
    mysql_cur.execute("SELECT id, name_th, name_en, deleted_date FROM business_units WHERE id = %s", (old_id,))
    old = mysql_cur.fetchone()
    if old and old['deleted_date'] is None:
        wrongly_deleted_ids.append(r['id'])
        print(f"WRONGLY DELETED location: new_id={r['id']}, migration_id={r['migration_id']}, "
              f"name_th={r['name_th']}, name_en={r['name_en']}, type={r['type']}")

print(f"\nTotal wrongly deleted locations to restore: {len(wrongly_deleted_ids)}")

# =====================================================
# 2. MISSING locations (exist in old, not migrated to new)
# =====================================================
print(f"\n{'='*60}")
print("MISSING LOCATIONS (need to be created in new PG)")
missing_old_ids = [15945, 15946, 15947]
for old_id in missing_old_ids:
    mysql_cur.execute("""
        SELECT bu.id, bu.name_en, bu.name_th, bu.type, bu.address, bu.email, bu.phone,
               bu.is_active, bu.deleted_date, bu.created_date, bu.updated_date,
               bu.belong_to_user, bu.children
        FROM business_units bu WHERE bu.id = %s
    """, (old_id,))
    old = mysql_cur.fetchone()
    if old:
        print(f"\n  old_id={old['id']}")
        print(f"    name_th={old['name_th']}")
        print(f"    name_en={old['name_en']}")
        print(f"    type={old['type']}")
        print(f"    address={old['address']}")
        print(f"    email={old['email']}")
        print(f"    phone={old['phone']}")
        print(f"    is_active={old['is_active']}")
        print(f"    deleted={old['deleted_date']}")
        print(f"    created={old['created_date']}")
        print(f"    belong_to_user={old['belong_to_user']}")
        print(f"    children={old['children']}")

# =====================================================
# 3. MISSING users
# =====================================================
print(f"\n{'='*60}")
print("MISSING USERS (need to be created in new PG)")
missing_user_ids = [23282, 23286, 23287]
for uid in missing_user_ids:
    mysql_cur.execute("""
        SELECT u.id, u.email, u.firstname, u.lastname, u.phone, u.platform,
               u.is_active, u.deleted_date, u.created_date, u.role,
               u.`business-role`, u.organization
        FROM users u WHERE u.id = %s
    """, (uid,))
    old = mysql_cur.fetchone()
    if old:
        print(f"\n  old_id={old['id']}")
        print(f"    email={old['email']}")
        print(f"    firstname={old['firstname']}, lastname={old['lastname']}")
        print(f"    phone={old['phone']}")
        print(f"    platform={old['platform']}")
        print(f"    is_active={old['is_active']}")
        print(f"    deleted={old['deleted_date']}")
        print(f"    created={old['created_date']}")
        print(f"    role={old['role']}, business-role={old['business-role']}")

# =====================================================
# 4. NAME MISMATCHES — show details
# =====================================================
print(f"\n{'='*60}")
print("NAME MISMATCHES")
name_mismatch_ids = [14657, 14660, 14661, 14662, 15639, 15641, 15642]
for old_id in name_mismatch_ids:
    mysql_cur.execute("SELECT id, name_en, name_th FROM business_units WHERE id = %s", (old_id,))
    old = mysql_cur.fetchone()
    pg_cur.execute("SELECT id, migration_id, name_en, name_th, display_name FROM user_locations WHERE migration_id = %s AND organization_id = %s",
                   (str(old_id), new_org_id))
    new = pg_cur.fetchone()
    if old and new:
        print(f"  old_id={old_id}: old_name_en='{old['name_en']}', old_name_th='{old['name_th']}'")
        print(f"              new_name_en='{new['name_en']}', new_name_th='{new['name_th']}', display_name='{new['display_name']}'")

# =====================================================
# 5. Check PG user_locations columns for reference
# =====================================================
print(f"\n{'='*60}")
pg_cur.execute("""
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_name = 'user_locations' ORDER BY ordinal_position
""")
print("user_locations columns:")
for r in pg_cur.fetchall():
    print(f"  {r['column_name']} ({r['data_type']})")

mysql_conn.close()
pg_conn.close()
