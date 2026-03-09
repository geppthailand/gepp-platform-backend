#!/usr/bin/env python3
"""
Query UOB organization structure from both legacy MySQL and new PostgreSQL.
Outputs data needed to build the org_structures/117.csv hierarchy.
"""

import json
import pymysql
import psycopg2
import psycopg2.extras

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

def main():
    # ---- MySQL: business_units for org=435 ----
    print("=" * 80)
    print("MYSQL: business_units WHERE organization=435 (UOB)")
    print("=" * 80)
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()

    mysql_cur.execute("""
        SELECT id, name_th, name_en, functions, type, is_active, deleted_date
        FROM business_units
        WHERE organization = 435
        ORDER BY id
    """)
    bus_units = mysql_cur.fetchall()
    print(f"\nFound {len(bus_units)} business_units:")
    print(f"{'ID':<8} {'name_th':<35} {'name_en':<30} {'functions':<40} {'type':<20} {'active':<7} {'deleted'}")
    print("-" * 170)
    for bu in bus_units:
        funcs = bu['functions'] or ''
        if len(funcs) > 38:
            funcs = funcs[:38] + '..'
        name_th = (bu['name_th'] or '')[:33]
        name_en = (bu['name_en'] or '')[:28]
        typ = (bu['type'] or '')[:18]
        deleted = 'Y' if bu['deleted_date'] else '-'
        print(f"{bu['id']:<8} {name_th:<35} {name_en:<30} {funcs:<40} {typ:<20} {bu['is_active']:<7} {deleted}")

    # Check which ones have wastemaker in functions
    print("\n--- Origin locations (functions contains 'wastemaker') ---")
    for bu in bus_units:
        funcs = bu['functions'] or ''
        if 'wastemaker' in funcs.lower():
            print(f"  ID={bu['id']}  {bu['name_th']}  |  {bu['name_en']}  |  functions={funcs}")

    # ---- MySQL: location_tags for org=435 ----
    print("\n" + "=" * 80)
    print("MYSQL: location_tags WHERE organization_id=435 (UOB)")
    print("=" * 80)
    mysql_cur.execute("""
        SELECT id, name_th, name_en, business_unit, is_active, is_root, deleted_date, start_date, end_date, note
        FROM location_tags
        WHERE organization_id = 435
        ORDER BY id
    """)
    loc_tags = mysql_cur.fetchall()
    print(f"\nFound {len(loc_tags)} location_tags:")
    print(f"{'ID':<6} {'name_th':<40} {'name_en':<30} {'business_unit':<15} {'root':<5} {'active':<7} {'deleted':<8} {'start_date':<22} {'end_date'}")
    print("-" * 170)
    for lt in loc_tags:
        name_th = (lt['name_th'] or '')[:38]
        name_en = (lt['name_en'] or '')[:28]
        bu = (lt['business_unit'] or '')[:13]
        deleted = 'Y' if lt['deleted_date'] else '-'
        sd = str(lt['start_date'] or '-')[:20]
        ed = str(lt['end_date'] or '-')[:20]
        print(f"{lt['id']:<6} {name_th:<40} {name_en:<30} {bu:<15} {lt['is_root']:<5} {lt['is_active']:<7} {deleted:<8} {sd:<22} {ed}")

    mysql_cur.close()
    mysql_conn.close()

    # ---- PostgreSQL: user_locations for org=117 ----
    print("\n" + "=" * 80)
    print("POSTGRESQL: user_locations WHERE organization_id=117 (UOB)")
    print("=" * 80)
    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    pg_cur.execute("""
        SELECT id, name_th, name_en, display_name, functions, type, hub_type,
               is_location, is_user, is_active, deleted_date, tags
        FROM user_locations
        WHERE organization_id = 117
          AND is_active = TRUE
          AND deleted_date IS NULL
        ORDER BY id
    """)
    ul_rows = pg_cur.fetchall()
    print(f"\nFound {len(ul_rows)} active user_locations:")
    print(f"{'ID':<8} {'name_th':<35} {'functions':<40} {'type':<15} {'is_loc':<7} {'is_usr':<7} {'tags'}")
    print("-" * 150)
    for ul in ul_rows:
        name_th = (ul['name_th'] or '')[:33]
        funcs = (ul['functions'] or '')[:38]
        typ = (ul['type'] or '')[:13]
        tags = str(ul['tags'] or '')[:40]
        print(f"{ul['id']:<8} {name_th:<35} {funcs:<40} {typ:<15} {ul['is_location']:<7} {ul['is_user']:<7} {tags}")

    pg_cur.close()
    pg_conn.close()

    print("\nDone!")


if __name__ == "__main__":
    main()
