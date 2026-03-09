"""
Try various combinations to match old report 45,070.35 for org 459, year 2025.
"""

import pymysql
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

OLD_ORG = 459
TARGET = 45070.35


def query_total(cur, start, end, is_active_filter=True, deleted_filter=True, dedup=True, biz_exclude=None):
    sql = """
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`, tr.is_active, tr.deleted_date,
               m.unit_weight, m.name_en AS mat_name,
               t.`business-unit` AS biz_unit, t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND t.transaction_date BETWEEN %s AND %s
    """
    if is_active_filter:
        sql += " AND tr.is_active = 1"
    if deleted_filter:
        sql += " AND tr.deleted_date IS NULL"
    cur.execute(sql, (OLD_ORG, start, end))
    rows = cur.fetchall()

    if biz_exclude:
        rows = [r for r in rows if r["biz_unit"] not in biz_exclude]

    if dedup:
        hops = {}
        for r in rows:
            key = f"{r['transaction_id']}_{r['journey_id']}"
            hops[key] = r
        rows = list(hops.values())

    non_rej = [r for r in rows if r["rec_status"] != "rejected"]
    total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in non_rej)
    return len(non_rej), total


def main():
    conn = pymysql.connect(**MYSQL_CONFIG)
    cur = conn.cursor()

    combos = [
        # (label, start, end, is_active, deleted, dedup, biz_exclude)
        ("No TZ, +active, +deleted",
         "2025-01-01", "2025-12-31 23:59:59", True, True, True, None),

        ("TZ -7h, +active, +deleted",
         "2024-12-31 17:00:00", "2025-12-30 17:00:00", True, True, True, None),

        ("TZ -7h, NO active, NO deleted",
         "2024-12-31 17:00:00", "2025-12-30 17:00:00", False, False, True, None),

        ("No TZ, NO active, NO deleted",
         "2025-01-01", "2025-12-31 23:59:59", False, False, True, None),

        # Exclude biz_unit 14031 (was excluded in 2024 fix)
        ("No TZ, +active, +deleted, excl 14031",
         "2025-01-01", "2025-12-31 23:59:59", True, True, True, {14031}),

        ("TZ -7h, +active, +deleted, excl 14031",
         "2024-12-31 17:00:00", "2025-12-30 17:00:00", True, True, True, {14031}),

        # Try end_date as 2025-12-31 (midnight, not 23:59:59)
        ("No TZ end=midnight, +active, +deleted",
         "2025-01-01", "2025-12-31", True, True, True, None),

        # Try different end interpretations for TZ
        ("TZ -7h end=2025-12-30 16:59:59, +active, +deleted",
         "2024-12-31 17:00:00", "2025-12-30 16:59:59", True, True, True, None),

        # No dedup
        ("TZ -7h, +active, +deleted, NO dedup",
         "2024-12-31 17:00:00", "2025-12-30 17:00:00", True, True, False, None),
    ]

    print(f"Target: {TARGET:.2f} kg")
    print(f"\n{'Label':<55} | {'Count':>6} | {'Total':>12} | {'Diff':>10}")
    print("-" * 95)

    for label, start, end, act, deld, ded, biz_ex in combos:
        cnt, total = query_total(cur, start, end, act, deld, ded, biz_ex)
        diff = total - TARGET
        match = "<<<" if abs(diff) < 0.1 else ""
        print(f"{label:<55} | {cnt:>6} | {total:>12.2f} | {diff:>+10.2f} {match}")

    # Also try by filtering specific biz_units to see if we can match
    print(f"\n{'='*70}")
    print("Per biz-unit with TZ shift, +active, +deleted:")

    cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.name_en AS mat_name,
               t.`business-unit` AS biz_unit, t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date BETWEEN '2024-12-31 17:00:00' AND '2025-12-30 17:00:00'
    """, (OLD_ORG,))
    rows = cur.fetchall()

    hops = {}
    for r in rows:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        hops[key] = r
    non_rej = [r for r in hops.values() if r["rec_status"] != "rejected"]

    by_bu = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in non_rej:
        w = abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0)
        by_bu[r["biz_unit"]]["count"] += 1
        by_bu[r["biz_unit"]]["weight"] += w

    total_tz = 0.0
    for bu in sorted(by_bu, key=lambda b: -by_bu[b]["weight"]):
        total_tz += by_bu[bu]["weight"]
        print(f"  {bu}: {by_bu[bu]['count']} recs, {by_bu[bu]['weight']:.2f} kg (running: {total_tz:.2f})")

    # Compare to no-TZ per biz-unit
    print(f"\nPer biz-unit WITHOUT TZ shift:")
    cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.name_en AS mat_name,
               t.`business-unit` AS biz_unit, t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= '2025-01-01' AND t.transaction_date <= '2025-12-31 23:59:59'
    """, (OLD_ORG,))
    rows2 = cur.fetchall()

    hops2 = {}
    for r in rows2:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        hops2[key] = r
    non_rej2 = [r for r in hops2.values() if r["rec_status"] != "rejected"]

    by_bu2 = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in non_rej2:
        w = abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0)
        by_bu2[r["biz_unit"]]["count"] += 1
        by_bu2[r["biz_unit"]]["weight"] += w

    print(f"\n{'biz_unit':>10} | {'TZ_count':>8} | {'TZ_weight':>12} | {'noTZ_count':>10} | {'noTZ_weight':>12} | {'diff':>10}")
    print("-" * 80)
    all_bus = set(list(by_bu.keys()) + list(by_bu2.keys()))
    for bu in sorted(all_bus, key=lambda b: -by_bu2.get(b, {}).get("weight", 0)):
        tz_c = by_bu.get(bu, {}).get("count", 0)
        tz_w = by_bu.get(bu, {}).get("weight", 0.0)
        no_c = by_bu2.get(bu, {}).get("count", 0)
        no_w = by_bu2.get(bu, {}).get("weight", 0.0)
        d = tz_w - no_w
        if abs(d) > 0.01:
            print(f"{bu:>10} | {tz_c:>8} | {tz_w:>12.2f} | {no_c:>10} | {no_w:>12.2f} | {d:>+10.2f} ***")
        else:
            print(f"{bu:>10} | {tz_c:>8} | {tz_w:>12.2f} | {no_c:>10} | {no_w:>12.2f} | {d:>+10.2f}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
