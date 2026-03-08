#!/usr/bin/env python3
"""
Transform manually-arranged organization structure CSV into organization_setup insert.

Input CSV format (after manual arrangement):
  branches,buildings,floors,rooms
  3376:สาขา กรุงเทพ,,,
  ,3377:อาคาร A,,
  ,,3378:ชั้น 1,
  ,,,3379:ห้อง 101
  ,,,3380:ห้อง 102
  ,,3381:ชั้น 2,
  ,3382:อาคาร B,,
  3383:สาขา ชลบุรี,,,

The column position determines the hierarchy level:
  - Column 0 (branches)  = Level 0 (root)
  - Column 1 (buildings) = Level 1
  - Column 2 (floors)    = Level 2
  - Column 3 (rooms)     = Level 3

Output: INSERT into organization_setup table with nested root_nodes JSON.

Usage:
  python3 transform_to_org_setup.py <org_id>.csv
  python3 transform_to_org_setup.py org_structures/123.csv
"""

import os
import sys
import csv
import json
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load DB config
ENV_PATH = os.path.join(os.path.dirname(__file__), "backend", "migrations", ".env")
load_dotenv(ENV_PATH)

PG_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}


def parse_cell(cell: str):
    """Parse 'id:name' cell value. Returns (node_id, name) or None if empty."""
    cell = cell.strip()
    if not cell:
        return None
    parts = cell.split(":", 1)
    node_id = int(parts[0])
    name = parts[1] if len(parts) > 1 else ""
    return node_id, name


def parse_csv(csv_path: str):
    """
    Parse the arranged CSV and build a nested tree structure.

    Returns (root_nodes, total_nodes, max_level).
    root_nodes is a list like:
      [{"nodeId": 3376, "children": [{"nodeId": 3377, "children": [...]}]}]
    """
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header
        for row in reader:
            # Pad row to 4 columns
            while len(row) < 4:
                row.append("")
            rows.append(row)

    if not rows:
        print("No data rows found in CSV")
        sys.exit(1)

    # Build tree by tracking parent stack at each level
    root_nodes = []
    # Stack: [level0_node, level1_node, level2_node, level3_node]
    stack = [None, None, None, None]
    total_nodes = 0
    max_level = 0

    for row_idx, row in enumerate(rows):
        # Find which column has the value
        level = None
        parsed = None
        for col in range(4):
            p = parse_cell(row[col])
            if p is not None:
                level = col
                parsed = p
                break

        if level is None:
            # Empty row, skip
            continue

        node_id, name = parsed
        node = {"nodeId": node_id, "children": []}
        total_nodes += 1
        max_level = max(max_level, level)

        # Place node in tree
        if level == 0:
            # Root level branch
            root_nodes.append(node)
            stack[0] = node
            # Reset deeper levels
            stack[1] = None
            stack[2] = None
            stack[3] = None
        else:
            # Find parent at level-1
            parent = stack[level - 1]
            if parent is None:
                print(f"WARNING: Row {row_idx + 2} at level {level} has no parent at level {level - 1}. "
                      f"Skipping node {node_id}:{name}")
                continue
            parent["children"].append(node)
            stack[level] = node
            # Reset deeper levels
            for deeper in range(level + 1, 4):
                stack[deeper] = None

    return root_nodes, total_nodes, max_level


def clean_children(nodes):
    """Remove empty children arrays for cleaner JSON."""
    for node in nodes:
        if node["children"]:
            clean_children(node["children"])
        else:
            del node["children"]
    return nodes


def insert_org_setup(org_id: int, root_nodes: list, total_nodes: int, max_level: int):
    """Insert or update organization_setup for the given org."""
    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "version": "1.0",
        "maxLevel": max_level,
        "createdAt": now,
        "totalNodes": total_nodes,
    }

    root_nodes_json = json.dumps(root_nodes, ensure_ascii=False)
    metadata_json = json.dumps(metadata, ensure_ascii=False)

    # Check if org exists
    cur.execute("SELECT id, name_en FROM organizations WHERE id = %s", (org_id,))
    org = cur.fetchone()
    if not org:
        print(f"ERROR: Organization {org_id} not found in database")
        cur.close()
        conn.close()
        sys.exit(1)

    print(f"Organization: {org_id} ({org['name_en']})")

    # Check if setup already exists
    cur.execute("""
        SELECT id FROM organization_setup
        WHERE organization_id = %s AND is_active = TRUE
    """, (org_id,))
    existing = cur.fetchone()

    if existing:
        # Update existing
        cur.execute("""
            UPDATE organization_setup
            SET root_nodes = %s::jsonb,
                metadata = %s::jsonb,
                updated_date = NOW()
            WHERE id = %s
        """, (root_nodes_json, metadata_json, existing["id"]))
        print(f"Updated existing organization_setup (id={existing['id']})")
    else:
        # Insert new
        cur.execute("""
            INSERT INTO organization_setup (organization_id, version, is_active, root_nodes, metadata)
            VALUES (%s, '1.0', TRUE, %s::jsonb, %s::jsonb)
            RETURNING id
        """, (org_id, root_nodes_json, metadata_json))
        new_id = cur.fetchone()["id"]
        print(f"Inserted new organization_setup (id={new_id})")

    conn.commit()
    cur.close()
    conn.close()

    print(f"  root_nodes: {total_nodes} nodes, max depth: {max_level}")
    print(f"  JSON preview: {root_nodes_json[:200]}...")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 transform_to_org_setup.py <org_id>.csv")
        print("       python3 transform_to_org_setup.py org_structures/123.csv")
        sys.exit(1)

    csv_path = sys.argv[1]

    # If just a filename, check in org_structures/ too
    if not os.path.exists(csv_path):
        alt_path = os.path.join("org_structures", csv_path)
        if os.path.exists(alt_path):
            csv_path = alt_path
        else:
            print(f"ERROR: File not found: {csv_path}")
            sys.exit(1)

    # Extract org_id from filename (e.g., "123.csv" -> 123)
    basename = os.path.basename(csv_path)
    org_id_str = os.path.splitext(basename)[0]
    try:
        org_id = int(org_id_str)
    except ValueError:
        print(f"ERROR: Cannot extract org_id from filename '{basename}'. "
              f"Expected format: <org_id>.csv (e.g., 123.csv)")
        sys.exit(1)

    print(f"Parsing CSV: {csv_path}")
    root_nodes, total_nodes, max_level = parse_csv(csv_path)

    # Optionally clean empty children arrays
    clean_children(root_nodes)

    print(f"Parsed {total_nodes} nodes, max level: {max_level}, root branches: {len(root_nodes)}")
    print(f"\nTree preview:")
    print(json.dumps(root_nodes, indent=2, ensure_ascii=False)[:500])
    print("...")

    insert_org_setup(org_id, root_nodes, total_nodes, max_level)
    print("\nDone!")


if __name__ == "__main__":
    main()
