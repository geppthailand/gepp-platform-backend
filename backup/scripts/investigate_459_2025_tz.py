"""
Verify the timezone difference between old and new report for org 459/141, year 2025.

Old report: start_date - 7h, end_date - 7h
  2025-01-01 00:00:00 - 7h = 2024-12-31 17:00:00
  2025-12-31 00:00:00 - 7h = 2025-12-30 17:00:00

New report: Bangkok start-of-day/end-of-day → UTC
  2025-01-01 00:00:00 +07:00 → 2024-12-31 17:00:00 UTC
  2025-12-31 23:59:59 +07:00 → 2025-12-30 16:59:59 UTC

Key difference: OLD end_date = 2025-12-30 17:00:00, NEW end_date = 2025-12-30 16:59:59
  (almost identical, ~1 second diff)

But ALSO: old report doesn't filter is_active/deleted_date on transaction_records!
"""

import pymysql
import psycopg2
import psycopg2.extras
from collections import defaultdict

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

OLD_ORG = 459
NEW_ORG = 141


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # ========== OLD REPORT LOGIC (with -7h timezone) ==========
    # Old report: start=2024-12-31 17:00:00, end=2025-12-30 17:00:00
    OLD_START = "2024-12-31 17:00:00"
    OLD_END = "2025-12-30 17:00:00"

    # My query range (no timezone)
    MY_START = "2025-01-01 00:00:00"
    MY_END = "2025-12-31 23:59:59"

    print("=== OLD REPORT TIMEZONE QUERY ===")
    print(f"  Old report range: {OLD_START} to {OLD_END}")
    print(f"  My query range:   {MY_START} to {MY_END}")

    # Query with old report's timezone range
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.name_en AS mat_name,
               t.status AS tx_status, t.`business-unit` AS biz_unit, t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND t.transaction_date BETWEEN %s AND %s
    """, (OLD_ORG, OLD_START, OLD_END))
    old_tz_all = mysql_cur.fetchall()

    # Apply last-hop dedup (same as old report)
    last_hops = {}
    for r in old_tz_all:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r
    non_rejected = {k: v for k, v in last_hops.items() if v["rec_status"] != "rejected"}

    old_tz_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in non_rejected.values())
    print(f"\n  Old TZ query: {len(old_tz_all)} raw -> {len(last_hops)} dedup -> {len(non_rejected)} non-rejected")
    print(f"  Old TZ total: {old_tz_total:.2f} kg")
    print(f"  Target:       45,070.35 kg")
    print(f"  Match: {'YES' if abs(old_tz_total - 45070.35) < 0.1 else 'NO'} (diff={old_tz_total - 45070.35:+.2f})")

    # Query with my range (no timezone)
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.name_en AS mat_name,
               t.status AS tx_status, t.`business-unit` AS biz_unit, t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, MY_START, MY_END))
    my_all = mysql_cur.fetchall()
    my_hops = {}
    for r in my_all:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        my_hops[key] = r
    my_non_rej = {k: v for k, v in my_hops.items() if v["rec_status"] != "rejected"}
    my_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in my_non_rej.values())
    print(f"\n  My query total: {my_total:.2f} kg")

    # Find records in OLD TZ range but NOT in MY range
    old_tz_ids = {v["rec_id"] for v in non_rejected.values()}
    my_ids = {v["rec_id"] for v in my_non_rej.values()}

    only_in_old_tz = old_tz_ids - my_ids
    only_in_my = my_ids - old_tz_ids

    print(f"\n  Records only in OLD TZ query: {len(only_in_old_tz)}")
    old_tz_dict = {v["rec_id"]: v for v in non_rejected.values()}
    only_old_weight = 0.0
    for rid in sorted(only_in_old_tz):
        r = old_tz_dict[rid]
        w = abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0)
        only_old_weight += w
        print(f"    rec_id={rid}, tx_date={r['transaction_date']}, w={w:.2f}, mat={r['mat_name']}, biz={r['biz_unit']}")
    print(f"    Total: {only_old_weight:.2f} kg")

    print(f"\n  Records only in MY query: {len(only_in_my)}")
    my_dict = {v["rec_id"]: v for v in my_non_rej.values()}
    only_my_weight = 0.0
    for rid in sorted(only_in_my):
        r = my_dict[rid]
        w = abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0)
        only_my_weight += w
        print(f"    rec_id={rid}, tx_date={r['transaction_date']}, w={w:.2f}, mat={r['mat_name']}, biz={r['biz_unit']}")
    print(f"    Total: {only_my_weight:.2f} kg")

    print(f"\n  Net difference: {only_old_weight - only_my_weight:+.2f} kg")
    print(f"  Expected diff:  {old_tz_total - my_total:+.2f} kg")

    # ========== NEW DB: Check with both date ranges ==========
    print(f"\n{'='*70}")
    print("=== NEW DB (PostgreSQL) ===")

    # New DB with my range
    pg_cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight,
               COUNT(*) AS cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
    """, (NEW_ORG, MY_START, MY_END))
    new_my = pg_cur.fetchone()
    print(f"  New DB (my range {MY_START} to {MY_END}):")
    print(f"    {new_my['cnt']} records, {float(new_my['total_weight'] or 0):.2f} kg")

    # New DB with old TZ range
    pg_cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight,
               COUNT(*) AS cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
    """, (NEW_ORG, OLD_START, OLD_END))
    new_tz = pg_cur.fetchone()
    print(f"  New DB (old TZ range {OLD_START} to {OLD_END}):")
    print(f"    {new_tz['cnt']} records, {float(new_tz['total_weight'] or 0):.2f} kg")

    # Check what records are at boundary dates in new DB
    print(f"\n  Records near 2024-12-31 in new DB:")
    pg_cur.execute("""
        SELECT tr.id, tr.migration_id, tr.origin_quantity, tr.transaction_date,
               m.unit_weight, m.name_en
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2024-12-31 00:00:00'
          AND tr.transaction_date <= '2025-01-01 00:00:00'
        ORDER BY tr.transaction_date
    """, (NEW_ORG,))
    boundary_new = pg_cur.fetchall()
    boundary_weight = 0.0
    for r in boundary_new:
        w = float(r["origin_quantity"] or 0) * float(r["unit_weight"] or 0)
        boundary_weight += w
        print(f"    rec={r['id']}, mig={r['migration_id']}, date={r['transaction_date']}, w={w:.2f}, mat={r['name_en']}")
    print(f"    Total boundary weight: {boundary_weight:.2f} kg")

    # Check end of 2025 boundary in new DB
    print(f"\n  Records near 2025-12-31 in new DB:")
    pg_cur.execute("""
        SELECT tr.id, tr.migration_id, tr.origin_quantity, tr.transaction_date,
               m.unit_weight, m.name_en
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2025-12-30 17:00:00'
          AND tr.transaction_date <= '2025-12-31 23:59:59'
        ORDER BY tr.transaction_date
    """, (NEW_ORG,))
    end_boundary = pg_cur.fetchall()
    end_weight = 0.0
    for r in end_boundary:
        w = float(r["origin_quantity"] or 0) * float(r["unit_weight"] or 0)
        end_weight += w
        print(f"    rec={r['id']}, mig={r['migration_id']}, date={r['transaction_date']}, w={w:.2f}, mat={r['name_en']}")
    print(f"    Total end boundary weight: {end_weight:.2f} kg")

    print(f"\n{'='*70}")
    print("SUMMARY:")
    print(f"  Old report (TZ-shifted): {old_tz_total:.2f} kg  (target: 45,070.35)")
    print(f"  My query (no TZ):        {my_total:.2f} kg")
    print(f"  New DB (no TZ):          {float(new_my['total_weight'] or 0):.2f} kg")
    print(f"  New DB (TZ-shifted):     {float(new_tz['total_weight'] or 0):.2f} kg")

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
