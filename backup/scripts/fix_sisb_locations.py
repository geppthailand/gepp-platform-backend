import pymysql
import psycopg2
import psycopg2.extras
from datetime import datetime

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
# FIX 1: Restore wrongly deleted locations
# =====================================================
wrongly_deleted_ids = [10420, 10419, 10421, 10452, 11259, 11261, 11260]
print(f"=== FIX 1: Restore {len(wrongly_deleted_ids)} wrongly deleted locations ===")
for loc_id in wrongly_deleted_ids:
    pg_cur.execute("SELECT id, migration_id, name_th, deleted_date FROM user_locations WHERE id = %s", (loc_id,))
    r = pg_cur.fetchone()
    print(f"  Restoring id={r['id']}, migration_id={r['migration_id']}, name={r['name_th']}")
    pg_cur.execute("UPDATE user_locations SET deleted_date = NULL WHERE id = %s", (loc_id,))

# =====================================================
# FIX 2: Create missing locations (old business_units not migrated)
# =====================================================
missing_bu_ids = [15945, 15946, 15947]
print(f"\n=== FIX 2: Create {len(missing_bu_ids)} missing locations ===")

for old_id in missing_bu_ids:
    mysql_cur.execute("""
        SELECT bu.id, bu.name_en, bu.name_th, bu.type, bu.address, bu.email, bu.phone,
               bu.is_active, bu.deleted_date, bu.created_date, bu.updated_date,
               bu.platform, bu.postal_code, bu.province_id, bu.district_id,
               bu.subdistrict_id, bu.country_id, bu.belong_to_user, bu.coordinate,
               bu.functions, bu.population, bu.material, bu.note
        FROM business_units bu WHERE bu.id = %s
    """, (old_id,))
    old = mysql_cur.fetchone()
    if not old:
        print(f"  SKIP: old_id={old_id} not found")
        continue

    name_th = (old['name_th'] or '').strip()
    name_en = (old['name_en'] or '').strip()
    display_name = name_en if name_en else name_th

    # Check if already exists in new PG
    pg_cur.execute("SELECT id FROM user_locations WHERE migration_id = %s AND organization_id = %s",
                   (old_id, new_org_id))
    existing = pg_cur.fetchone()
    if existing:
        print(f"  SKIP: old_id={old_id} already exists as new_id={existing['id']}")
        continue

    # Map platform: old is lowercase, new PG enum is uppercase
    platform_map = {
        'gepp_business_web': 'GEPP_BUSINESS_WEB',
        'gepp_epr_web': 'GEPP_EPR_WEB',
        'gepp_reward_app': 'GEPP_REWARD_APP',
        'gepp_backoffice': 'ADMIN_WEB',
        'admin_web': 'ADMIN_WEB',
        'main_backend': 'API',
        'user_trial': 'WEB',
        'user_paid': 'WEB',
        'n/a': 'NA',
    }
    old_platform = old['platform'] or 'gepp_business_web'
    pg_platform = platform_map.get(old_platform, 'GEPP_BUSINESS_WEB')

    print(f"  Creating: old_id={old_id}, name_th='{name_th}', display_name='{display_name}'")
    pg_cur.execute("""
        INSERT INTO user_locations (
            is_user, is_location, name_th, name_en, display_name,
            email, phone, platform, type,
            address, postal_code, province_id, district_id, subdistrict_id, country_id,
            functions, population, material, note,
            organization_id, is_active, created_date, updated_date, deleted_date,
            migration_id
        ) VALUES (
            false, true, %s, %s, %s,
            %s, %s, %s::platform_enum, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s
        ) RETURNING id
    """, (
        name_th, name_en or None, display_name,
        old['email'], old['phone'],
        pg_platform,
        old['type'],
        old['address'], old['postal_code'],
        old['province_id'], old['district_id'], old['subdistrict_id'], old['country_id'],
        old['functions'], old['population'], old['material'], old['note'],
        new_org_id, bool(old['is_active']),
        old['created_date'], old['updated_date'], old['deleted_date'],
        old_id
    ))
    new_row = pg_cur.fetchone()
    print(f"    -> Created new_id={new_row['id']}")

# =====================================================
# FIX 3: Create missing users
# =====================================================
missing_user_ids = [23282, 23286, 23287]
print(f"\n=== FIX 3: Create {len(missing_user_ids)} missing users ===")

for old_uid in missing_user_ids:
    mysql_cur.execute("""
        SELECT u.id, u.email, u.firstname, u.lastname, u.phone, u.platform,
               u.is_active, u.deleted_date, u.created_date, u.updated_date,
               u.role, u.`business-role`, u.username, u.password,
               u.facebook_id, u.apple_id, u.google_id_gmail,
               u.is_email_active, u.email_notification, u.note,
               u.expired_date, u.locale, u.country_id, u.currency_id
        FROM users u WHERE u.id = %s
    """, (old_uid,))
    old = mysql_cur.fetchone()
    if not old:
        print(f"  SKIP: old_id={old_uid} not found")
        continue

    # Check if already exists
    pg_cur.execute("SELECT id FROM user_locations WHERE migration_id = %s AND organization_id = %s AND is_user = true",
                   (old_uid, new_org_id))
    existing = pg_cur.fetchone()
    if existing:
        print(f"  SKIP: old_id={old_uid} already exists as new_id={existing['id']}")
        continue

    firstname = (old['firstname'] or '').strip()
    lastname = (old['lastname'] or '').strip()
    display_name = f"{firstname} {lastname}".strip()
    name_en = display_name

    # Map platform
    platform_map = {
        'gepp_business_web': 'GEPP_BUSINESS_WEB',
        'gepp_epr_web': 'GEPP_EPR_WEB',
        'gepp_reward_app': 'GEPP_REWARD_APP',
        'gepp_backoffice': 'ADMIN_WEB',
        'admin_web': 'ADMIN_WEB',
        'main_backend': 'API',
        'user_trial': 'WEB',
        'user_paid': 'WEB',
        'n/a': 'NA',
    }
    old_platform = old['platform'] or 'gepp_business_web'
    pg_platform = platform_map.get(old_platform, 'GEPP_BUSINESS_WEB')

    print(f"  Creating: old_id={old_uid}, email={old['email']}, name={display_name}")
    pg_cur.execute("""
        INSERT INTO user_locations (
            is_user, is_location, name_en, display_name, first_name, last_name,
            email, is_email_active, email_notification, phone,
            username, password, facebook_id, apple_id, google_id_gmail,
            platform, note, locale, country_id, currency_id,
            organization_id, is_active, created_date, updated_date, deleted_date,
            expired_date, migration_id
        ) VALUES (
            true, false, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s::platform_enum, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        ) RETURNING id
    """, (
        name_en, display_name, firstname, lastname,
        old['email'], bool(old['is_email_active']), old['email_notification'], old['phone'],
        old['username'], old['password'], old['facebook_id'], old['apple_id'], old['google_id_gmail'],
        pg_platform,
        old['note'], old['locale'], old['country_id'], old['currency_id'],
        new_org_id, bool(old['is_active']),
        old['created_date'], old['updated_date'], old['deleted_date'],
        old['expired_date'], old_uid
    ))
    new_row = pg_cur.fetchone()
    print(f"    -> Created new_id={new_row['id']}")

# =====================================================
# COMMIT
# =====================================================
confirm = input("\nProceed with commit? (yes/no): ")
if confirm.strip().lower() == 'yes':
    pg_conn.commit()
    print("All fixes committed successfully!")
else:
    pg_conn.rollback()
    print("Rolled back.")

mysql_conn.close()
pg_conn.close()
