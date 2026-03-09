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

# Step 1: Find org in new PG
pg_cur.execute("""
    SELECT DISTINCT ul.organization_id, ul.email, ul.name_en
    FROM user_locations ul
    WHERE ul.email = 'sisb@gepp.me' AND ul.is_user = true
""")
rows = pg_cur.fetchall()
print("=== New PG: user with email sisb@gepp.me ===")
for r in rows:
    print(f"  org_id={r['organization_id']}, email={r['email']}, name={r['name_en']}")
new_org_id = rows[0]['organization_id']

# Step 2: Find old org in MySQL
mysql_cur.execute("SELECT id, email, organization, firstname, lastname FROM users WHERE email = 'sisb@gepp.me'")
old_users = mysql_cur.fetchall()
print("\n=== Old MySQL: user with email sisb@gepp.me ===")
for r in old_users:
    print(f"  id={r['id']}, org={r['organization']}, email={r['email']}, name={r['firstname']} {r['lastname']}")
old_org_id = old_users[0]['organization']

# =========================================================
# LOCATIONS COMPARISON: business_units (old) vs user_locations is_location (new)
# =========================================================
print(f"\n{'='*70}")
print(f"LOCATIONS: old org={old_org_id}, new org={new_org_id}")
print(f"{'='*70}")

mysql_cur.execute("""
    SELECT bu.id, bu.name_en, bu.name_th, bu.type, bu.deleted_date, bu.address,
           bu.is_active, bu.email, bu.phone
    FROM business_units bu
    WHERE bu.organization = %s
    ORDER BY bu.id
""", (old_org_id,))
old_locations = mysql_cur.fetchall()

pg_cur.execute("""
    SELECT ul.id, ul.migration_id, ul.name_en, ul.name_th, ul.display_name,
           ul.type, ul.deleted_date, ul.is_location, ul.is_user, ul.is_active,
           ul.address, ul.email, ul.phone
    FROM user_locations ul
    WHERE ul.organization_id = %s AND ul.is_location = true
    ORDER BY ul.id
""", (new_org_id,))
new_locations = pg_cur.fetchall()

old_loc_map = {r['id']: r for r in old_locations}
new_loc_by_migration = {}
for r in new_locations:
    if r['migration_id']:
        new_loc_by_migration[str(r['migration_id'])] = r

print(f"Old locations: {len(old_locations)}, New locations: {len(new_locations)}")

# Find mismatches
missing_in_new = []
mismatched = []
for old_id, old in old_loc_map.items():
    new = new_loc_by_migration.get(str(old_id))
    if not new:
        status = "DELETED" if old['deleted_date'] else "ACTIVE"
        missing_in_new.append(old)
        print(f"  MISSING in new: old_id={old_id}, name_en={old['name_en']}, name_th={old['name_th']}, type={old['type']}, {status}")
    else:
        issues = []
        old_deleted = old['deleted_date'] is not None
        new_deleted = new['deleted_date'] is not None
        if old_deleted != new_deleted:
            issues.append(f"deleted: old={'DEL' if old_deleted else 'active'} vs new={'DEL' if new_deleted else 'active'}")

        old_name_en = (old['name_en'] or '').strip()
        new_name_en = (new['name_en'] or '').strip()
        if old_name_en != new_name_en:
            issues.append(f"name_en: old='{old_name_en}' vs new='{new_name_en}'")

        old_name_th = (old['name_th'] or '').strip()
        new_name_th = (new['name_th'] or '').strip()
        if old_name_th != new_name_th:
            issues.append(f"name_th: old='{old_name_th}' vs new='{new_name_th}'")

        old_active = bool(old['is_active'])
        new_active = bool(new['is_active'])
        if old_active != new_active:
            issues.append(f"is_active: old={old_active} vs new={new_active}")

        if issues:
            mismatched.append((old, new, issues))
            for issue in issues:
                print(f"  MISMATCH old_id={old_id} -> new_id={new['id']}: {issue}")

new_without_migration = [r for r in new_locations if not r['migration_id']]

print(f"\n  Missing in new: {len(missing_in_new)}")
print(f"  Mismatched: {len(mismatched)}")
print(f"  New without migration_id: {len(new_without_migration)}")

# =========================================================
# USERS COMPARISON: users (old) vs user_locations is_user (new)
# =========================================================
print(f"\n{'='*70}")
print(f"USERS: old org={old_org_id}, new org={new_org_id}")
print(f"{'='*70}")

mysql_cur.execute("""
    SELECT u.id, u.email, u.firstname, u.lastname, u.organization,
           u.deleted_date, u.role, u.is_active, u.phone, u.platform
    FROM users u
    WHERE u.organization = %s
    ORDER BY u.id
""", (old_org_id,))
old_users_all = mysql_cur.fetchall()

pg_cur.execute("""
    SELECT ul.id, ul.migration_id, ul.email, ul.name_en, ul.display_name,
           ul.deleted_date, ul.is_user, ul.is_active, ul.phone, ul.platform
    FROM user_locations ul
    WHERE ul.organization_id = %s AND ul.is_user = true
    ORDER BY ul.id
""", (new_org_id,))
new_users_all = pg_cur.fetchall()

new_user_by_migration = {}
for r in new_users_all:
    if r['migration_id']:
        new_user_by_migration[str(r['migration_id'])] = r

print(f"Old users: {len(old_users_all)}, New users: {len(new_users_all)}")

user_missing = []
user_mismatched = []
for old_u in old_users_all:
    new_u = new_user_by_migration.get(str(old_u['id']))
    if not new_u:
        status = "DELETED" if old_u['deleted_date'] else "ACTIVE"
        user_missing.append(old_u)
        print(f"  MISSING in new: old_id={old_u['id']}, email={old_u['email']}, {old_u['firstname']} {old_u['lastname']}, {status}")
    else:
        issues = []
        old_del = old_u['deleted_date'] is not None
        new_del = new_u['deleted_date'] is not None
        if old_del != new_del:
            issues.append(f"deleted: old={'DEL' if old_del else 'active'} vs new={'DEL' if new_del else 'active'}")
        old_email = (old_u['email'] or '').strip()
        new_email = (new_u['email'] or '').strip()
        if old_email != new_email:
            issues.append(f"email: old='{old_email}' vs new='{new_email}'")
        old_active = bool(old_u['is_active'])
        new_active = bool(new_u['is_active'])
        if old_active != new_active:
            issues.append(f"is_active: old={old_active} vs new={new_active}")
        if issues:
            user_mismatched.append((old_u, new_u, issues))
            for issue in issues:
                print(f"  MISMATCH old_id={old_u['id']} -> new_id={new_u['id']}: {issue}")

print(f"\n  User missing in new: {len(user_missing)}")
print(f"  User mismatched: {len(user_mismatched)}")

mysql_conn.close()
pg_conn.close()
