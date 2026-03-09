#!/usr/bin/env python3
"""
Export organization structures to CSV files.

For each migrated organization (migration_id IS NOT NULL), exports its
user_locations (is_location=TRUE, is_active=TRUE, deleted_date IS NULL)
to org_structures/{org_id}.csv

CSV format:
  branches,buildings,floors,rooms
  {id}:{name_en},,,
  ...

Usage:
  python3 export_org_structures.py
"""

import os
import csv
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load DB config from backend/migrations/.env
ENV_PATH = os.path.join(os.path.dirname(__file__), "backend", "migrations", ".env")
load_dotenv(ENV_PATH)

PG_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "org_structures")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get all active organizations
    cur.execute("""
        SELECT id, name
        FROM organizations
        WHERE is_active = TRUE
          AND deleted_date IS NULL
        ORDER BY id
    """)
    orgs = cur.fetchall()
    print(f"Found {len(orgs)} active organizations")

    exported = 0
    for org in orgs:
        org_id = org["id"]
        org_name = org["name"] or f"org_{org_id}"

        # Get locations for this org
        cur.execute("""
            SELECT id, name_th
            FROM user_locations
            WHERE organization_id = %s
              AND is_location = TRUE
              AND is_active = TRUE
              AND deleted_date IS NULL
            ORDER BY id
        """, (org_id,))
        locations = cur.fetchall()

        if not locations:
            continue

        csv_path = os.path.join(OUTPUT_DIR, f"{org_id}.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["branches", "buildings", "floors", "rooms"])
            for loc in locations:
                name = loc["name_th"] or ""
                writer.writerow([f"{loc['id']}:{name}", "", "", ""])

        exported += 1
        print(f"  [{exported}] Org {org_id} ({org_name}): {len(locations)} locations -> {csv_path}")

    print(f"\nExported {exported} organization CSVs to {OUTPUT_DIR}/")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
