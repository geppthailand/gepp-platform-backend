"""
EXACT old report reproduction for org 459, year 2025.
Key finding: fetchall() appends "AND deleted_date IS NULL" to ALL queries!
So records DO have deleted_date filter, but NO is_active filter.
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

# Old report TZ: -7h
OLD_START = "2024-12-31 17:00:00"
OLD_END = "2025-12-30 17:00:00"

# No TZ
NO_TZ_START = "2025-01-01 00:00:00"
NO_TZ_END = "2025-12-31 23:59:59"


def query_old_report(cur, start, end, label):
    """Reproduce exact old report logic"""
    # Get biz_units from business_units table (with deleted_date IS NULL)
    cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (OLD_ORG,))
    biz_ids = [r["id"] for r in cur.fetchall()]
    biz_filter = ",".join(str(b) for b in biz_ids)

    # 1. Transactions: with deleted_date IS NULL (from fetchall)
    cur.execute(f"""
        SELECT id, `business-unit` AS biz_unit, transaction_date, status
        FROM transactions
        WHERE transaction_date BETWEEN %s AND %s
          AND transaction_type = 1
          AND `business-unit` IN ({biz_filter})
          AND deleted_date IS NULL
    """, (start, end))
    txs = cur.fetchall()
    tx_by_id = {t["id"]: t for t in txs}

    if not txs:
        print(f"  {label}: No transactions")
        return

    # 2. Records: with deleted_date IS NULL (from fetchall), but NO is_active filter
    tx_ids = ",".join(str(t["id"]) for t in txs)
    cur.execute(f"""
        SELECT tr.id, tr.transaction_id, tr.quantity, tr.status, tr.material,
               tr.journey_id, tr.is_active
        FROM transaction_records tr
        WHERE tr.transaction_id IN ({tx_ids})
          AND tr.deleted_date IS NULL
    """)
    recs = cur.fetchall()

    # 3. Materials (with deleted_date IS NULL)
    cur.execute("SELECT id, unit_weight, name_en FROM materials WHERE id > 0 AND deleted_date IS NULL")
    mats = {m["id"]: m for m in cur.fetchall()}

    # 4. Journey_id dedup (last wins)
    last_hops = {}
    for r in recs:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        mat = mats.get(r["material"], {})
        r["unit_weight"] = mat.get("unit_weight", 0)
        r["mat_name"] = mat.get("name_en", "?")
        r["biz_unit"] = tx_by_id[r["transaction_id"]]["biz_unit"]
        last_hops[key] = r

    # 5. Non-rejected
    non_rej = {k: v for k, v in last_hops.items() if v["status"] != "rejected"}

    # 6. Calculate: quantity * unit_weight (raw, not abs)
    total_raw = sum(float(r["quantity"] or 0) * float(r["unit_weight"] or 0) for r in non_rej.values())
    total_abs = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in non_rej.values())

    # Check inactive records
    inactive = [r for r in non_rej.values() if r["is_active"] != 1]

    print(f"  {label}:")
    print(f"    Txs: {len(txs)}, Recs: {len(recs)}, Dedup: {len(last_hops)}, Non-rej: {len(non_rej)}")
    print(f"    Inactive in non-rej: {len(inactive)}")
    print(f"    Total (raw qty): {total_raw:.2f} kg")
    print(f"    Total (abs qty): {total_abs:.2f} kg")
    print(f"    Target: {TARGET:.2f} kg")
    diff_raw = total_raw - TARGET
    diff_abs = total_abs - TARGET
    print(f"    Raw match: {'YES' if abs(diff_raw) < 0.1 else 'NO'} (diff={diff_raw:+.2f})")
    print(f"    Abs match: {'YES' if abs(diff_abs) < 0.1 else 'NO'} (diff={diff_abs:+.2f})")

    if inactive:
        print(f"\n    Inactive records included:")
        for r in inactive:
            qty = float(r["quantity"] or 0)
            uw = float(r["unit_weight"] or 0)
            print(f"      rec_id={r['id']}, qty={qty}, uw={uw}, w={qty*uw:.2f}, "
                  f"is_active={r['is_active']}, mat={r['mat_name']}, biz={r['biz_unit']}")

    by_bu = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in non_rej.values():
        w = abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0)
        by_bu[r["biz_unit"]]["count"] += 1
        by_bu[r["biz_unit"]]["weight"] += w

    print(f"\n    Biz-unit breakdown:")
    for bu in sorted(by_bu, key=lambda b: -by_bu[b]["weight"]):
        print(f"      {bu}: {by_bu[bu]['count']} recs, {by_bu[bu]['weight']:.2f} kg")


def main():
    conn = pymysql.connect(**MYSQL_CONFIG)
    cur = conn.cursor()

    print(f"Target: {TARGET:.2f} kg\n")

    query_old_report(cur, OLD_START, OLD_END, "TZ -7h + deleted_date IS NULL")
    print()
    query_old_report(cur, NO_TZ_START, NO_TZ_END, "No TZ + deleted_date IS NULL")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
