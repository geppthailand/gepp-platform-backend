#!/usr/bin/env python3
"""
Organization Structure Migration Script
========================================
Reads a CSV structure file (e.g., org_structures/117.csv) and:
1. Creates new user_locations for 'new:' entries (branches) and 'mig:' entries (floors from location_tags)
2. Builds nested JSON tree for organization_setup.root_nodes
3. Populates hub_node with non-wastemaker user_locations (destinations)
4. Inserts/updates organization_setup row
5. Migrates location_tag_id from legacy MySQL transactions to new PostgreSQL transactions

Usage:
    python migrate_org_structure.py 117.csv
    python migrate_org_structure.py 117.csv --dry-run
"""

import csv
import json
import os
import sys
from datetime import datetime

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

# ============================================================================
# HELPERS
# ============================================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def parse_csv_entry(cell):
    """
    Parse a CSV cell into (entry_type, entry_id, entry_name).

    Formats:
      new:{name}           → ('new', None, name)
      mig:{tag_id}:{name}  → ('mig', tag_id, name)
      {ul_id}:{name}       → ('existing', ul_id, name)
    """
    cell = cell.strip()
    if not cell:
        return None

    if cell.startswith("new:"):
        name = cell[4:]
        return ("new", None, name)
    elif cell.startswith("mig:"):
        parts = cell[4:].split(":", 1)
        tag_id = int(parts[0])
        name = parts[1] if len(parts) > 1 else ""
        return ("mig", tag_id, name)
    else:
        # existing: {ul_id}:{name}
        parts = cell.split(":", 1)
        ul_id = int(parts[0])
        name = parts[1] if len(parts) > 1 else ""
        return ("existing", ul_id, name)


def get_org_id_from_filename(csv_filename):
    """Extract org_id from filename like '117.csv' → 117"""
    basename = os.path.basename(csv_filename)
    name_part = os.path.splitext(basename)[0]
    return int(name_part)


def get_legacy_org_id(pg_cur, org_id):
    """Get the legacy MySQL org_id from migration_id on the organizations table."""
    pg_cur.execute(
        "SELECT migration_id FROM organizations WHERE id = %s",
        (org_id,)
    )
    row = pg_cur.fetchone()
    if row and row.get("migration_id"):
        return int(row["migration_id"])
    return None


def get_legacy_org_id_from_mappings(org_id):
    """Fallback: load from migration_id_mappings.json"""
    mappings_path = os.path.join(os.path.dirname(__file__), "migration_id_mappings.json")
    if not os.path.exists(mappings_path):
        return None
    with open(mappings_path) as f:
        data = json.load(f)
    org_map = data.get("org_map", {})
    # org_map is {legacy_id: new_id}, we need reverse
    for legacy_id, new_id in org_map.items():
        if new_id == org_id:
            return int(legacy_id)
    return None


# ============================================================================
# STEP 1: PARSE CSV INTO TREE STRUCTURE
# ============================================================================

def parse_csv_structure(csv_path):
    """
    Parse the CSV hierarchy file into a list of branch structures.

    Returns:
        [
            {
                "entry": ("new", None, "UOB Plaza Bangkok Branch"),
                "buildings": [
                    {
                        "entry": ("existing", 9682, "UOB Plaza Bangkok"),
                        "floors": [
                            {
                                "entry": ("mig", 156, "ชั้น 1 (UOB PZ)"),
                                "rooms": [...]
                            },
                            ...
                        ]
                    },
                    ...
                ]
            },
            ...
        ]
    """
    branches = []
    current_branch = None
    current_building = None
    current_floor = None

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header

        for row_num, row in enumerate(reader, start=2):
            # Pad row to 4 columns
            while len(row) < 4:
                row.append("")

            branch_cell, building_cell, floor_cell, room_cell = row

            if branch_cell.strip():
                entry = parse_csv_entry(branch_cell)
                if entry:
                    current_branch = {"entry": entry, "buildings": []}
                    branches.append(current_branch)
                    current_building = None
                    current_floor = None

            elif building_cell.strip():
                entry = parse_csv_entry(building_cell)
                if entry and current_branch:
                    current_building = {"entry": entry, "floors": []}
                    current_branch["buildings"].append(current_building)
                    current_floor = None

            elif floor_cell.strip():
                entry = parse_csv_entry(floor_cell)
                if entry and current_building:
                    current_floor = {"entry": entry, "rooms": []}
                    current_building["floors"].append(current_floor)

            elif room_cell.strip():
                entry = parse_csv_entry(room_cell)
                if entry and current_floor:
                    current_floor["rooms"].append({"entry": entry})

    return branches


# ============================================================================
# STEP 2: CREATE USER_LOCATIONS FOR NEW AND MIG ENTRIES
# ============================================================================

def create_user_locations(pg_cur, pg_conn, org_id, branches, mysql_cur, dry_run=False):
    """
    Create user_locations for 'new:' (branches) and 'mig:' (floors from location_tags).
    Sets parent_location_id for hierarchy: branch → building → floor → room.

    Returns:
        tag_id_map: {legacy_tag_id: new_user_location_id}  (for transaction migration)
        node_tree: resolved tree with actual IDs for all nodes
    """
    tag_id_map = {}  # legacy location_tag_id → new user_location_id

    # Pre-fetch location_tag data from MySQL for mig entries
    mig_tag_ids = []
    for branch in branches:
        for building in branch["buildings"]:
            for floor in building["floors"]:
                etype, eid, ename = floor["entry"]
                if etype == "mig":
                    mig_tag_ids.append(eid)
                for room in floor.get("rooms", []):
                    etype, eid, ename = room["entry"]
                    if etype == "mig":
                        mig_tag_ids.append(eid)

    tag_data = {}
    if mig_tag_ids and mysql_cur:
        placeholders = ",".join(["%s"] * len(mig_tag_ids))
        mysql_cur.execute(f"""
            SELECT id, name_th, name_en, business_unit, is_active, is_root,
                   start_date, end_date, note
            FROM location_tags
            WHERE id IN ({placeholders})
        """, mig_tag_ids)
        for row in mysql_cur.fetchall():
            tag_data[row["id"]] = row

    log(f"  Pre-fetched {len(tag_data)} location_tags from MySQL")

    # Pre-fetch existing user_locations for this org (for duplicate detection)
    pg_cur.execute("""
        SELECT id, name_th, name_en, migration_id
        FROM user_locations
        WHERE organization_id = %s
          AND is_active = TRUE
          AND deleted_date IS NULL
    """, (org_id,))
    existing_by_name = {}   # name_th → {id, name_th, name_en, migration_id}
    existing_by_mig_id = {} # migration_id → {id, ...}
    for row in pg_cur.fetchall():
        if row["name_th"]:
            existing_by_name[row["name_th"].strip()] = row
        if row["migration_id"]:
            existing_by_mig_id[int(row["migration_id"])] = row

    log(f"  Pre-fetched {len(existing_by_name)} existing user_locations for duplicate check")

    def find_existing(name_th, name_en, migration_id=None):
        """Check if a user_location already exists by migration_id or name_th/name_en."""
        # First check by migration_id (most precise for mig: entries)
        if migration_id and migration_id in existing_by_mig_id:
            return existing_by_mig_id[migration_id]
        # Then check by name_th
        if name_th and name_th.strip() in existing_by_name:
            return existing_by_name[name_th.strip()]
        # Then check by name_en
        if name_en and name_en.strip() in existing_by_name:
            return existing_by_name[name_en.strip()]
        return None

    def create_single_location(entry, parent_id, level_name):
        """Create a single user_location and return its new ID."""
        etype, eid, ename = entry

        if etype == "existing":
            # Already exists - just update parent_location_id if needed
            if not dry_run and parent_id:
                pg_cur.execute("""
                    UPDATE user_locations
                    SET parent_location_id = %s
                    WHERE id = %s AND (parent_location_id IS NULL OR parent_location_id != %s)
                """, (parent_id, eid, parent_id))
            log(f"    [existing] {level_name} id={eid} name={ename} parent={parent_id}")
            return eid

        elif etype == "new":
            # Check if already exists by name
            found = find_existing(ename, ename)
            if found:
                found_id = found["id"]
                # Update parent if needed
                if not dry_run and parent_id:
                    pg_cur.execute("""
                        UPDATE user_locations
                        SET parent_location_id = %s
                        WHERE id = %s AND (parent_location_id IS NULL OR parent_location_id != %s)
                    """, (parent_id, found_id, parent_id))
                log(f"    [already exists] {level_name} id={found_id} name={ename} parent={parent_id} — skipping create")
                return found_id

            if dry_run:
                log(f"    [DRY-RUN] Would create {level_name}: {ename} parent={parent_id}")
                return -1  # placeholder

            pg_cur.execute("""
                INSERT INTO user_locations (
                    is_user, is_location,
                    name_th, name_en, display_name,
                    functions, type,
                    organization_id, parent_location_id,
                    platform, is_active,
                    country_id, currency_id,
                    is_email_active
                ) VALUES (
                    FALSE, TRUE,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    'GEPP_BUSINESS_WEB', TRUE,
                    212, 12,
                    FALSE
                )
                RETURNING id
            """, (
                ename,  # name_th
                ename,  # name_en
                ename,  # display_name
                '["wastemaker"]',  # functions - branches contain origin buildings
                'branch',  # type
                org_id,
                parent_id,
            ))
            new_id = pg_cur.fetchone()["id"]
            # Add to cache so subsequent lookups find it
            existing_by_name[ename.strip()] = {"id": new_id, "name_th": ename, "name_en": ename, "migration_id": None}
            log(f"    [created] {level_name} id={new_id} name={ename} parent={parent_id}")
            return new_id

        elif etype == "mig":
            # Migrate from location_tag → new user_location (floor/room)
            legacy_tag = tag_data.get(eid, {})
            name_th = legacy_tag.get("name_th") or ename
            name_en = legacy_tag.get("name_en") or ename

            # Check if already migrated (by migration_id or name)
            found = find_existing(name_th, name_en, migration_id=eid)
            if found:
                found_id = found["id"]
                tag_id_map[eid] = found_id
                # Update parent if needed
                if not dry_run and parent_id:
                    pg_cur.execute("""
                        UPDATE user_locations
                        SET parent_location_id = %s
                        WHERE id = %s AND (parent_location_id IS NULL OR parent_location_id != %s)
                    """, (parent_id, found_id, parent_id))
                log(f"    [already exists] {level_name} id={found_id} tag_id={eid} name={name_th} parent={parent_id} — skipping create")
                return found_id

            if dry_run:
                log(f"    [DRY-RUN] Would migrate {level_name}: tag_id={eid} name={name_th} parent={parent_id}")
                return -1

            pg_cur.execute("""
                INSERT INTO user_locations (
                    is_user, is_location,
                    name_th, name_en, display_name,
                    functions, type,
                    organization_id, parent_location_id,
                    platform, is_active,
                    country_id, currency_id,
                    is_email_active,
                    migration_id
                ) VALUES (
                    FALSE, TRUE,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    'GEPP_BUSINESS_WEB', TRUE,
                    212, 12,
                    FALSE,
                    %s
                )
                RETURNING id
            """, (
                name_th,
                name_en,
                name_th,  # display_name
                '["wastemaker"]',  # floors are origin locations
                'floor',  # type
                org_id,
                parent_id,
                eid,  # migration_id = old location_tag.id
            ))
            new_id = pg_cur.fetchone()["id"]
            tag_id_map[eid] = new_id
            # Add to cache
            existing_by_name[name_th.strip()] = {"id": new_id, "name_th": name_th, "name_en": name_en, "migration_id": eid}
            existing_by_mig_id[eid] = {"id": new_id, "name_th": name_th, "name_en": name_en, "migration_id": eid}
            log(f"    [migrated] {level_name} id={new_id} tag_id={eid} name={name_th} parent={parent_id}")
            return new_id

    # Process the tree
    for branch in branches:
        branch_id = create_single_location(branch["entry"], None, "branch")
        branch["resolved_id"] = branch_id

        for building in branch["buildings"]:
            building_id = create_single_location(building["entry"], branch_id, "building")
            building["resolved_id"] = building_id

            for floor in building["floors"]:
                floor_id = create_single_location(floor["entry"], building_id, "floor")
                floor["resolved_id"] = floor_id

                for room in floor.get("rooms", []):
                    room_id = create_single_location(room["entry"], floor_id, "room")
                    room["resolved_id"] = room_id

    if not dry_run:
        pg_conn.commit()

    log(f"  Created/migrated locations. tag_id_map has {len(tag_id_map)} entries.")
    return tag_id_map, branches


# ============================================================================
# STEP 3: BUILD ROOT_NODES JSON TREE
# ============================================================================

def build_root_nodes(branches):
    """
    Build the nested root_nodes JSON structure:
    [
        {
            "nodeId": branch_id,
            "children": [
                {
                    "nodeId": building_id,
                    "children": [
                        {"nodeId": floor_id, "children": [
                            {"nodeId": room_id, "children": []}
                        ]}
                    ]
                }
            ]
        }
    ]
    """
    root_nodes = []

    for branch in branches:
        branch_node = {
            "nodeId": branch["resolved_id"],
            "children": []
        }

        for building in branch["buildings"]:
            building_node = {
                "nodeId": building["resolved_id"],
                "children": []
            }

            for floor in building["floors"]:
                floor_node = {
                    "nodeId": floor["resolved_id"],
                    "children": []
                }

                for room in floor.get("rooms", []):
                    room_node = {
                        "nodeId": room["resolved_id"],
                        "children": []
                    }
                    floor_node["children"].append(room_node)

                building_node["children"].append(floor_node)

            branch_node["children"].append(building_node)

        root_nodes.append(branch_node)

    return root_nodes


# ============================================================================
# STEP 4: BUILD HUB_NODE (non-wastemaker destinations)
# ============================================================================

def build_hub_node(pg_cur, org_id):
    """
    Build hub_node JSON with non-wastemaker user_locations.
    These are destination locations (collectors, recyclers, sorters, etc.).

    Returns: {"children": [{"nodeId": id}, ...]}
    """
    pg_cur.execute("""
        SELECT id, name_th, functions
        FROM user_locations
        WHERE organization_id = %s
          AND is_active = TRUE
          AND deleted_date IS NULL
          AND is_location = TRUE
          AND (functions IS NULL OR functions NOT LIKE '%%wastemaker%%')
          AND parent_location_id IS NULL
    """, (org_id,))

    children = []
    for row in pg_cur.fetchall():
        children.append({"nodeId": row["id"]})
        log(f"    [hub] id={row['id']} name={row['name_th']} functions={row['functions']}")

    return {"children": children}


# ============================================================================
# STEP 5: INSERT ORGANIZATION_SETUP
# ============================================================================

def insert_organization_setup(pg_cur, pg_conn, org_id, root_nodes, hub_node, dry_run=False):
    """
    Insert or update organization_setup for the given org_id.
    """
    root_nodes_json = json.dumps(root_nodes, ensure_ascii=False)
    hub_node_json = json.dumps(hub_node, ensure_ascii=False)

    metadata = {
        "migrated_at": datetime.now().isoformat(),
        "source": "migrate_org_structure.py",
        "version_notes": "Initial structure migration from legacy CSV"
    }
    metadata_json = json.dumps(metadata, ensure_ascii=False)

    if dry_run:
        log(f"  [DRY-RUN] Would insert organization_setup for org_id={org_id}")
        log(f"    root_nodes: {len(root_nodes)} branches")
        log(f"    hub_node: {len(hub_node)} destinations")
        return

    # Check if setup already exists
    pg_cur.execute(
        "SELECT id, version FROM organization_setup WHERE organization_id = %s ORDER BY id DESC LIMIT 1",
        (org_id,)
    )
    existing = pg_cur.fetchone()

    if existing:
        # Create new version
        old_version = existing["version"] or "1.0"
        try:
            major, minor = old_version.split(".")
            new_version = f"{major}.{int(minor) + 1}"
        except (ValueError, AttributeError):
            new_version = "1.1"

        log(f"  Existing setup found (version {old_version}). Creating version {new_version}.")
    else:
        new_version = "1.0"

    pg_cur.execute("""
        INSERT INTO organization_setup (
            organization_id, version,
            root_nodes, hub_node, metadata,
            is_active, created_date, updated_date
        ) VALUES (
            %s, %s,
            %s::json, %s::json, %s::json,
            TRUE, NOW(), NOW()
        )
        RETURNING id
    """, (
        org_id,
        new_version,
        root_nodes_json,
        hub_node_json,
        metadata_json,
    ))
    new_id = pg_cur.fetchone()["id"]
    pg_conn.commit()

    log(f"  Inserted organization_setup id={new_id} version={new_version} for org_id={org_id}")
    return new_id


# ============================================================================
# STEP 6: MIGRATE LOCATION_TAG_ID ON TRANSACTIONS
# ============================================================================

def migrate_transaction_location_tags(pg_cur, pg_conn, mysql_cur, org_id, legacy_org_id, tag_id_map, dry_run=False):
    """
    For transactions in this org that have NULL location_tag_id,
    look up the legacy MySQL transaction's location_tag_id and map it
    to the new user_location_id via tag_id_map.

    Legacy MySQL: transactions.location_tag_id → location_tags.id
    New PG: transactions.location_tag_id → user_locations.id (the migrated floor)
    """
    if not tag_id_map:
        log("  No tag_id_map entries - skipping transaction location_tag migration.")
        return

    if not legacy_org_id:
        log("  No legacy_org_id found - skipping transaction location_tag migration.")
        return

    log(f"  Migrating location_tag_id for org {org_id} (legacy org {legacy_org_id})...")

    # Get all legacy transactions for this org that have a location_tag_id
    mysql_cur.execute("""
        SELECT id, location_tag_id
        FROM transactions
        WHERE organization = %s
          AND location_tag_id IS NOT NULL
          AND is_active = 1
          AND deleted_date IS NULL
    """, (legacy_org_id,))
    legacy_txs = mysql_cur.fetchall()
    log(f"  Found {len(legacy_txs)} legacy transactions with location_tag_id")

    if not legacy_txs:
        return

    # Get new PG transactions for this org that have migration_id (= old tx id)
    pg_cur.execute("""
        SELECT id, migration_id, location_tag_id
        FROM transactions
        WHERE organization_id = %s
          AND migration_id IS NOT NULL
    """, (org_id,))
    pg_txs = {row["migration_id"]: row for row in pg_cur.fetchall()}
    log(f"  Found {len(pg_txs)} new PG transactions with migration_id")

    updated = 0
    skipped_no_mapping = 0
    skipped_no_pg_tx = 0
    skipped_already_set = 0

    for ltx in legacy_txs:
        old_tx_id = ltx["id"]
        old_tag_id = ltx["location_tag_id"]

        # Find the new user_location_id for this tag
        new_location_id = tag_id_map.get(old_tag_id)
        if not new_location_id:
            skipped_no_mapping += 1
            continue

        # Find the corresponding new PG transaction
        pg_tx = pg_txs.get(old_tx_id)
        if not pg_tx:
            skipped_no_pg_tx += 1
            continue

        # Skip if already set
        if pg_tx["location_tag_id"] is not None:
            skipped_already_set += 1
            continue

        if not dry_run:
            pg_cur.execute("""
                UPDATE transactions
                SET location_tag_id = %s, updated_date = NOW()
                WHERE id = %s
            """, (new_location_id, pg_tx["id"]))

        updated += 1

    if not dry_run:
        pg_conn.commit()

    log(f"  Transaction location_tag migration complete:")
    log(f"    Updated: {updated}")
    log(f"    Skipped (no tag mapping): {skipped_no_mapping}")
    log(f"    Skipped (no PG transaction): {skipped_no_pg_tx}")
    log(f"    Skipped (already set): {skipped_already_set}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_org_structure.py <csv_file> [--dry-run]")
        print("  e.g.: python migrate_org_structure.py 117.csv")
        print("  e.g.: python migrate_org_structure.py org_structures/117.csv --dry-run")
        sys.exit(1)

    csv_input = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    # Resolve CSV path
    if not os.path.exists(csv_input):
        # Try org_structures/ directory
        alt_path = os.path.join(os.path.dirname(__file__), "org_structures", csv_input)
        if os.path.exists(alt_path):
            csv_input = alt_path
        else:
            print(f"Error: CSV file not found: {csv_input}")
            sys.exit(1)

    org_id = get_org_id_from_filename(csv_input)

    log("=" * 70)
    log(f"Organization Structure Migration")
    log(f"  CSV: {csv_input}")
    log(f"  Org ID: {org_id}")
    log(f"  Dry Run: {dry_run}")
    log("=" * 70)

    # Parse CSV
    log("\nStep 1: Parsing CSV structure...")
    branches = parse_csv_structure(csv_input)
    total_buildings = sum(len(b["buildings"]) for b in branches)
    total_floors = sum(len(f["floors"]) for b in branches for f in b["buildings"])
    total_rooms = sum(len(r.get("rooms", [])) for b in branches for f in b["buildings"] for r in f["floors"])
    log(f"  Parsed: {len(branches)} branches, {total_buildings} buildings, {total_floors} floors, {total_rooms} rooms")

    # Connect to databases
    log("\nConnecting to databases...")
    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()

    try:
        # Get legacy org ID for transaction migration
        legacy_org_id = get_legacy_org_id(pg_cur, org_id)
        if not legacy_org_id:
            legacy_org_id = get_legacy_org_id_from_mappings(org_id)
        log(f"  Legacy MySQL org_id: {legacy_org_id}")

        # Step 2: Create user_locations
        log("\nStep 2: Creating user_locations...")
        tag_id_map, branches = create_user_locations(
            pg_cur, pg_conn, org_id, branches, mysql_cur, dry_run=dry_run
        )

        if not dry_run:
            # Step 3: Build root_nodes
            log("\nStep 3: Building root_nodes tree...")
            root_nodes = build_root_nodes(branches)
            log(f"  Built root_nodes with {len(root_nodes)} top-level branches")

            # Step 4: Build hub_node
            log("\nStep 4: Building hub_node (non-wastemaker destinations)...")
            hub_node = build_hub_node(pg_cur, org_id)
            log(f"  Found {len(hub_node)} destination locations")

            # Step 5: Insert organization_setup
            log("\nStep 5: Inserting organization_setup...")
            insert_organization_setup(pg_cur, pg_conn, org_id, root_nodes, hub_node, dry_run=dry_run)

            # Step 6: Migrate transaction location_tags
            log("\nStep 6: Migrating transaction location_tag_id...")
            migrate_transaction_location_tags(
                pg_cur, pg_conn, mysql_cur, org_id, legacy_org_id, tag_id_map, dry_run=dry_run
            )
        else:
            log("\n[DRY-RUN] Skipping steps 3-6 (no real IDs available)")
            log(f"  Would build root_nodes from {len(branches)} branches")
            log(f"  Would build hub_node for non-wastemaker locations in org {org_id}")
            log(f"  Would insert organization_setup for org {org_id}")
            log(f"  Would migrate location_tag_id on transactions for org {org_id}")

        log("\n" + "=" * 70)
        log("Migration complete!")
        log("=" * 70)

        # Print summary
        if not dry_run and tag_id_map:
            log("\nTag ID Mapping (legacy_tag_id → new_user_location_id):")
            for old_id, new_id in sorted(tag_id_map.items()):
                log(f"  {old_id} → {new_id}")

    except Exception as e:
        if not dry_run:
            pg_conn.rollback()
        log(f"\nERROR: {e}")
        raise
    finally:
        mysql_cur.close()
        mysql_conn.close()
        pg_cur.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
