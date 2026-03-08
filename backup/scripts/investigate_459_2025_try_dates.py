"""
Try different end_date values to find what matches 45,070.35.
The old report does: end_date = parse(endDate) - 7h
"""

import pymysql

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


def query_total(cur, start, end):
    cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (OLD_ORG,))
    biz_ids = [r["id"] for r in cur.fetchall()]
    biz_filter = ",".join(str(b) for b in biz_ids)

    cur.execute(f"""
        SELECT id FROM transactions
        WHERE transaction_date BETWEEN %s AND %s
          AND transaction_type = 1
          AND `business-unit` IN ({biz_filter})
          AND deleted_date IS NULL
    """, (start, end))
    txs = cur.fetchall()
    if not txs:
        return 0, 0

    tx_ids = ",".join(str(t["id"]) for t in txs)
    cur.execute(f"""
        SELECT tr.id, tr.transaction_id, tr.quantity, tr.status, tr.material, tr.journey_id
        FROM transaction_records tr
        WHERE tr.transaction_id IN ({tx_ids})
          AND tr.deleted_date IS NULL
    """)
    recs = cur.fetchall()

    cur.execute("SELECT id, unit_weight FROM materials WHERE id > 0 AND deleted_date IS NULL")
    mats = {m["id"]: m for m in cur.fetchall()}

    hops = {}
    for r in recs:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        r["uw"] = float(mats.get(r["material"], {}).get("unit_weight", 0) or 0)
        hops[key] = r

    non_rej = [v for v in hops.values() if v["status"] != "rejected"]
    total = sum(abs(float(r["quantity"] or 0)) * r["uw"] for r in non_rej)
    return len(non_rej), total


def main():
    conn = pymysql.connect(**MYSQL_CONFIG)
    cur = conn.cursor()

    combos = [
        # (label, start, end) — simulating what -7h would produce from various frontend dates
        ("endDate=2025-12-31 → end=2025-12-30 17:00",
         "2024-12-31 17:00:00", "2025-12-30 17:00:00"),

        ("endDate=2026-01-01 → end=2025-12-31 17:00",
         "2024-12-31 17:00:00", "2025-12-31 17:00:00"),

        ("No TZ: 2025-01-01 to 2025-12-31 23:59:59",
         "2025-01-01 00:00:00", "2025-12-31 23:59:59"),

        ("Corrected TZ: start=2024-12-31 17:00, end=2025-12-31 16:59:59",
         "2024-12-31 17:00:00", "2025-12-31 16:59:59"),

        # Maybe old frontend sends current-time and endDate differently
        ("TZ end=2025-12-31 00:00 (no -7h on end)",
         "2024-12-31 17:00:00", "2025-12-31 00:00:00"),

        ("TZ end=2025-12-31 23:59:59 (end-of-day, no -7h)",
         "2024-12-31 17:00:00", "2025-12-31 23:59:59"),

        # Start at 2025-01-01, end with TZ shift from 2026-01-01
        ("start=2025-01-01, end=2025-12-31 17:00",
         "2025-01-01 00:00:00", "2025-12-31 17:00:00"),
    ]

    print(f"Target: {TARGET:.2f}\n")
    print(f"{'Label':<60} | {'Count':>6} | {'Total':>12} | {'Diff':>10}")
    print("-" * 100)
    for label, start, end in combos:
        cnt, total = query_total(cur, start, end)
        diff = total - TARGET
        match = " <<<" if abs(diff) < 0.1 else ""
        print(f"{label:<60} | {cnt:>6} | {total:>12.2f} | {diff:>+10.2f}{match}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
