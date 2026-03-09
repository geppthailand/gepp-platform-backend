#!/usr/bin/env python3
"""
Legacy Database Migration Script
=================================
Extracts data from legacy MySQL (Gepp_new) and validates/maps it
to the new PostgreSQL schema (backend/GEPPPlatform).

Legacy MySQL: localhost:3306, root, Gepp_new
New PostgreSQL: from backend/migrations/.env

Key mappings:
- organization + organization_info → organizations + organization_info
- users + user_info → user_locations (is_user=True)
- business_units → user_locations (is_location=True)
- transactions → transactions (new schema)
- transaction_records → transaction_records (deduplicated by transaction_id+journey_id, first only)
- transaction_images → transactions.images (JSONB)
- transaction_record_images → transaction_records.images (JSONB)
- materials matched by name_en
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

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

# Load PostgreSQL config from backend/migrations/.env
def load_pg_config():
    env_path = Path(__file__).parent / "backend" / "migrations" / ".env"
    config = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                config[key.strip()] = val.strip()
    return {
        "host": config["DB_HOST"],
        "port": int(config.get("DB_PORT", 5432)),
        "dbname": config["DB_NAME"],
        "user": config["DB_USER"],
        "password": config["DB_PASSWORD"],
    }


PG_CONFIG = load_pg_config()


# ============================================================================
# HELPERS
# ============================================================================

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return super().default(obj)


def fmt(val):
    """Format value for display."""
    if val is None:
        return "NULL"
    if isinstance(val, str) and len(val) > 60:
        return val[:60] + "..."
    return str(val)


def parse_simple_array(val):
    """Parse TypeORM simple-array (comma-separated string) into list."""
    if not val or val == "":
        return []
    return [x.strip() for x in str(val).split(",") if x.strip()]


def parse_coordinate(coord_bytes):
    """Parse MySQL geometry point to lat,lng string."""
    if coord_bytes is None:
        return None
    try:
        # MySQL geometry is WKB with 4-byte SRID prefix
        import struct
        if isinstance(coord_bytes, (bytes, bytearray)) and len(coord_bytes) >= 25:
            # Skip SRID (4 bytes), byte order (1 byte), type (4 bytes)
            x = struct.unpack_from("<d", coord_bytes, 9)[0]
            y = struct.unpack_from("<d", coord_bytes, 17)[0]
            if x == 0 and y == 0:
                return None
            return f"{y},{x}"  # lat,lng
        return None
    except Exception:
        return None


# ============================================================================
# EXTRACTION FROM LEGACY MYSQL
# ============================================================================

def extract_legacy_data(mysql_conn):
    """Extract all relevant data from legacy MySQL database."""
    cursor = mysql_conn.cursor()
    data = {}

    print("=" * 80)
    print("PHASE 1: EXTRACTING DATA FROM LEGACY MySQL (Gepp_new)")
    print("=" * 80)

    # --- Organizations ---
    print("\n[1/12] Extracting organizations...")
    cursor.execute("""
        SELECT o.*, oi.tax_id AS info_tax_id, oi.image_url AS info_image_url
        FROM organization o
        LEFT JOIN organization_info oi ON o.organization_info = oi.id
        WHERE o.is_active = 1 AND o.deleted_date IS NULL
        ORDER BY o.id
    """)
    data["organizations"] = cursor.fetchall()
    print(f"  Found {len(data['organizations'])} active organizations")

    # --- Organization Info ---
    print("\n[2/12] Extracting organization_info...")
    cursor.execute("""
        SELECT * FROM organization_info
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    data["organization_info"] = cursor.fetchall()
    print(f"  Found {len(data['organization_info'])} organization_info records")

    # --- Users + User Info ---
    print("\n[3/12] Extracting users with user_info...")
    cursor.execute("""
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
            ui.materials AS ui_materials,
            ui.application_date AS ui_application_date,
            ui.project_id AS ui_project_id
        FROM users u
        LEFT JOIN user_info ui ON u.user_info = ui.id
        WHERE u.is_active = 1 AND u.deleted_date IS NULL
        ORDER BY u.id
    """)
    data["users"] = cursor.fetchall()
    print(f"  Found {len(data['users'])} active users")

    # --- Business Units ---
    print("\n[4/12] Extracting business_units...")
    cursor.execute("""
        SELECT * FROM business_units
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY id
    """)
    data["business_units"] = cursor.fetchall()
    print(f"  Found {len(data['business_units'])} active business_units")

    # --- Business Unit Images ---
    print("\n[5/12] Extracting business_unit_images...")
    cursor.execute("""
        SELECT * FROM business_unit_images
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    data["business_unit_images"] = cursor.fetchall()
    print(f"  Found {len(data['business_unit_images'])} business_unit_images")

    # --- Business Unit Types ---
    print("\n[6/12] Extracting business_unit_types...")
    cursor.execute("""
        SELECT * FROM business_unit_types
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    data["business_unit_types"] = cursor.fetchall()
    print(f"  Found {len(data['business_unit_types'])} business_unit_types")

    # --- Business Groups ---
    print("\n[7/12] Extracting business_groups...")
    cursor.execute("""
        SELECT * FROM business_groups
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY id
    """)
    data["business_groups"] = cursor.fetchall()
    print(f"  Found {len(data['business_groups'])} business_groups")

    # --- Materials ---
    print("\n[8/12] Extracting materials...")
    cursor.execute("""
        SELECT m.*, mc.name_en AS cat_name_en, mc.name_th AS cat_name_th
        FROM materials m
        LEFT JOIN material_categories mc ON m.material_category_id = mc.id
        WHERE m.is_active = 1 AND m.deleted_date IS NULL
        ORDER BY m.id
    """)
    data["materials"] = cursor.fetchall()
    print(f"  Found {len(data['materials'])} active materials")

    # --- Transactions ---
    print("\n[9/12] Extracting transactions...")
    cursor.execute("""
        SELECT * FROM transactions
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY id
    """)
    data["transactions"] = cursor.fetchall()
    print(f"  Found {len(data['transactions'])} active transactions")

    # --- Transaction Images ---
    print("\n[10/12] Extracting transaction_images...")
    cursor.execute("""
        SELECT * FROM transaction_images
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    data["transaction_images"] = cursor.fetchall()
    print(f"  Found {len(data['transaction_images'])} transaction_images")

    # --- Transaction Records (deduplicate by transaction_id + journey_id) ---
    print("\n[11/12] Extracting transaction_records (deduplicating journey chains)...")
    cursor.execute("""
        SELECT * FROM transaction_records
        WHERE is_active = 1 AND deleted_date IS NULL
        ORDER BY transaction_id, journey_id, id
    """)
    all_records = cursor.fetchall()
    print(f"  Raw transaction_records: {len(all_records)}")

    # Deduplicate: for each (transaction_id, journey_id) keep only the first record
    seen = set()
    deduped_records = []
    duplicate_count = 0
    for rec in all_records:
        key = (rec["transaction_id"], rec.get("journey_id"))
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped_records.append(rec)
    data["transaction_records"] = deduped_records
    print(f"  After dedup (first per transaction_id+journey_id): {len(deduped_records)} "
          f"(removed {duplicate_count} journey-chain duplicates)")

    # --- Transaction Record Images ---
    print("\n[12/12] Extracting transaction_record_images...")
    cursor.execute("""
        SELECT * FROM transaction_record_images
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    data["transaction_record_images"] = cursor.fetchall()
    print(f"  Found {len(data['transaction_record_images'])} transaction_record_images")

    # --- Transaction Types ---
    print("\n[Bonus] Extracting transaction_types...")
    cursor.execute("SELECT * FROM transaction_types WHERE is_active = 1")
    data["transaction_types"] = cursor.fetchall()
    print(f"  Found {len(data['transaction_types'])} transaction_types")

    # --- Location Tags ---
    print("\n[Bonus] Extracting location_tags...")
    cursor.execute("""
        SELECT * FROM location_tags
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    data["location_tags"] = cursor.fetchall()
    print(f"  Found {len(data['location_tags'])} location_tags")

    return data


# ============================================================================
# EXTRACT NEW DATABASE DATA FOR COMPARISON
# ============================================================================

def extract_new_data(pg_conn):
    """Extract reference data from the new PostgreSQL database."""
    cursor = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    data = {}

    print("\n" + "=" * 80)
    print("PHASE 2: EXTRACTING DATA FROM NEW PostgreSQL FOR COMPARISON")
    print("=" * 80)

    # --- Materials (new) ---
    print("\n[1/5] Extracting new materials...")
    cursor.execute("""
        SELECT m.id, m.name_en, m.name_th, m.category_id, m.main_material_id,
               m.unit_name_en, m.unit_name_th, m.unit_weight, m.color, m.calc_ghg,
               m.is_global, m.organization_id
        FROM materials m
        WHERE m.is_active = TRUE AND m.deleted_date IS NULL
        ORDER BY m.id
    """)
    data["materials"] = cursor.fetchall()
    print(f"  Found {len(data['materials'])} new materials")

    # --- Main Materials ---
    print("\n[2/5] Extracting new main_materials...")
    cursor.execute("""
        SELECT id, name_en, name_th, code, color
        FROM main_materials
        WHERE is_active = TRUE AND deleted_date IS NULL
        ORDER BY id
    """)
    data["main_materials"] = cursor.fetchall()
    print(f"  Found {len(data['main_materials'])} new main_materials")

    # --- Material Categories ---
    print("\n[3/5] Extracting new material_categories...")
    cursor.execute("""
        SELECT id, name_en, name_th, code, color
        FROM material_categories
        WHERE is_active = TRUE AND deleted_date IS NULL
        ORDER BY id
    """)
    data["material_categories"] = cursor.fetchall()
    print(f"  Found {len(data['material_categories'])} new material_categories")

    # --- Existing Organizations ---
    print("\n[4/5] Extracting existing organizations in new DB...")
    cursor.execute("""
        SELECT o.id, o.name, o.owner_id, o.organization_info_id,
               oi.company_name, oi.tax_id, oi.company_email
        FROM organizations o
        LEFT JOIN organization_info oi ON o.organization_info_id = oi.id
        WHERE o.is_active = TRUE AND o.deleted_date IS NULL
        ORDER BY o.id
    """)
    data["organizations"] = cursor.fetchall()
    print(f"  Found {len(data['organizations'])} existing organizations")

    # --- Existing User Locations ---
    print("\n[5/5] Extracting existing user_locations in new DB...")
    cursor.execute("""
        SELECT id, email, first_name, last_name, name_en, name_th,
               is_user, is_location, organization_id, platform
        FROM user_locations
        WHERE is_active = TRUE AND deleted_date IS NULL
        ORDER BY id
    """)
    data["user_locations"] = cursor.fetchall()
    print(f"  Found {len(data['user_locations'])} existing user_locations")

    return data


# ============================================================================
# MATERIAL MATCHING
# ============================================================================

def validate_materials(legacy_data, new_data):
    """Match legacy materials with new materials by name_en."""
    print("\n" + "=" * 80)
    print("PHASE 3: MATERIAL MATCHING (name_en)")
    print("=" * 80)

    old_materials = legacy_data["materials"]
    new_materials = new_data["materials"]

    # Build name_en lookup for new materials
    new_by_name = {}
    for m in new_materials:
        name = (m["name_en"] or "").strip().lower()
        if name:
            new_by_name[name] = m

    material_map = {}  # old_id -> new_id
    matched = []
    unmatched_old = []
    unmatched_new_names = set(new_by_name.keys())

    for om in old_materials:
        old_name = (om["name_en"] or "").strip().lower()
        if old_name in new_by_name:
            nm = new_by_name[old_name]
            material_map[om["id"]] = nm["id"]
            matched.append((om, nm))
            unmatched_new_names.discard(old_name)
        else:
            unmatched_old.append(om)

    print(f"\n  Matched materials: {len(matched)}")
    print(f"  Unmatched OLD materials (no new equivalent): {len(unmatched_old)}")
    print(f"  Unmatched NEW materials (no old equivalent): {len(unmatched_new_names)}")

    if matched:
        print(f"\n  --- Matched Materials (sample, max 20) ---")
        print(f"  {'Old ID':<8} {'New ID':<8} {'name_en':<40} {'Old Price':<12} {'New Unit'}")
        print(f"  {'-'*8} {'-'*8} {'-'*40} {'-'*12} {'-'*15}")
        for om, nm in matched[:20]:
            print(f"  {om['id']:<8} {nm['id']:<8} {(om['name_en'] or '')[:40]:<40} "
                  f"{om.get('price', 0):<12} {nm.get('unit_name_en', 'N/A')}")

    if unmatched_old:
        print(f"\n  --- Unmatched OLD Materials (need manual mapping) ---")
        for om in unmatched_old[:30]:
            print(f"    OLD ID={om['id']}: name_en='{om.get('name_en', '')}', "
                  f"name_th='{om.get('name_th', '')}', cat='{om.get('cat_name_en', '')}'")

    if unmatched_new_names:
        print(f"\n  --- Unmatched NEW Materials (not in legacy) ---")
        for name in sorted(unmatched_new_names)[:30]:
            nm = new_by_name[name]
            print(f"    NEW ID={nm['id']}: name_en='{nm.get('name_en', '')}'")

    return material_map


# ============================================================================
# SCHEMA MAPPING & VALIDATION
# ============================================================================

def map_and_validate(legacy_data, new_data, material_map):
    """Map legacy data to new schema and validate compatibility."""
    print("\n" + "=" * 80)
    print("PHASE 4: SCHEMA MAPPING & COMPATIBILITY VALIDATION")
    print("=" * 80)

    # Build lookup indexes
    legacy_users_by_id = {u["id"]: u for u in legacy_data["users"]}
    legacy_bu_by_id = {bu["id"]: bu for bu in legacy_data["business_units"]}
    legacy_orgs_by_id = {o["id"]: o for o in legacy_data["organizations"]}

    # Images grouped by parent
    bu_images_by_bu = defaultdict(list)
    for img in legacy_data["business_unit_images"]:
        bu_images_by_bu[img["business_unit_id"]].append(img)

    tx_images_by_tx = defaultdict(list)
    for img in legacy_data["transaction_images"]:
        tx_images_by_tx[img["transaction_id"]].append(img)

    tr_images_by_tr = defaultdict(list)
    for img in legacy_data["transaction_record_images"]:
        tr_images_by_tr[img["transaction_record_id"]].append(img)

    # New DB existing data lookups
    new_emails = set()
    for ul in new_data["user_locations"]:
        if ul.get("email"):
            new_emails.add(ul["email"].lower().strip())

    new_org_names = set()
    for org in new_data["organizations"]:
        if org.get("name"):
            new_org_names.add(org["name"].lower().strip())

    issues = []
    warnings = []

    # -----------------------------------------------------------------------
    # A) MAP ORGANIZATIONS
    # -----------------------------------------------------------------------
    print("\n--- A) Organization Mapping ---")
    org_mappings = []
    for org in legacy_data["organizations"]:
        org_name = (org.get("name") or "").strip()
        owner_id = org.get("owner")
        owner = legacy_users_by_id.get(owner_id) if owner_id else None

        new_org = {
            "legacy_id": org["id"],
            "name": org_name,
            "description": None,
            "owner_email": owner.get("email") if owner else None,
            "owner_legacy_id": owner_id,
            "info_tax_id": org.get("info_tax_id"),
            "info_image_url": org.get("info_image_url"),
            "country_id": org.get("country_id", 212),
            "currency_id": org.get("currency_id", 12),
            "created_date": org.get("created_date"),
        }

        # Check for conflict with existing new DB orgs
        if org_name.lower().strip() in new_org_names:
            warnings.append(f"Organization '{org_name}' (legacy ID={org['id']}) already exists in new DB")

        org_mappings.append(new_org)

    print(f"  Organizations to migrate: {len(org_mappings)}")

    # -----------------------------------------------------------------------
    # B) MAP USERS → user_locations (is_user=True)
    # -----------------------------------------------------------------------
    print("\n--- B) Users → user_locations (is_user=True) ---")
    user_mappings = []
    email_conflicts = 0
    for u in legacy_data["users"]:
        email = (u.get("email") or "").strip()

        # Map platform enum
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
        old_platform = (u.get("platform") or "n/a").strip()
        new_platform = platform_map.get(old_platform, "NA")

        ul = {
            "legacy_user_id": u["id"],
            "legacy_org_id": u.get("organization"),
            "is_user": True,
            "is_location": False,
            # Name fields
            "first_name": u.get("firstname"),
            "last_name": u.get("lastname"),
            "display_name": u.get("display_name") or "GEPP User",
            "name_en": f"{u.get('firstname') or ''} {u.get('lastname') or ''}".strip() or None,
            "name_th": None,
            # Auth
            "email": email or None,
            "username": u.get("username"),
            "password": u.get("password"),
            "is_email_active": bool(u.get("is_email_active")),
            "email_notification": u.get("email_notification"),
            "phone": u.get("phone"),
            "facebook_id": u.get("facebook_id"),
            "apple_id": u.get("apple_id"),
            "google_id_gmail": u.get("google_id_gmail"),
            # Platform
            "platform": new_platform,
            "locale": u.get("locale", "TH"),
            # User info fields
            "profile_image_url": u.get("profile_image_url"),
            "account_type": u.get("account_type"),
            "company_name": u.get("company_name"),
            "company_phone": u.get("company_phone"),
            "company_email": u.get("company_email"),
            "business_type": u.get("business_type"),
            "business_industry": u.get("business_industry"),
            "business_sub_industry": u.get("business_sub_industry"),
            "tax_id": u.get("ui_tax_id"),
            "national_id": u.get("ui_national_id"),
            "national_card_image": u.get("ui_national_card_image"),
            "business_registration_certificate": u.get("ui_brc"),
            "address": u.get("ui_address"),
            "province_id": u.get("ui_province_id"),
            "district_id": u.get("ui_district_id"),
            "subdistrict_id": u.get("ui_subdistrict_id"),
            "country_id": u.get("ui_country_id") or u.get("country_id", 212),
            "currency_id": u.get("currency_id", 12),
            "phone_code_id": u.get("ui_phone_code"),
            "nationality_id": u.get("ui_nationality"),
            "footprint": u.get("ui_footprint"),
            "note": u.get("note"),
            "expired_date": u.get("expired_date"),
            "sub_users": parse_simple_array(u.get("sub_users")),
            "material": u.get("ui_materials"),
            "created_date": u.get("created_date"),
        }

        if email and email.lower() in new_emails:
            email_conflicts += 1
            warnings.append(f"User email '{email}' (legacy ID={u['id']}) already exists in new DB")

        user_mappings.append(ul)

    print(f"  Users to migrate: {len(user_mappings)}")
    print(f"  Email conflicts with new DB: {email_conflicts}")

    # -----------------------------------------------------------------------
    # C) MAP BUSINESS UNITS → user_locations (is_location=True)
    # -----------------------------------------------------------------------
    print("\n--- C) Business Units → user_locations (is_location=True) ---")
    location_mappings = []
    for bu in legacy_data["business_units"]:
        coord = parse_coordinate(bu.get("coordinate"))
        images = bu_images_by_bu.get(bu["id"], [])
        image_urls = [img["image_url"] for img in images if img.get("image_url")]

        ul = {
            "legacy_bu_id": bu["id"],
            "legacy_org_id": bu.get("organization"),
            "is_user": False,
            "is_location": True,
            # Name
            "name_th": bu.get("name_th"),
            "name_en": bu.get("name_en"),
            "display_name": bu.get("name_en") or bu.get("name_th"),
            # Location
            "coordinate": coord,
            "address": bu.get("address"),
            "email": bu.get("email"),
            "phone": bu.get("phone"),
            "postal_code": bu.get("postal_code"),
            "province_id": bu.get("province_id"),
            "district_id": bu.get("district_id"),
            "subdistrict_id": bu.get("subdistrict_id"),
            "country_id": bu.get("country_id", 212),
            # Business
            "functions": bu.get("functions"),
            "type": bu.get("type"),
            "population": bu.get("population"),
            "material": bu.get("material"),
            "note": bu.get("note"),
            "platform": "GEPP_BUSINESS_WEB",
            # Relationships
            "created_by_legacy_id": bu.get("created_id"),
            "auditor_legacy_id": bu.get("auditor_id"),
            "belong_to_user_legacy_id": bu.get("belong_to_user"),
            "user_ids": parse_simple_array(bu.get("user")),
            # Images (will be stored as profile_image_url or can be tracked separately)
            "images": image_urls,
            "profile_image_url": image_urls[0] if image_urls else None,
            "created_date": bu.get("created_date"),
        }
        location_mappings.append(ul)

    print(f"  Business units to migrate as locations: {len(location_mappings)}")

    # -----------------------------------------------------------------------
    # D) MAP TRANSACTIONS
    # -----------------------------------------------------------------------
    print("\n--- D) Transactions Mapping ---")

    # Status mapping
    status_map = {
        "pending": "pending",
        "approved": "approved",
        "rejected": "rejected",
        "completed": "completed",
    }

    transaction_mappings = []
    tx_missing_org = 0
    tx_missing_bu = 0
    tx_missing_material_count = 0

    for tx in legacy_data["transactions"]:
        bu_id = tx.get("business-unit")
        bu = legacy_bu_by_id.get(bu_id) if bu_id else None

        # Collect images for this transaction
        images = tx_images_by_tx.get(tx["id"], [])
        image_urls = [img["image_url"] for img in images if img.get("image_url")]

        # Parse coordinate
        coord = parse_coordinate(tx.get("coordinate"))
        origin_coords = None
        if coord:
            parts = coord.split(",")
            if len(parts) == 2:
                origin_coords = {"lat": float(parts[0]), "lng": float(parts[1])}

        new_tx = {
            "legacy_tx_id": tx["id"],
            "legacy_org_id": tx.get("organization"),
            "legacy_bu_id": bu_id,
            "status": status_map.get(tx.get("status"), "pending"),
            "transaction_method": "origin",
            "origin_legacy_bu_id": bu_id,
            "notes": tx.get("note"),
            "transaction_date": tx.get("transaction_date"),
            "weight_kg": float(tx.get("total_quantity") or 0),
            "images": json.dumps(image_urls, cls=DecimalEncoder),
            "origin_coordinates": json.dumps(origin_coords) if origin_coords else None,
            "created_by_legacy_user_id": tx.get("created_id"),
            "invoice_no": tx.get("invoice_no"),
            "location_tag_id": tx.get("location_tag_id"),
            "created_date": tx.get("created_date"),
            # Will be filled after mapping records
            "transaction_record_ids": [],
            "destination_ids": [],
        }

        if not tx.get("organization"):
            tx_missing_org += 1
            issues.append(f"Transaction ID={tx['id']} has no organization")
        if not bu_id:
            tx_missing_bu += 1

        transaction_mappings.append(new_tx)

    print(f"  Transactions to migrate: {len(transaction_mappings)}")
    if tx_missing_org:
        print(f"  WARNING: {tx_missing_org} transactions missing organization")
    if tx_missing_bu:
        print(f"  WARNING: {tx_missing_bu} transactions missing business-unit (origin)")

    # -----------------------------------------------------------------------
    # E) MAP TRANSACTION RECORDS (already deduplicated)
    # -----------------------------------------------------------------------
    print("\n--- E) Transaction Records Mapping ---")

    record_mappings = []
    material_match_ok = 0
    material_match_fail = 0
    records_by_tx = defaultdict(list)

    for rec in legacy_data["transaction_records"]:
        old_material_id = rec.get("material")
        new_material_id = material_map.get(old_material_id)

        if new_material_id:
            material_match_ok += 1
        else:
            material_match_fail += 1
            issues.append(
                f"TransactionRecord ID={rec['id']} has material_id={old_material_id} "
                f"with no match in new DB"
            )

        # Collect images
        images = tr_images_by_tr.get(rec["id"], [])
        image_urls = [img["image_url"] for img in images if img.get("image_url")]

        new_rec = {
            "legacy_tr_id": rec["id"],
            "legacy_tx_id": rec.get("transaction_id"),
            "legacy_journey_id": rec.get("journey_id"),
            "status": status_map.get(rec.get("status"), "pending"),
            "transaction_type": "manual_input",
            # Material
            "legacy_material_id": old_material_id,
            "new_material_id": new_material_id,
            # Quantity
            "origin_quantity": float(rec.get("quantity") or 0),
            "origin_weight_kg": float(rec.get("quantity") or 0),
            "origin_price_per_unit": float(rec.get("price") or 0),
            "total_amount": float((rec.get("quantity") or 0) * (rec.get("price") or 0)),
            # Locations
            "origin_legacy_bu_id": rec.get("origin_business-unit"),
            "destination_legacy_bu_id": rec.get("destination_business-unit"),
            # Other
            "notes": rec.get("note"),
            "transaction_date": rec.get("transaction_date"),
            "images": json.dumps(image_urls, cls=DecimalEncoder),
            "off_site": bool(rec.get("off_site")),
            "elimination_approach": rec.get("elimination_approach"),
            "created_date": rec.get("created_date"),
        }
        record_mappings.append(new_rec)
        records_by_tx[rec.get("transaction_id")].append(new_rec)

    print(f"  Transaction records to migrate: {len(record_mappings)}")
    print(f"  Material matches: {material_match_ok} OK, {material_match_fail} FAILED")

    # Link records back to transactions
    for tx_map in transaction_mappings:
        tx_recs = records_by_tx.get(tx_map["legacy_tx_id"], [])
        tx_map["record_count"] = len(tx_recs)
        # Destination IDs (from records)
        dest_bu_ids = []
        for r in tx_recs:
            dest_id = r.get("destination_legacy_bu_id")
            dest_bu_ids.append(dest_id)
        tx_map["destination_legacy_bu_ids"] = dest_bu_ids

    # -----------------------------------------------------------------------
    # F) BUSINESS GROUPS → Organizational Hierarchy
    # -----------------------------------------------------------------------
    print("\n--- F) Business Groups → Org Hierarchy ---")
    bg_mappings = []
    for bg in legacy_data["business_groups"]:
        bg_map = {
            "legacy_bg_id": bg["id"],
            "legacy_org_id": bg.get("organization"),
            "name_th": bg.get("name_th"),
            "name_en": bg.get("name_en"),
            "is_root": bool(bg.get("is_root")),
            "sub_groups": parse_simple_array(bg.get("business-group")),
            "business_units": parse_simple_array(bg.get("business-unit")),
            "users": parse_simple_array(bg.get("user")),
            "note": bg.get("note"),
            "created_by_legacy_id": bg.get("created_by_id"),
        }
        bg_mappings.append(bg_map)

    print(f"  Business groups: {len(bg_mappings)}")
    root_groups = [bg for bg in bg_mappings if bg["is_root"]]
    print(f"  Root groups: {len(root_groups)}")

    # -----------------------------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------------------------
    results = {
        "org_mappings": org_mappings,
        "user_mappings": user_mappings,
        "location_mappings": location_mappings,
        "transaction_mappings": transaction_mappings,
        "record_mappings": record_mappings,
        "bg_mappings": bg_mappings,
        "material_map": material_map,
        "issues": issues,
        "warnings": warnings,
    }

    return results


# ============================================================================
# CROSS-VALIDATION
# ============================================================================

def cross_validate(results, legacy_data, new_data):
    """Perform deep cross-validation between mapped data."""
    print("\n" + "=" * 80)
    print("PHASE 5: CROSS-VALIDATION")
    print("=" * 80)

    issues = results["issues"]
    warnings = results["warnings"]

    # --- A) Organization-User consistency ---
    print("\n--- A) Organization-User Consistency ---")
    user_org_ids = set(u["legacy_org_id"] for u in results["user_mappings"] if u["legacy_org_id"])
    org_ids = set(o["legacy_id"] for o in results["org_mappings"])
    orphan_users = user_org_ids - org_ids
    if orphan_users:
        warnings.append(f"Users reference {len(orphan_users)} organizations not in active orgs: {orphan_users}")
        print(f"  WARNING: {len(orphan_users)} org IDs referenced by users but not in active orgs")
    else:
        print(f"  OK: All user org references are valid")

    # --- B) Location-Organization consistency ---
    print("\n--- B) Location-Organization Consistency ---")
    loc_org_ids = set(l["legacy_org_id"] for l in results["location_mappings"] if l["legacy_org_id"])
    orphan_locs = loc_org_ids - org_ids
    if orphan_locs:
        warnings.append(f"Locations reference {len(orphan_locs)} orgs not in active orgs: {orphan_locs}")
        print(f"  WARNING: {len(orphan_locs)} org IDs referenced by locations but not in active orgs")
    else:
        print(f"  OK: All location org references are valid")

    # --- C) Transaction-Organization consistency ---
    print("\n--- C) Transaction-Organization Consistency ---")
    tx_org_ids = set(t["legacy_org_id"] for t in results["transaction_mappings"] if t["legacy_org_id"])
    orphan_txs = tx_org_ids - org_ids
    if orphan_txs:
        warnings.append(f"Transactions reference {len(orphan_txs)} orgs not in active orgs")
        print(f"  WARNING: {len(orphan_txs)} org IDs referenced by transactions not in active orgs")
    else:
        print(f"  OK: All transaction org references are valid")

    # --- D) Transaction Record → Business Unit references ---
    print("\n--- D) Transaction Record → Business Unit References ---")
    bu_ids = set(l["legacy_bu_id"] for l in results["location_mappings"])
    missing_origin = 0
    missing_dest = 0
    for rec in results["record_mappings"]:
        if rec["origin_legacy_bu_id"] and rec["origin_legacy_bu_id"] not in bu_ids:
            missing_origin += 1
        if rec["destination_legacy_bu_id"] and rec["destination_legacy_bu_id"] not in bu_ids:
            missing_dest += 1
    if missing_origin or missing_dest:
        print(f"  WARNING: {missing_origin} records have missing origin BU, "
              f"{missing_dest} have missing destination BU")
    else:
        print(f"  OK: All record BU references found")

    # --- E) Transaction → Business Unit references ---
    print("\n--- E) Transaction → Business Unit (origin) References ---")
    tx_missing_bu = sum(1 for t in results["transaction_mappings"]
                        if t["legacy_bu_id"] and t["legacy_bu_id"] not in bu_ids)
    if tx_missing_bu:
        print(f"  WARNING: {tx_missing_bu} transactions reference missing business units")
    else:
        print(f"  OK: All transaction BU references found")

    # --- F) Material quantity/price sanity ---
    print("\n--- F) Transaction Record Quantity/Price Sanity ---")
    zero_qty = sum(1 for r in results["record_mappings"] if r["origin_quantity"] == 0)
    negative_qty = sum(1 for r in results["record_mappings"] if r["origin_quantity"] < 0)
    negative_price = sum(1 for r in results["record_mappings"] if r["origin_price_per_unit"] < 0)
    print(f"  Records with zero quantity: {zero_qty}")
    print(f"  Records with negative quantity: {negative_qty}")
    print(f"  Records with negative price: {negative_price}")
    if negative_qty:
        issues.append(f"{negative_qty} transaction records have negative quantity")
    if negative_price:
        issues.append(f"{negative_price} transaction records have negative price")

    # --- G) Duplicate email check within legacy users ---
    print("\n--- G) Duplicate Emails in Legacy Users ---")
    email_counts = defaultdict(list)
    for u in results["user_mappings"]:
        if u["email"]:
            email_counts[u["email"].lower().strip()].append(u["legacy_user_id"])
    dupes = {e: ids for e, ids in email_counts.items() if len(ids) > 1}
    if dupes:
        print(f"  WARNING: {len(dupes)} duplicate email addresses found:")
        for email, ids in list(dupes.items())[:10]:
            print(f"    '{email}' → user IDs: {ids}")
    else:
        print(f"  OK: No duplicate emails in legacy users")

    # --- H) Organization owner exists as user ---
    print("\n--- H) Organization Owner Validation ---")
    user_ids = set(u["legacy_user_id"] for u in results["user_mappings"])
    missing_owners = []
    for org in results["org_mappings"]:
        if org["owner_legacy_id"] and org["owner_legacy_id"] not in user_ids:
            missing_owners.append(org)
    if missing_owners:
        print(f"  WARNING: {len(missing_owners)} orgs have owners not in active users")
        for o in missing_owners[:5]:
            print(f"    Org '{o['name']}' (ID={o['legacy_id']}) owner_id={o['owner_legacy_id']}")
    else:
        print(f"  OK: All organization owners are active users")

    return issues, warnings


# ============================================================================
# GENERATE ID MAPPING PLAN
# ============================================================================

def generate_id_mapping_plan(results):
    """Generate a plan for how IDs will be mapped during actual migration."""
    print("\n" + "=" * 80)
    print("PHASE 6: ID MAPPING PLAN (for actual migration)")
    print("=" * 80)

    print("""
    During actual migration, IDs will be mapped as follows:

    1. ORGANIZATIONS:
       - INSERT into organizations + organization_info
       - Store mapping: old_org_id → new_org_id

    2. USERS → user_locations (is_user=True):
       - INSERT into user_locations
       - Store mapping: old_user_id → new_user_location_id

    3. BUSINESS UNITS → user_locations (is_location=True):
       - INSERT into user_locations
       - Store mapping: old_bu_id → new_user_location_id

    4. UPDATE organization.owner_id using user_id mapping

    5. TRANSACTIONS:
       - Map organization using org_id mapping
       - Map origin_id (business-unit) using bu_id mapping
       - INSERT into transactions
       - Store mapping: old_tx_id → new_tx_id

    6. TRANSACTION RECORDS:
       - Map material_id using material_map
       - Map destination_id using bu_id mapping
       - INSERT into transaction_records
       - UPDATE transactions.transaction_records array
       - UPDATE transactions.destination_ids array

    7. BUSINESS GROUPS → organization_setup / parent_location_id hierarchy
       - Build tree from business_groups
       - Set parent_location_id on user_locations
       - Generate organization_setup JSON
    """)


# ============================================================================
# GENERATE MIGRATION SQL PREVIEW
# ============================================================================

def generate_migration_preview(results, output_file="migration_preview.json"):
    """Save a JSON preview of all mapped data for review."""
    print("\n" + "=" * 80)
    print(f"PHASE 7: SAVING MIGRATION PREVIEW → {output_file}")
    print("=" * 80)

    preview = {
        "summary": {
            "organizations": len(results["org_mappings"]),
            "users_as_user_locations": len(results["user_mappings"]),
            "business_units_as_user_locations": len(results["location_mappings"]),
            "transactions": len(results["transaction_mappings"]),
            "transaction_records": len(results["record_mappings"]),
            "business_groups": len(results["bg_mappings"]),
            "material_matches": len(results["material_map"]),
        },
        "material_map": {str(k): v for k, v in results["material_map"].items()},
        "issues": results["issues"],
        "warnings": results["warnings"],
        # Sample data (first 5 of each)
        "sample_organizations": results["org_mappings"][:5],
        "sample_users": results["user_mappings"][:5],
        "sample_locations": results["location_mappings"][:5],
        "sample_transactions": results["transaction_mappings"][:5],
        "sample_records": results["record_mappings"][:5],
        "sample_business_groups": results["bg_mappings"][:5],
    }

    output_path = Path(__file__).parent / output_file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(preview, f, indent=2, cls=DecimalEncoder, ensure_ascii=False)

    print(f"  Preview saved to: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")


# ============================================================================
# PER-ORGANIZATION BREAKDOWN
# ============================================================================

def per_org_breakdown(results):
    """Show migration data breakdown per organization."""
    print("\n" + "=" * 80)
    print("PHASE 8: PER-ORGANIZATION BREAKDOWN")
    print("=" * 80)

    org_stats = defaultdict(lambda: {
        "name": "Unknown",
        "users": 0,
        "locations": 0,
        "transactions": 0,
        "records": 0,
        "business_groups": 0,
    })

    for o in results["org_mappings"]:
        org_stats[o["legacy_id"]]["name"] = o["name"]

    for u in results["user_mappings"]:
        oid = u.get("legacy_org_id")
        if oid:
            org_stats[oid]["users"] += 1

    for l in results["location_mappings"]:
        oid = l.get("legacy_org_id")
        if oid:
            org_stats[oid]["locations"] += 1

    for t in results["transaction_mappings"]:
        oid = t.get("legacy_org_id")
        if oid:
            org_stats[oid]["transactions"] += 1

    for r in results["record_mappings"]:
        # Get org from transaction
        tx_id = r.get("legacy_tx_id")
        # We'll count through transactions instead
        pass

    for bg in results["bg_mappings"]:
        oid = bg.get("legacy_org_id")
        if oid:
            org_stats[oid]["business_groups"] += 1

    # Sort by transaction count desc
    sorted_orgs = sorted(org_stats.items(), key=lambda x: x[1]["transactions"], reverse=True)

    print(f"\n  {'Org ID':<8} {'Name':<30} {'Users':<8} {'Locs':<8} {'Txns':<10} {'BGroups':<8}")
    print(f"  {'-'*8} {'-'*30} {'-'*8} {'-'*8} {'-'*10} {'-'*8}")
    for oid, stats in sorted_orgs[:30]:
        print(f"  {oid:<8} {stats['name'][:30]:<30} {stats['users']:<8} "
              f"{stats['locations']:<8} {stats['transactions']:<10} {stats['business_groups']:<8}")

    if len(sorted_orgs) > 30:
        print(f"  ... and {len(sorted_orgs) - 30} more organizations")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 80)
    print("GEPP LEGACY → NEW PLATFORM MIGRATION TOOL")
    print(f"Run at: {datetime.now().isoformat()}")
    print("=" * 80)
    print(f"\nMySQL (legacy): {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")
    print(f"PostgreSQL (new): {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")

    # Connect to MySQL
    print("\nConnecting to MySQL...")
    try:
        mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        print("  MySQL connected OK")
    except Exception as e:
        print(f"  ERROR connecting to MySQL: {e}")
        sys.exit(1)

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print("  PostgreSQL connected OK")
    except Exception as e:
        print(f"  ERROR connecting to PostgreSQL: {e}")
        sys.exit(1)

    try:
        # Phase 1: Extract legacy data
        legacy_data = extract_legacy_data(mysql_conn)

        # Phase 2: Extract new data for comparison
        new_data = extract_new_data(pg_conn)

        # Phase 3: Material matching
        material_map = validate_materials(legacy_data, new_data)

        # Phase 4: Map and validate schema compatibility
        results = map_and_validate(legacy_data, new_data, material_map)

        # Phase 5: Cross-validation
        issues, warnings = cross_validate(results, legacy_data, new_data)

        # Phase 6: ID mapping plan
        generate_id_mapping_plan(results)

        # Phase 7: Save preview
        generate_migration_preview(results)

        # Phase 8: Per-org breakdown
        per_org_breakdown(results)

        # Final report
        print("\n" + "=" * 80)
        print("FINAL MIGRATION READINESS REPORT")
        print("=" * 80)
        print(f"\n  Total Organizations:       {len(results['org_mappings'])}")
        print(f"  Total Users → UserLocs:    {len(results['user_mappings'])}")
        print(f"  Total BUs → UserLocs:      {len(results['location_mappings'])}")
        print(f"  Total Transactions:        {len(results['transaction_mappings'])}")
        print(f"  Total TransactionRecords:  {len(results['record_mappings'])}")
        print(f"  Total BusinessGroups:      {len(results['bg_mappings'])}")
        print(f"  Material Matches:          {len(material_map)}")

        print(f"\n  Issues (blocking): {len(issues)}")
        for i, issue in enumerate(issues[:20]):
            print(f"    [{i+1}] {issue}")
        if len(issues) > 20:
            print(f"    ... and {len(issues) - 20} more issues")

        print(f"\n  Warnings (non-blocking): {len(warnings)}")
        for i, warn in enumerate(warnings[:20]):
            print(f"    [{i+1}] {warn}")
        if len(warnings) > 20:
            print(f"    ... and {len(warnings) - 20} more warnings")

        if not issues:
            print("\n  STATUS: READY FOR MIGRATION (no blocking issues)")
        else:
            print(f"\n  STATUS: {len(issues)} BLOCKING ISSUES NEED RESOLUTION")

    finally:
        mysql_conn.close()
        pg_conn.close()
        print("\nDatabase connections closed.")


if __name__ == "__main__":
    main()
