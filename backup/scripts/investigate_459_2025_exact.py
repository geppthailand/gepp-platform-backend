"""
Reproduce the EXACT old report logic for org 459, year 2025.
1. Get all business_units from business_units table (not from transactions)
2. Apply -7h timezone shift
3. No is_active/deleted_date filter on records
4. Use raw quantity (not abs)
5. Journey_id dedup (last wins)
6. Non-rejected filter
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


def main():
    conn = pymysql.connect(**MYSQL_CONFIG)
    cur = conn.cursor()

    # 1. Get business_units from business_units table (same as old report)
    cur.execute("SELECT id, name_en, name_th FROM business_units WHERE organization = %s", (OLD_ORG,))
    biz_units = cur.fetchall()
    biz_ids = [b["id"] for b in biz_units]
    print(f"Business units from table: {len(biz_ids)}")
    for b in biz_units:
        print(f"  {b['id']}: {b['name_en']}")

    # Also check what biz_units appear in transactions for this org
    cur.execute("""
        SELECT DISTINCT t.`business-unit` AS bu
        FROM transactions t
        WHERE t.organization = %s
        ORDER BY t.`business-unit`
    """, (OLD_ORG,))
    tx_bus = [r["bu"] for r in cur.fetchall()]
    print(f"\nBiz-units in transactions: {tx_bus}")

    missing_from_table = set(tx_bus) - set(biz_ids)
    extra_in_table = set(biz_ids) - set(tx_bus)
    print(f"In transactions but NOT in business_units table: {missing_from_table}")
    print(f"In business_units table but NOT in transactions: {extra_in_table}")

    # 2. Old report date range with -7h TZ shift
    OLD_START = "2024-12-31 17:00:00"
    OLD_END = "2025-12-30 17:00:00"

    # 3. Query exactly like old report
    biz_filter = ",".join(str(b) for b in biz_ids)
    cur.execute(f"""
        SELECT * FROM transactions
        WHERE `transaction_date` BETWEEN %s AND %s
          AND transaction_type = 1
          AND `business-unit` IN ({biz_filter})
    """, (OLD_START, OLD_END))
    transactions = cur.fetchall()
    transactions_by_id = {t["id"]: t for t in transactions}
    print(f"\nTransactions (TZ range, biz filtered): {len(transactions)}")

    if not transactions:
        print("No transactions found!")
        cur.close(); conn.close()
        return

    # 4. Get ALL records (no is_active/deleted_date filter, same as old report)
    tx_ids = ",".join(str(t["id"]) for t in transactions)
    cur.execute(f"""
        SELECT * FROM transaction_records WHERE transaction_id IN ({tx_ids})
    """)
    records = cur.fetchall()
    print(f"Records (no is_active/deleted filter): {len(records)}")

    # 5. Get materials
    cur.execute("SELECT * FROM materials WHERE id > 0")
    materials = cur.fetchall()
    materials_by_id = {m["id"]: m for m in materials}

    # 6. Build last_hops (same dedup as old report)
    last_hops = {}
    for r in records:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        # Merge record with material data
        mat = materials_by_id.get(r["material"], {})
        hop = {**r}
        hop["mat_unit_weight"] = mat.get("unit_weight", 0)
        hop["mat_calc_ghg"] = mat.get("calc_ghg", 0)
        hop["mat_name_en"] = mat.get("name_en", "?")
        hop["mat_material_category_id"] = mat.get("material_category_id")
        # transaction_date from parent transaction
        hop["transaction_date"] = transactions_by_id[r["transaction_id"]]["transaction_date"]
        hop["fh_origin"] = transactions_by_id[r["transaction_id"]]["business-unit"]
        last_hops[key] = hop

    print(f"Last hops (deduped): {len(last_hops)}")

    # 7. Calculate weights using raw quantity (not abs, same as old report)
    non_rejected = {k: v for k, v in last_hops.items() if v["status"] != "rejected"}
    print(f"Non-rejected: {len(non_rejected)}")

    total_weight = 0.0
    by_bu = defaultdict(lambda: {"count": 0, "weight": 0.0})
    negative_qty = []
    for k, r in non_rejected.items():
        qty = float(r["quantity"] or 0)  # RAW, not abs
        uw = float(r["mat_unit_weight"] or 0)
        w = qty * uw
        total_weight += w
        by_bu[r["fh_origin"]]["count"] += 1
        by_bu[r["fh_origin"]]["weight"] += w
        if qty < 0:
            negative_qty.append({"key": k, "qty": qty, "uw": uw, "w": w, "mat": r["mat_name_en"]})

    print(f"\nTotal weight (raw qty): {total_weight:.2f} kg")
    print(f"Target: {TARGET:.2f} kg")
    print(f"Match: {'YES' if abs(total_weight - TARGET) < 0.1 else 'NO'} (diff={total_weight - TARGET:+.2f})")

    if negative_qty:
        print(f"\nNegative quantities: {len(negative_qty)}")
        for r in negative_qty:
            print(f"  {r['key']}: qty={r['qty']}, uw={r['uw']}, w={r['w']:.2f}, mat={r['mat']}")

    # Also try with abs(quantity)
    total_abs = 0.0
    for k, r in non_rejected.items():
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["mat_unit_weight"] or 0)
        total_abs += qty * uw
    print(f"\nTotal weight (abs qty): {total_abs:.2f} kg")

    print(f"\nBiz-unit breakdown:")
    for bu in sorted(by_bu, key=lambda b: -by_bu[b]["weight"]):
        print(f"  {bu}: {by_bu[bu]['count']} recs, {by_bu[bu]['weight']:.2f} kg")

    # 8. Also try WITHOUT TZ shift but with old report's record logic (no is_active/deleted filter)
    print(f"\n{'='*70}")
    print("WITHOUT TZ SHIFT but with old report record logic:")
    cur.execute(f"""
        SELECT * FROM transactions
        WHERE `transaction_date` BETWEEN '2025-01-01' AND '2025-12-31 23:59:59'
          AND transaction_type = 1
          AND `business-unit` IN ({biz_filter})
    """)
    tx2 = cur.fetchall()
    tx2_by_id = {t["id"]: t for t in tx2}

    if tx2:
        tx2_ids = ",".join(str(t["id"]) for t in tx2)
        cur.execute(f"SELECT * FROM transaction_records WHERE transaction_id IN ({tx2_ids})")
        recs2 = cur.fetchall()

        hops2 = {}
        for r in recs2:
            key = f"{r['transaction_id']}_{r['journey_id']}"
            mat = materials_by_id.get(r["material"], {})
            hop = {**r}
            hop["mat_unit_weight"] = mat.get("unit_weight", 0)
            hop["fh_origin"] = tx2_by_id[r["transaction_id"]]["business-unit"]
            hops2[key] = hop

        nr2 = {k: v for k, v in hops2.items() if v["status"] != "rejected"}
        total2 = sum(float(r["quantity"] or 0) * float(r["mat_unit_weight"] or 0) for r in nr2.values())
        total2_abs = sum(abs(float(r["quantity"] or 0)) * float(r["mat_unit_weight"] or 0) for r in nr2.values())
        print(f"  Records: {len(recs2)}, Deduped: {len(hops2)}, Non-rejected: {len(nr2)}")
        print(f"  Total (raw qty): {total2:.2f} kg")
        print(f"  Total (abs qty): {total2_abs:.2f} kg")
        print(f"  Target: {TARGET:.2f} kg")
        print(f"  Raw match: {'YES' if abs(total2 - TARGET) < 0.1 else 'NO'} (diff={total2 - TARGET:+.2f})")
        print(f"  Abs match: {'YES' if abs(total2_abs - TARGET) < 0.1 else 'NO'} (diff={total2_abs - TARGET:+.2f})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
