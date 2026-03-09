#!/usr/bin/env python3
"""
Legacy → New Platform Migration INSERT Script
===============================================
Reads from legacy MySQL (Gepp_new) and inserts into LOCAL PostgreSQL.

Source: MySQL localhost:3306 root/Gepp_new
Target: PostgreSQL localhost:5432 geppsa-ard/postgres

Run migrate_legacy_data.py first for validation/preview.
"""

import json
import struct
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import pymysql
import psycopg2
import psycopg2.extras

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

# LOCAL_PG_CONFIG = {
#     "host": "13.215.109.125",
#     "port": 5432,
#     "dbname": "postgres",
#     "user": "postgres",
#     "password": "6N0i8SKEVfd19B3",
# }

# Default role presets for new organizations
DEFAULT_ORG_ROLES = [
    {"key": "admin", "name": "Administrator", "description": "Full access", "is_system": True},
    {"key": "data_input", "name": "Data Input Specialist", "description": "Can create/edit transactions", "is_system": True},
    {"key": "auditor", "name": "Auditor", "description": "Can audit transactions", "is_system": True},
    {"key": "viewer", "name": "Viewer", "description": "Read-only access", "is_system": True},
]

BATCH_SIZE = 500

# ============================================================================
# STEP 0: COPY LOCATION REFERENCE DATA
# ============================================================================

def copy_reference_data(mysql_cur, pg_cur, pg_conn, remote_pg_config):
    """Copy all reference data: locations from MySQL, materials from remote PG, currencies from MySQL."""
    log("Step 0: Populating reference data...")

    # Ensure migration_id columns exist on all target tables
    for t in ["organizations", "organization_info", "user_locations", "transactions", "transaction_records"]:
        pg_cur.execute(f"""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = '{t}' AND column_name = 'migration_id'
        """)
        if not pg_cur.fetchone():
            pg_cur.execute(f"ALTER TABLE {t} ADD COLUMN migration_id BIGINT")
            log(f"  Added migration_id column to {t}")
    pg_conn.commit()

    # Set timezone to UTC so MySQL datetimes (UTC+0) are stored correctly
    pg_cur.execute("SET timezone = 'UTC'")

    # Disable FK checks for bulk inserts
    pg_cur.execute("SET session_replication_role = 'replica'")
    pg_conn.commit()

    # Clean up ONLY previously migrated data (keep existing non-migrated data)
    log("  Cleaning up previously migrated data only (migration_id IS NOT NULL)...")

    # 1. First delete organization_roles linked to migrated organizations (no migration_id column)
    pg_cur.execute("""
        DELETE FROM organization_roles
        WHERE organization_id IN (SELECT id FROM organizations WHERE migration_id IS NOT NULL)
    """)
    cnt = pg_cur.rowcount
    if cnt > 0:
        log(f"    organization_roles: removed {cnt} old migrated rows")

    # 2. Delete from tables that have migration_id column (order: children first)
    migrated_tables = [
        "transaction_records", "transactions",
        "user_locations", "organization_info", "organizations",
    ]
    for t in migrated_tables:
        pg_cur.execute(f"DELETE FROM {t} WHERE migration_id IS NOT NULL")
        cnt = pg_cur.rowcount
        if cnt > 0:
            log(f"    {t}: removed {cnt} old migrated rows")

    pg_conn.commit()
    log("  Cleaned previously migrated data (existing data preserved)")

    # --- Location data from MySQL ---
    log("  Loading location data from MySQL...")

    # Countries — skip if id or code already exists
    mysql_cur.execute("SELECT id, name_th, name_en, country_code, timezone FROM location_countries")
    countries = mysql_cur.fetchall()
    pg_cur.execute("SELECT id, code FROM location_countries")
    existing_ids = set()
    existing_codes = set()
    for r in pg_cur.fetchall():
        existing_ids.add(r["id"])
        if r["code"]:
            existing_codes.add(r["code"])
    inserted_countries = 0
    for c in countries:
        code = c.get("country_code")
        if c["id"] in existing_ids or (code and code in existing_codes):
            continue
        pg_cur.execute("""
            INSERT INTO location_countries (id, name_th, name_en, code, timezone, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), NOW())
        """, (c["id"], c["name_th"], c["name_en"], code, c.get("timezone")))
        existing_ids.add(c["id"])
        if code:
            existing_codes.add(code)
        inserted_countries += 1
    pg_conn.commit()
    log(f"    Countries: {len(countries)} total, {inserted_countries} inserted, {len(countries)-inserted_countries} skipped (exist)")

    # Regions
    mysql_cur.execute("SELECT id, country_id, name_th, name_en FROM location_regions")
    regions = mysql_cur.fetchall()
    for r in regions:
        pg_cur.execute("""
            INSERT INTO location_regions (id, country_id, name_th, name_en, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET name_th=EXCLUDED.name_th, name_en=EXCLUDED.name_en
        """, (r["id"], r["country_id"], r["name_th"], r["name_en"]))
    pg_conn.commit()
    log(f"    Regions: {len(regions)}")

    # Provinces
    mysql_cur.execute("SELECT id, country_id, region_id, name_th, name_en FROM location_provinces")
    for p in mysql_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO location_provinces (id, country_id, region_id, name_th, name_en, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET name_th=EXCLUDED.name_th, name_en=EXCLUDED.name_en
        """, (p["id"], p["country_id"], p["region_id"], p["name_th"], p["name_en"]))
    pg_conn.commit()
    log(f"    Provinces done")

    # Districts
    mysql_cur.execute("SELECT id, province_id, name_th, name_en FROM location_districts")
    for d in mysql_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO location_districts (id, province_id, name_th, name_en, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET name_th=EXCLUDED.name_th, name_en=EXCLUDED.name_en
        """, (d["id"], d["province_id"], d["name_th"], d["name_en"]))
    pg_conn.commit()
    log(f"    Districts done")

    # Subdistricts
    mysql_cur.execute("SELECT id, district_id, postal_code, name_th, name_en FROM location_subdistricts")
    for s in mysql_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO location_subdistricts (id, district_id, name_th, name_en, postal_code, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET name_th=EXCLUDED.name_th, name_en=EXCLUDED.name_en, postal_code=EXCLUDED.postal_code
        """, (s["id"], s["district_id"], s["name_th"], s["name_en"], s.get("postal_code")))
    pg_conn.commit()
    log(f"    Subdistricts done")

    # Nationalities
    mysql_cur.execute("SELECT id, name FROM nationalities WHERE is_active = 1")
    for n in mysql_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO nationalities (id, name_en, is_active, created_date, updated_date)
            VALUES (%s, %s, TRUE, NOW(), NOW()) ON CONFLICT (id) DO NOTHING
        """, (n["id"], n.get("name")))
    pg_conn.commit()
    log(f"    Nationalities done")

    # Phone codes
    mysql_cur.execute("SELECT id, country, code FROM phone_number_country_code WHERE is_active = 1")
    for p in mysql_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO phone_number_country_codes (id, country_id, code, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, TRUE, NOW(), NOW()) ON CONFLICT (id) DO NOTHING
        """, (p["id"], p.get("country"), p.get("code")))
    pg_conn.commit()
    log(f"    Phone codes done")

    # Banks
    mysql_cur.execute("SELECT id, country_id, bank_code, name_en, name_th FROM banks WHERE is_active = 1")
    for b in mysql_cur.fetchall():
        pg_cur.execute("""
            INSERT INTO banks (id, country_id, code, name_en, name_th, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), NOW()) ON CONFLICT (id) DO NOTHING
        """, (b["id"], b.get("country_id", 212), b.get("bank_code"), b.get("name_en"), b.get("name_th")))
    pg_conn.commit()
    log(f"    Banks done")

    # Currencies: build mapping old_id → new_id by code, insert only missing ones
    pg_cur.execute("SELECT id, code FROM currencies")
    pg_code_to_id = {}
    pg_cur_ids = set()
    for r in pg_cur.fetchall():
        pg_cur_ids.add(r["id"])
        if r["code"]:
            pg_code_to_id[r["code"]] = r["id"]
    pg_cur.execute("SELECT COALESCE(MAX(id), 0) as mx FROM currencies")
    next_cur_id = pg_cur.fetchone()["mx"] + 1

    mysql_cur.execute("SELECT id, name_th, name_en, currency_code FROM currencies WHERE is_active = 1")
    currency_map = {}  # old_mysql_id → new_pg_id
    for c in mysql_cur.fetchall():
        code = c.get("currency_code")
        if code and code in pg_code_to_id:
            currency_map[c["id"]] = pg_code_to_id[code]
        elif code:
            # Insert missing currency (skip if code somehow conflicts)
            try:
                pg_cur.execute("""
                    INSERT INTO currencies (id, name_th, name_en, code, is_active, created_date, updated_date)
                    VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())
                """, (next_cur_id, c.get("name_th"), c.get("name_en"), code))
                currency_map[c["id"]] = next_cur_id
                pg_code_to_id[code] = next_cur_id
                next_cur_id += 1
            except Exception:
                pg_conn.rollback()
                pg_cur.execute("SET session_replication_role = 'replica'")
    pg_conn.commit()
    log(f"    Currencies done (mapped {len(currency_map)})")

    # --- Materials from REMOTE PG (these have the correct new schema) ---
    log("  Loading materials from remote PG...")
    import psycopg2 as pg2
    remote_conn = pg2.connect(**remote_pg_config)
    remote_cur = remote_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Material categories
    remote_cur.execute("SELECT * FROM material_categories WHERE is_active = TRUE")
    cats = remote_cur.fetchall()
    for c in cats:
        pg_cur.execute("""
            INSERT INTO material_categories (id, name_th, name_en, code, color, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), NOW()) ON CONFLICT (id) DO NOTHING
        """, (c["id"], c.get("name_th"), c.get("name_en"), c.get("code"), c.get("color")))
    pg_conn.commit()
    log(f"    Material categories: {len(cats)}")

    # Main materials
    remote_cur.execute("SELECT * FROM main_materials WHERE is_active = TRUE")
    mains = remote_cur.fetchall()
    for m in mains:
        pg_cur.execute("""
            INSERT INTO main_materials (id, name_th, name_en, name_local, code, color, display_order,
                material_tag_groups, is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW()) ON CONFLICT (id) DO NOTHING
        """, (m["id"], m.get("name_th"), m.get("name_en"), m.get("name_local"), m.get("code"),
              m.get("color"), m.get("display_order"), m.get("material_tag_groups")))
    pg_conn.commit()
    log(f"    Main materials: {len(mains)}")

    # Materials
    remote_cur.execute("""
        SELECT id, name_th, name_en, category_id, main_material_id, tags,
               is_global, organization_id, unit_name_th, unit_name_en,
               unit_weight, color, calc_ghg, is_active
        FROM materials WHERE is_active = TRUE
    """)
    mats = remote_cur.fetchall()
    for m in mats:
        pg_cur.execute("""
            INSERT INTO materials (id, name_th, name_en, category_id, main_material_id, tags,
                is_global, organization_id, unit_name_th, unit_name_en, unit_weight, color, calc_ghg,
                is_active, created_date, updated_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
        """, (m["id"], m.get("name_th"), m.get("name_en"), m.get("category_id"),
              m.get("main_material_id"), json.dumps(m.get("tags") or []),
              m.get("is_global"), m.get("organization_id"),
              m.get("unit_name_th"), m.get("unit_name_en"),
              m.get("unit_weight"), m.get("color"), m.get("calc_ghg"),
              m.get("is_active")))
    pg_conn.commit()
    log(f"    Materials: {len(mats)}")

    remote_cur.close()
    remote_conn.close()

    # Reset all sequences
    seqs = [
        ("location_countries", "location_countries_id_seq"),
        ("location_regions", "location_regions_id_seq"),
        ("location_provinces", "location_provinces_id_seq"),
        ("location_districts", "location_districts_id_seq"),
        ("location_subdistricts", "location_subdistricts_id_seq"),
        ("nationalities", "nationalities_id_seq"),
        ("phone_number_country_codes", "phone_number_country_codes_id_seq"),
        ("banks", "banks_id_seq"),
        ("currencies", "currencies_id_seq"),
        ("material_categories", "material_categories_id_seq"),
        ("main_materials", "main_materials_id_seq"),
        ("materials", "materials_id_seq"),
    ]
    for table, seq in seqs:
        try:
            pg_cur.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1) + 1, false)")
        except Exception:
            pg_conn.rollback()
    pg_conn.commit()

    log("  Reference data complete. (FK checks still disabled for migration steps)")
    return currency_map


# ============================================================================
# HELPERS
# ============================================================================

def parse_simple_array(val):
    if not val or val == "":
        return []
    return [x.strip() for x in str(val).split(",") if x.strip()]


def parse_coordinate(coord_bytes):
    if coord_bytes is None:
        return None
    try:
        if isinstance(coord_bytes, (bytes, bytearray)) and len(coord_bytes) >= 25:
            x = struct.unpack_from("<d", coord_bytes, 9)[0]
            y = struct.unpack_from("<d", coord_bytes, 17)[0]
            if x == 0 and y == 0:
                return None
            return f"{y},{x}"  # lat,lng
        return None
    except Exception:
        return None


def safe_str(val, max_len=255):
    if val is None:
        return None
    s = str(val).strip()
    return s[:max_len] if s else None


def safe_decimal(val, default=0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ============================================================================
# STEP 1: BUILD MATERIAL MAP FROM LOCAL PG
# ============================================================================

def build_material_map(mysql_cur, pg_cur, pg_conn):
    """Build old_material_id → {new_id, main_material_id, category_id, unit} map.
    Unmatched materials are auto-inserted into PG materials table."""
    log("Building material map...")

    # Get old materials
    mysql_cur.execute("""
        SELECT id, name_en, name_th FROM materials
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    old_materials = mysql_cur.fetchall()

    # Get new materials from local PG
    pg_cur.execute("""
        SELECT id, name_en, name_th, main_material_id, category_id,
               unit_name_en, unit_weight
        FROM materials
        WHERE is_active = TRUE AND deleted_date IS NULL
    """)
    new_materials = pg_cur.fetchall()

    new_by_name = {}
    for m in new_materials:
        name = (m["name_en"] or "").strip().lower()
        if name:
            new_by_name[name] = m

    # Get main_materials and their typical category (from materials table)
    pg_cur.execute("SELECT id, name_en FROM main_materials WHERE is_active = TRUE")
    main_mats = pg_cur.fetchall()
    # Find typical category_id for each main_material
    pg_cur.execute("""
        SELECT DISTINCT main_material_id, category_id
        FROM materials WHERE main_material_id IS NOT NULL AND category_id IS NOT NULL
    """)
    main_mat_category = {}
    for r in pg_cur.fetchall():
        main_mat_category[r["main_material_id"]] = r["category_id"]
    for mm in main_mats:
        mm["category_id"] = main_mat_category.get(mm["id"])

    # Keyword → category_id mapping for guessing
    category_keywords = {
        "electronic": 2, "e-waste": 2, "computer": 2, "telecommunication": 2,
        "hazardous": 5, "battery": 5, "bulb": 5, "spray": 5, "chemical": 5,
        "biohazard": 6, "bio-hazard": 6,
        "organic": 3, "food": 3, "plant": 3,
        "general": 4, "general waste": 4,
        "recyclable": 1, "recycle": 1,
        "plastic": 1, "glass": 1, "paper": 1, "metal": 1, "wood": 1,
        "rubber": 8, "construction": 7,
        "beverage carton": 1, "ubc": 1, "carton": 1,
        "polyal": 1, "pulp": 1, "starch": 3,
        "fire extinguisher": 5,
    }

    def guess_category(name_en):
        """Guess category_id from material name keywords."""
        name_lower = (name_en or "").lower()
        for keyword, cat_id in category_keywords.items():
            if keyword in name_lower:
                return cat_id
        return 4  # default: General Waste

    # Get next material ID
    pg_cur.execute("SELECT COALESCE(MAX(id), 0) as mx FROM materials")
    next_mat_id = pg_cur.fetchone()["mx"] + 1

    mat_map = {}
    matched = 0
    inserted = 0
    for om in old_materials:
        old_name = (om["name_en"] or "").strip().lower()
        if old_name in new_by_name:
            nm = new_by_name[old_name]
            mat_map[om["id"]] = {
                "new_id": nm["id"],
                "main_material_id": nm["main_material_id"],
                "category_id": nm["category_id"],
                "unit": nm["unit_name_en"] or "Kilogram",
            }
            matched += 1
        else:
            # Insert unmatched material into PG
            cat_id = guess_category(om["name_en"])
            # Find first main_material in this category
            main_mat_id = None
            for mm in main_mats:
                if mm["category_id"] == cat_id:
                    main_mat_id = mm["id"]
                    break
            if not main_mat_id and main_mats:
                main_mat_id = main_mats[0]["id"]

            pg_cur.execute("""
                INSERT INTO materials (
                    id, name_en, name_th, category_id, main_material_id,
                    tags, is_global, unit_name_en, unit_name_th,
                    is_active, created_date, updated_date
                ) VALUES (%s, %s, %s, %s, %s, '[]'::jsonb, TRUE, 'Kilogram', 'กิโลกรัม',
                          TRUE, NOW(), NOW())
                RETURNING id
            """, (next_mat_id, om["name_en"], om["name_th"], cat_id, main_mat_id))
            new_id = pg_cur.fetchone()["id"]

            mat_map[om["id"]] = {
                "new_id": new_id,
                "main_material_id": main_mat_id,
                "category_id": cat_id,
                "unit": "Kilogram",
            }
            # Also add to new_by_name so we don't insert duplicates
            new_by_name[old_name] = {
                "id": new_id, "name_en": om["name_en"],
                "main_material_id": main_mat_id, "category_id": cat_id,
                "unit_name_en": "Kilogram",
            }
            next_mat_id += 1
            inserted += 1

    pg_conn.commit()
    log(f"  Material map: {matched} matched, {inserted} auto-inserted, {len(old_materials)} total")
    return mat_map


# ============================================================================
# STEP 2: INSERT ORGANIZATIONS
# ============================================================================

def insert_organizations(mysql_cur, pg_cur, pg_conn):
    """Insert organizations + organization_info. Returns old_org_id → new_org_id map."""
    log("Inserting organizations...")

    mysql_cur.execute("""
        SELECT o.id, o.name, o.owner, o.country_id, o.currency_id,
               o.created_date, o.updated_date,
               o.organization_info AS old_info_id,
               oi.tax_id, oi.image_url
        FROM organization o
        LEFT JOIN organization_info oi ON o.organization_info = oi.id
        WHERE o.is_active = 1 AND o.deleted_date IS NULL
        ORDER BY o.id
    """)
    orgs = mysql_cur.fetchall()
    log(f"  Found {len(orgs)} legacy organizations to insert")

    org_map = {}  # old_org_id → new_org_id
    org_owner_map = {}  # new_org_id → old_owner_user_id (to update later)

    for org in orgs:
        # 1. Insert organization_info
        pg_cur.execute("""
            INSERT INTO organization_info (
                tax_id, profile_image_url, company_name,
                created_date, updated_date, is_active,
                migration_id
            ) VALUES (%s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id
        """, (
            safe_str(org["tax_id"], 50),
            safe_str(org["image_url"]),
            safe_str(org["name"]),
            org["created_date"],
            org["updated_date"],
            org.get("old_info_id"),
        ))
        new_info_id = pg_cur.fetchone()["id"]

        # 2. Insert organization
        pg_cur.execute("""
            INSERT INTO organizations (
                name, organization_info_id,
                created_date, updated_date, is_active,
                migration_id
            ) VALUES (%s, %s, %s, %s, TRUE, %s)
            RETURNING id
        """, (
            safe_str(org["name"]),
            new_info_id,
            org["created_date"],
            org["updated_date"],
            org["id"],
        ))
        new_org_id = pg_cur.fetchone()["id"]
        org_map[org["id"]] = new_org_id

        if org["owner"]:
            org_owner_map[new_org_id] = org["owner"]

        # 3. Create default organization_roles
        for role in DEFAULT_ORG_ROLES:
            pg_cur.execute("""
                INSERT INTO organization_roles (
                    organization_id, key, name, description, is_system,
                    created_date, updated_date, is_active
                ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), TRUE)
            """, (new_org_id, role["key"], role["name"], role["description"], role["is_system"]))

    pg_conn.commit()
    log(f"  Inserted {len(org_map)} organizations (with info + roles)")
    return org_map, org_owner_map


# ============================================================================
# STEP 3: INSERT USERS AS user_locations (is_user=True)
# ============================================================================

def insert_users(mysql_cur, pg_cur, pg_conn, org_map, currency_map):
    """Insert legacy users → user_locations. Returns old_user_id → new_ul_id map."""
    log("Inserting users as user_locations (is_user=True)...")

    mysql_cur.execute("""
        SELECT u.*,
            ui.display_name, ui.profile_image_url, ui.account_type,
            ui.company_name, ui.company_phone, ui.company_email,
            ui.use_purpose, ui.business_type, ui.business_industry,
            ui.business_sub_industry, ui.tax_id AS ui_tax_id,
            ui.national_id AS ui_national_id,
            ui.national_card_image AS ui_national_card_image,
            ui.business_registration_certificate AS ui_brc,
            ui.address AS ui_address,
            ui.province_id AS ui_province_id,
            ui.district_id AS ui_district_id,
            ui.subdistrict_id AS ui_subdistrict_id,
            ui.country_id AS ui_country_id,
            ui.phone_number AS ui_phone_number,
            ui.phone_code AS ui_phone_code,
            ui.nationality AS ui_nationality,
            ui.footprint AS ui_footprint,
            ui.materials AS ui_materials
        FROM users u
        LEFT JOIN user_info ui ON u.user_info = ui.id
        WHERE u.is_active = 1 AND u.deleted_date IS NULL
        ORDER BY u.id
    """)
    users = mysql_cur.fetchall()
    log(f"  Found {len(users)} legacy users")

    platform_map = {
        "gepp_business_web": "GEPP_BUSINESS_WEB",
        "gepp_epr_web": "GEPP_EPR_WEB",
        "gepp_reward_app": "GEPP_REWARD_APP",
        "gepp_backoffice": "ADMIN_WEB",
        "main_backend": "API",
        "admin_web": "ADMIN_WEB",
        "user_trial": "WEB",
        "user_paid": "WEB",
        "n/a": "NA",
    }

    user_map = {}  # old_user_id → new_ul_id
    batch = []
    count = 0

    for u in users:
        old_platform = (u.get("platform") or "n/a").strip()
        new_platform = platform_map.get(old_platform, "BUSINESS")
        new_org_id = org_map.get(u.get("organization"))
        sub_users = parse_simple_array(u.get("sub_users"))

        row = (
            True,   # is_user
            False,  # is_location
            safe_str(u.get("firstname")),   # first_name
            safe_str(u.get("lastname")),    # last_name
            None,  # name_th
            f"{u.get('firstname') or ''} {u.get('lastname') or ''}".strip() or None,  # name_en
            safe_str(u.get("display_name")) or "GEPP User",  # display_name
            safe_str(u.get("email")),
            bool(u.get("is_email_active")),
            safe_str(u.get("email_notification")),
            safe_str(u.get("phone")),
            safe_str(u.get("username")),
            safe_str(u.get("password")),
            safe_str(u.get("facebook_id")),
            safe_str(u.get("apple_id")),
            safe_str(u.get("google_id_gmail")),
            new_platform,
            None,  # coordinate
            safe_str(u.get("ui_address")),
            None,  # postal_code
            u.get("ui_country_id") or u.get("country_id") or 212,
            u.get("ui_province_id"),
            u.get("ui_district_id"),
            u.get("ui_subdistrict_id"),
            safe_str(u.get("business_type")),
            safe_str(u.get("business_industry")),
            safe_str(u.get("business_sub_industry")),
            safe_str(u.get("company_name")),
            safe_str(u.get("company_phone")),
            safe_str(u.get("company_email")),
            safe_str(u.get("ui_tax_id")),
            None,  # functions
            None,  # type
            None,  # population
            safe_str(u.get("ui_materials")),  # material
            safe_str(u.get("profile_image_url")),
            safe_str(u.get("ui_national_id")),
            safe_str(u.get("ui_national_card_image")),
            safe_str(u.get("ui_brc")),
            new_org_id,
            u.get("locale") or "TH",
            u.get("ui_nationality"),
            currency_map.get(u.get("currency_id"), 12),
            u.get("ui_phone_code"),
            safe_str(u.get("note")),
            u.get("expired_date"),
            safe_decimal(u.get("ui_footprint")),
            json.dumps(sub_users) if sub_users else None,
            u.get("created_date"),
            u.get("updated_date"),
            u["id"],  # store old_id temporarily for mapping
        )
        batch.append(row)

        if len(batch) >= BATCH_SIZE:
            inserted = _insert_user_batch(pg_cur, batch)
            for old_id, new_id in inserted:
                user_map[old_id] = new_id
            count += len(batch)
            batch = []

    if batch:
        inserted = _insert_user_batch(pg_cur, batch)
        for old_id, new_id in inserted:
            user_map[old_id] = new_id
        count += len(batch)

    pg_conn.commit()
    log(f"  Inserted {count} users as user_locations")
    return user_map


def _insert_user_batch(pg_cur, batch):
    """Insert a batch of users and return list of (old_id, new_id)."""
    results = []
    for row in batch:
        old_id = row[-1]
        vals = row  # keep old_id at end as migration_id
        pg_cur.execute("""
            INSERT INTO user_locations (
                is_user, is_location,
                first_name, last_name, name_th, name_en, display_name,
                email, is_email_active, email_notification,
                phone, username, password,
                facebook_id, apple_id, google_id_gmail,
                platform,
                coordinate, address, postal_code,
                country_id, province_id, district_id, subdistrict_id,
                business_type, business_industry, business_sub_industry,
                company_name, company_phone, company_email, tax_id,
                functions, type, population, material,
                profile_image_url, national_id, national_card_image,
                business_registration_certificate,
                organization_id,
                locale, nationality_id, currency_id, phone_code_id,
                note, expired_date, footprint,
                sub_users,
                created_date, updated_date, is_active,
                migration_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, TRUE,
                %s
            )
            RETURNING id
        """, vals)
        new_id = pg_cur.fetchone()["id"]
        results.append((old_id, new_id))
    return results


# ============================================================================
# STEP 4: INSERT BUSINESS UNITS AS user_locations (is_location=True)
# ============================================================================

def insert_business_units(mysql_cur, pg_cur, pg_conn, org_map, user_map):
    """Insert business_units → user_locations. Returns old_bu_id → new_ul_id map."""
    log("Inserting business_units as user_locations (is_location=True)...")

    mysql_cur.execute("""
        SELECT * FROM business_units
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY id
    """)
    bus = mysql_cur.fetchall()

    # Get images
    mysql_cur.execute("""
        SELECT * FROM business_unit_images
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    bu_images = defaultdict(list)
    for img in mysql_cur.fetchall():
        bu_images[img["business_unit_id"]].append(img["image_url"])

    log(f"  Found {len(bus)} legacy business_units")

    bu_map = {}  # old_bu_id → new_ul_id
    count = 0

    for bu in bus:
        new_org_id = org_map.get(bu.get("organization"))
        coord = parse_coordinate(bu.get("coordinate"))
        images = bu_images.get(bu["id"], [])
        created_by_new = user_map.get(bu.get("created_id"))
        auditor_new = user_map.get(bu.get("auditor_id"))
        user_ids = parse_simple_array(bu.get("user"))

        # Members: map old user IDs to new
        members = []
        for uid_str in user_ids:
            try:
                uid = int(uid_str)
                new_uid = user_map.get(uid)
                if new_uid:
                    members.append({"user_id": new_uid, "role": "member"})
            except (ValueError, TypeError):
                pass

        pg_cur.execute("""
            INSERT INTO user_locations (
                is_user, is_location,
                name_th, name_en, display_name,
                email, is_email_active, phone,
                platform,
                coordinate, address, postal_code,
                country_id, province_id, district_id, subdistrict_id,
                functions, type, population, material,
                profile_image_url,
                organization_id,
                created_by_id, auditor_id,
                members, note,
                created_date, updated_date, is_active,
                migration_id
            ) VALUES (
                FALSE, TRUE,
                %s, %s, %s,
                %s, FALSE, %s,
                'GEPP_BUSINESS_WEB',
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s,
                %s,
                %s, %s,
                %s, %s,
                %s, %s, TRUE,
                %s
            )
            RETURNING id
        """, (
            safe_str(bu.get("name_th")),
            safe_str(bu.get("name_en")),
            safe_str(bu.get("name_en")) or safe_str(bu.get("name_th")),
            safe_str(bu.get("email")),
            safe_str(bu.get("phone")),
            coord,
            safe_str(bu.get("address")),
            safe_str(bu.get("postal_code"), 10),
            bu.get("country_id") or 212,
            bu.get("province_id"),
            bu.get("district_id"),
            bu.get("subdistrict_id"),
            safe_str(bu.get("functions")),
            safe_str(bu.get("type")),
            safe_str(bu.get("population")),
            safe_str(bu.get("material")),
            images[0] if images else None,
            new_org_id,
            created_by_new,
            auditor_new,
            json.dumps(members) if members else None,
            safe_str(bu.get("note")),
            bu.get("created_date"),
            bu.get("updated_date"),
            bu["id"],  # migration_id = old business_unit id
        ))
        new_id = pg_cur.fetchone()["id"]
        bu_map[bu["id"]] = new_id
        count += 1

        if count % BATCH_SIZE == 0:
            pg_conn.commit()
            log(f"    ... inserted {count} business_units")

    pg_conn.commit()
    log(f"  Inserted {count} business_units as user_locations")
    return bu_map


# ============================================================================
# STEP 5: UPDATE ORGANIZATION OWNERS
# ============================================================================

def update_org_owners(pg_cur, pg_conn, org_owner_map, user_map):
    """Set organization.owner_id using user_map."""
    log("Updating organization owners...")
    updated = 0
    for new_org_id, old_owner_id in org_owner_map.items():
        new_owner_id = user_map.get(old_owner_id)
        if new_owner_id:
            pg_cur.execute("""
                UPDATE organizations SET owner_id = %s WHERE id = %s
            """, (new_owner_id, new_org_id))
            updated += 1

    pg_conn.commit()
    log(f"  Updated {updated}/{len(org_owner_map)} organization owners")


# ============================================================================
# STEP 6: INSERT TRANSACTIONS
# ============================================================================

def insert_transactions(mysql_cur, pg_cur, pg_conn, org_map, bu_map, user_map):
    """Insert transactions. Returns old_tx_id → new_tx_id map."""
    log("Inserting transactions...")

    mysql_cur.execute("""
        SELECT * FROM transactions
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY id
    """)
    txs = mysql_cur.fetchall()

    # Get transaction images
    mysql_cur.execute("""
        SELECT * FROM transaction_images
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    tx_images = defaultdict(list)
    for img in mysql_cur.fetchall():
        tx_images[img["transaction_id"]].append(img["image_url"])

    log(f"  Found {len(txs)} legacy transactions")

    status_map = {"pending": "pending", "approved": "approved", "rejected": "rejected", "completed": "completed"}

    tx_map = {}  # old_tx_id → new_tx_id
    tx_created_by_map = {}  # old_tx_id → new_created_by_id
    tx_date_map = {}  # old_tx_id → transaction_date
    count = 0
    skipped = 0

    for tx in txs:
        new_org_id = org_map.get(tx.get("organization"))
        if not new_org_id:
            skipped += 1
            continue

        bu_id = tx.get("business-unit")
        new_origin_id = bu_map.get(bu_id)
        new_created_by = user_map.get(tx.get("created_id"))

        images = tx_images.get(tx["id"], [])
        images_json = json.dumps(images) if images else "[]"

        coord = parse_coordinate(tx.get("coordinate"))
        origin_coords = None
        if coord:
            parts = coord.split(",")
            if len(parts) == 2:
                try:
                    origin_coords = json.dumps({"lat": float(parts[0]), "lng": float(parts[1])})
                except ValueError:
                    pass

        status = status_map.get(tx.get("status"), "pending")

        pg_cur.execute("""
            INSERT INTO transactions (
                status, transaction_method,
                organization_id, origin_id,
                weight_kg, total_amount,
                transaction_date, notes, images,
                origin_coordinates,
                created_by_id,
                location_tag_id,
                created_date, updated_date, is_active,
                transaction_records, destination_ids,
                migration_id
            ) VALUES (
                %s, 'origin',
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s,
                %s,
                %s,
                %s, %s, TRUE,
                '{}'::bigint[], '{}'::bigint[],
                %s
            )
            RETURNING id
        """, (
            status,
            new_org_id,
            new_origin_id,
            safe_decimal(tx.get("total_quantity")),
            0,  # total_amount (will be calculated from records)
            tx.get("transaction_date"),
            safe_str(tx.get("note")),
            images_json,
            origin_coords,
            new_created_by,
            None,  # location_tag_id - needs separate mapping if needed
            tx.get("created_date"),
            tx.get("updated_date"),
            tx["id"],  # migration_id = old transaction id
        ))
        new_tx_id = pg_cur.fetchone()["id"]
        tx_map[tx["id"]] = new_tx_id
        if new_created_by:
            tx_created_by_map[tx["id"]] = new_created_by
        tx_date_map[tx["id"]] = tx.get("transaction_date")
        count += 1

        if count % BATCH_SIZE == 0:
            pg_conn.commit()
            log(f"    ... inserted {count} transactions")

    pg_conn.commit()
    log(f"  Inserted {count} transactions (skipped {skipped} with missing org)")
    return tx_map, tx_created_by_map, tx_date_map


# ============================================================================
# STEP 7: INSERT TRANSACTION RECORDS
# ============================================================================

def insert_transaction_records(mysql_cur, pg_cur, pg_conn, tx_map, bu_map, user_map, mat_map, tx_created_by_map, tx_date_map):
    """Insert transaction records. Update transactions arrays.
    tx_created_by_map: old_tx_id → new_created_by_id (from transactions)."""
    log("Inserting transaction_records...")

    mysql_cur.execute("""
        SELECT * FROM transaction_records
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY transaction_id, journey_id, id
    """)
    records = mysql_cur.fetchall()
    log(f"  Records to process: {len(records)}")

    # Get record images
    mysql_cur.execute("""
        SELECT * FROM transaction_record_images
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    rec_images = defaultdict(list)
    for img in mysql_cur.fetchall():
        rec_images[img["transaction_record_id"]].append(img["image_url"])

    status_map = {"pending": "pending", "approved": "approved", "rejected": "rejected", "completed": "completed"}

    # Track: new_tx_id → list of (new_rec_id, new_dest_id)
    tx_records_map = defaultdict(list)
    count = 0
    skipped_tx = 0
    skipped_mat = 0

    for rec in records:
        old_tx_id = rec.get("transaction_id")
        new_tx_id = tx_map.get(old_tx_id)
        if not new_tx_id:
            skipped_tx += 1
            continue

        old_mat_id = rec.get("material")
        mat_info = mat_map.get(old_mat_id)
        if not mat_info:
            skipped_mat += 1
            continue

        new_dest_id = bu_map.get(rec.get("destination_business-unit"))
        # Get created_by from parent transaction (records don't have their own created_id)
        new_created_by = tx_created_by_map.get(old_tx_id)

        images = rec_images.get(rec["id"], [])
        images_json = json.dumps(images) if images else "[]"

        qty = abs(safe_decimal(rec.get("quantity")))
        price = abs(safe_decimal(rec.get("price")))
        total = qty * price

        status = status_map.get(rec.get("status"), "pending")

        pg_cur.execute("""
            INSERT INTO transaction_records (
                is_active, status,
                created_transaction_id, traceability,
                transaction_type,
                material_id, main_material_id, category_id,
                tags, unit,
                origin_quantity, origin_weight_kg,
                origin_price_per_unit, total_amount,
                currency_id,
                notes, images,
                hazardous_level,
                destination_id,
                created_by_id,
                transaction_date,
                created_date, updated_date,
                migration_id
            ) VALUES (
                TRUE, %s,
                %s, '{}'::bigint[],
                'manual_input',
                %s, %s, %s,
                '[]'::jsonb, %s,
                %s, %s,
                %s, %s,
                12,
                %s, %s,
                0,
                %s,
                %s,
                %s,
                %s, %s,
                %s
            )
            RETURNING id
        """, (
            status,
            new_tx_id,
            mat_info["new_id"],
            mat_info["main_material_id"],
            mat_info["category_id"],
            mat_info["unit"],
            qty,
            qty,  # weight_kg = quantity (assuming kg)
            price,
            total,
            safe_str(rec.get("note")),
            images_json,
            new_dest_id,
            new_created_by or list(user_map.values())[0],  # fallback to first migrated user
            tx_date_map.get(old_tx_id) or rec.get("transaction_date"),  # use parent tx date
            rec.get("created_date"),
            rec.get("updated_date"),
            rec["id"],  # migration_id = old transaction_record id
        ))
        new_rec_id = pg_cur.fetchone()["id"]
        tx_records_map[new_tx_id].append((new_rec_id, new_dest_id))
        count += 1

        if count % BATCH_SIZE == 0:
            pg_conn.commit()
            log(f"    ... inserted {count} records")

    pg_conn.commit()
    log(f"  Inserted {count} records (skipped: {skipped_tx} no tx, {skipped_mat} no material)")

    # Update transactions with record arrays and destination arrays
    log("  Updating transactions.transaction_records & destination_ids arrays...")
    updated = 0
    update_errors = 0
    for new_tx_id, rec_list in tx_records_map.items():
        rec_ids = [r[0] for r in rec_list]
        dest_ids = [r[1] for r in rec_list]

        try:
            # Calculate total_amount for transaction (cap to avoid overflow)
            pg_cur.execute("""
                SELECT COALESCE(SUM(total_amount), 0) as total,
                       COALESCE(SUM(origin_weight_kg), 0) as weight
                FROM transaction_records
                WHERE created_transaction_id = %s AND is_active = TRUE
            """, (new_tx_id,))
            totals = pg_cur.fetchone()
            total_amt = min(float(totals["total"]), 99999.9999)
            weight = min(float(totals["weight"]), 99999.9999)

            pg_cur.execute("""
                UPDATE transactions
                SET transaction_records = %s,
                    destination_ids = %s,
                    total_amount = %s,
                    weight_kg = %s
                WHERE id = %s
            """, (rec_ids, dest_ids, total_amt, weight, new_tx_id))
            updated += 1
        except Exception:
            pg_conn.rollback()
            # Fallback: just set arrays without totals
            pg_cur.execute("""
                UPDATE transactions
                SET transaction_records = %s,
                    destination_ids = %s
                WHERE id = %s
            """, (rec_ids, dest_ids, new_tx_id))
            updated += 1
            update_errors += 1

        if updated % BATCH_SIZE == 0:
            pg_conn.commit()

    pg_conn.commit()
    log(f"  Updated {updated} transactions with record/destination arrays ({update_errors} overflow errors, arrays-only)")

    return tx_records_map


# ============================================================================
# STEP 8: RESET SEQUENCES
# ============================================================================

def reset_sequences(pg_cur, pg_conn):
    """Reset auto-increment sequences to max(id) + 1."""
    log("Resetting sequences...")
    tables = [
        ("organizations", "organizations_id_seq"),
        ("organization_info", "organization_info_id_seq"),
        ("user_locations", "user_locations_id_seq"),
        ("transactions", "transactions_id_seq"),
        ("transaction_records", "transaction_records_id_seq"),
        ("organization_roles", "organization_roles_id_seq"),
    ]
    for table, seq in tables:
        pg_cur.execute(f"SELECT COALESCE(MAX(id), 0) + 1 AS next_val FROM {table}")
        next_val = pg_cur.fetchone()["next_val"]
        pg_cur.execute(f"SELECT setval('{seq}', {next_val}, false)")
        log(f"  {seq} → {next_val}")

    pg_conn.commit()


# ============================================================================
# STEP 9: SAVE ID MAPPINGS
# ============================================================================

def save_mappings(org_map, user_map, bu_map, tx_map, mat_map):
    """Save all ID mappings to a JSON file for reference."""
    mappings = {
        "generated_at": datetime.now().isoformat(),
        "org_map": {str(k): v for k, v in org_map.items()},
        "user_map": {str(k): v for k, v in user_map.items()},
        "bu_map": {str(k): v for k, v in bu_map.items()},
        "tx_map": {str(k): v for k, v in tx_map.items()},
        "material_map": {str(k): v for k, v in mat_map.items()},
        "counts": {
            "organizations": len(org_map),
            "users": len(user_map),
            "business_units": len(bu_map),
            "transactions": len(tx_map),
        },
    }
    with open("migration_id_mappings.json", "w") as f:
        json.dump(mappings, f, indent=2)
    log("  Saved ID mappings to migration_id_mappings.json")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 80)
    print("GEPP LEGACY → LOCAL PG MIGRATION INSERT")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 80)
    print(f"Source: MySQL {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")
    print(f"Target: PostgreSQL {LOCAL_PG_CONFIG['host']}:{LOCAL_PG_CONFIG['port']}/{LOCAL_PG_CONFIG['dbname']}")
    print()

    # Connect
    log("Connecting to MySQL...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()

    log("Connecting to local PostgreSQL...")
    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Step 0: Copy all reference data (locations from MySQL, materials from remote PG)
        from pathlib import Path
        env_path = Path(__file__).parent / "backend" / "migrations" / ".env"
        remote_cfg = {}
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    remote_cfg[k.strip()] = v.strip()
        remote_pg_config = {
            "host": remote_cfg["DB_HOST"], "port": int(remote_cfg.get("DB_PORT", 5432)),
            "dbname": remote_cfg["DB_NAME"], "user": remote_cfg["DB_USER"], "password": remote_cfg["DB_PASSWORD"],
        }
        currency_map = copy_reference_data(mysql_cur, pg_cur, pg_conn, remote_pg_config)

        # Step 1: Material map
        mat_map = build_material_map(mysql_cur, pg_cur, pg_conn)

        # Step 2: Organizations
        org_map, org_owner_map = insert_organizations(mysql_cur, pg_cur, pg_conn)

        # Step 3: Users
        user_map = insert_users(mysql_cur, pg_cur, pg_conn, org_map, currency_map)

        # Step 4: Business Units
        bu_map = insert_business_units(mysql_cur, pg_cur, pg_conn, org_map, user_map)

        # Step 5: Update org owners
        update_org_owners(pg_cur, pg_conn, org_owner_map, user_map)

        # Step 6: Transactions
        tx_map, tx_created_by_map, tx_date_map = insert_transactions(mysql_cur, pg_cur, pg_conn, org_map, bu_map, user_map)

        # Step 7: Transaction Records + update tx arrays
        insert_transaction_records(mysql_cur, pg_cur, pg_conn, tx_map, bu_map, user_map, mat_map, tx_created_by_map, tx_date_map)

        # Step 8: Re-enable FK checks + Reset sequences
        pg_cur.execute("SET session_replication_role = 'origin'")
        pg_conn.commit()
        log("FK checks re-enabled.")
        reset_sequences(pg_cur, pg_conn)

        # Step 9: Save mappings
        save_mappings(org_map, user_map, bu_map, tx_map, mat_map)

        # Summary
        print()
        print("=" * 80)
        print("MIGRATION COMPLETE")
        print("=" * 80)
        print(f"  Organizations inserted:      {len(org_map)}")
        print(f"  Users (user_locations):       {len(user_map)}")
        print(f"  BusinessUnits (user_locs):    {len(bu_map)}")
        print(f"  Transactions:                 {len(tx_map)}")
        print(f"  Material matches used:        {len(mat_map)}")
        print(f"  ID mappings: migration_id_mappings.json")
        print(f"  Finished: {datetime.now().isoformat()}")

    except Exception as e:
        pg_conn.rollback()
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        mysql_cur.close()
        mysql_conn.close()
        pg_cur.close()
        pg_conn.close()
        log("Connections closed.")


if __name__ == "__main__":
    main()
