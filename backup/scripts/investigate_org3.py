"""
Break down old records by business-unit and check which were migrated.
Also check the old report total per business-unit.
"""

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

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

OLD_ORG = 443
NEW_ORG = 125
DATE_FROM = "2023-01-01"
DATE_TO = "2023-12-31 23:59:59"


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # 1. Get ALL old records for org 443, 2023
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.calc_ghg, m.name_en AS mat_name,
               t.status AS tx_status, t.`business-unit` AS biz_unit,
               t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND tr.is_active = 1
          AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s
          AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    old_all = mysql_cur.fetchall()

    # Apply last-hop dedup
    last_hops = {}
    for r in old_all:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r

    old_records = {r["rec_id"]: r for r in last_hops.values() if r["rec_status"] != "rejected"}

    # 2. Break down by business-unit
    by_bu = {}
    for rec_id, r in old_records.items():
        bu = r["biz_unit"]
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        if bu not in by_bu:
            by_bu[bu] = {"count": 0, "weight": 0.0, "rec_ids": []}
        by_bu[bu]["count"] += 1
        by_bu[bu]["weight"] += w
        by_bu[bu]["rec_ids"].append(rec_id)

    print("OLD records by business-unit (2023, after dedup, non-rejected):")
    print(f"{'biz_unit':>10} | {'count':>6} | {'weight':>15}")
    print("-" * 40)
    for bu, data in sorted(by_bu.items(), key=lambda x: -x[1]["weight"]):
        print(f"{bu:>10} | {data['count']:>6} | {data['weight']:>15.2f}")
    total_old = sum(d["weight"] for d in by_bu.values())
    total_count = sum(d["count"] for d in by_bu.values())
    print(f"{'TOTAL':>10} | {total_count:>6} | {total_old:>15.2f}")

    # 3. Get migration_ids from new records
    pg_cur.execute("""
        SELECT tr.migration_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL
          AND tr.deleted_date IS NULL
          AND tr.migration_id IS NOT NULL
    """, (NEW_ORG,))
    migrated_ids = {r["migration_id"] for r in pg_cur.fetchall()}
    print(f"\nTotal migrated record IDs: {len(migrated_ids)}")

    # 4. Check which business-unit records were migrated
    print("\nMigrated vs not-migrated by business-unit:")
    print(f"{'biz_unit':>10} | {'total':>6} | {'migrated':>8} | {'not_migr':>8} | {'migrated_w':>12} | {'not_migr_w':>12}")
    print("-" * 75)
    for bu, data in sorted(by_bu.items(), key=lambda x: -x[1]["weight"]):
        mig_count = 0
        mig_weight = 0.0
        not_mig_count = 0
        not_mig_weight = 0.0
        for rec_id in data["rec_ids"]:
            r = old_records[rec_id]
            qty = abs(float(r["quantity"] or 0))
            uw = float(r["unit_weight"] or 0)
            w = qty * uw
            if rec_id in migrated_ids:
                mig_count += 1
                mig_weight += w
            else:
                not_mig_count += 1
                not_mig_weight += w
        print(f"{bu:>10} | {data['count']:>6} | {mig_count:>8} | {not_mig_count:>8} | {mig_weight:>12.2f} | {not_mig_weight:>12.2f}")

    # 5. Check business-unit names
    for bu in by_bu.keys():
        mysql_cur.execute("SELECT name FROM `business-unit` WHERE id = %s", (bu,))
        row = mysql_cur.fetchone()
        name = row["name"] if row else "UNKNOWN"
        print(f"  biz_unit {bu} = {name}")

    # 6. Check if old report uses SPECIFIC business-unit filter
    # The old report filters by user's accessible business-units
    # Let's check the old report number 526,992.71
    # Try each combination of business-units to see which gives 526,992.71
    all_bus = sorted(by_bu.keys())
    from itertools import combinations
    print(f"\nSearching for combination that gives 526,992.71...")
    target = 526992.71
    found = False
    for r in range(1, len(all_bus) + 1):
        for combo in combinations(all_bus, r):
            combo_weight = sum(by_bu[bu]["weight"] for bu in combo)
            if abs(combo_weight - target) < 1.0:
                print(f"  MATCH: business-units {combo} -> {combo_weight:.2f} kg")
                found = True
    if not found:
        print(f"  No exact match found. Closest:")
        for r in range(1, len(all_bus) + 1):
            for combo in combinations(all_bus, r):
                combo_weight = sum(by_bu[bu]["weight"] for bu in combo)
                if abs(combo_weight - target) < 5000:
                    print(f"  CLOSE: business-units {combo} -> {combo_weight:.2f} kg (diff={combo_weight - target:+.2f})")

    # 7. Also check: maybe old report filters per-transaction, not per-biz-unit
    # Could the 526,992.71 come from specific transactions?
    # Let's check migrated-only weight
    mig_total = 0.0
    mig_count = 0
    for rec_id, r in old_records.items():
        if rec_id in migrated_ids:
            qty = abs(float(r["quantity"] or 0))
            uw = float(r["unit_weight"] or 0)
            mig_total += qty * uw
            mig_count += 1
    print(f"\nWeight of ONLY migrated old records: {mig_total:.2f} kg ({mig_count} records)")
    print(f"  Diff from target 526,992.71: {mig_total - target:+.2f} kg")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
