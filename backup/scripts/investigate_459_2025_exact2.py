"""
Reproduce EXACT old report logic for org 459, year 2025.
Key differences found:
1. Old report filters by business-unit IN (org's biz units), NOT by t.organization
2. Old report has NO is_active filter on records (only deleted_date IS NULL from fetchall)
3. Old report uses quantity * unit_weight (no ABS)
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

    # Step 1: Get all business units for org 459 (same as old report)
    cur.execute("""
        SELECT * FROM business_units
        WHERE organization = %s AND deleted_date IS NULL
    """, (OLD_ORG,))
    biz_units = cur.fetchall()
    biz_unit_ids = [b['id'] for b in biz_units]
    print(f"Org {OLD_ORG} has {len(biz_unit_ids)} business units: {biz_unit_ids}")

    # Step 2: Old report date range (with -7h timezone shift)
    # User selects 2025-01-01 to 2025-12-31
    # Old code: start_date = 2025-01-01 00:00:00 - 7h = 2024-12-31 17:00:00
    #           end_date   = 2025-12-31 00:00:00 - 7h = 2025-12-30 17:00:00
    OLD_START = "2024-12-31 17:00:00"
    OLD_END = "2025-12-30 17:00:00"

    # Also try without TZ shift
    NO_TZ_START = "2025-01-01"
    NO_TZ_END = "2025-12-31 23:59:59"

    biz_ids_str = ",".join([str(b) for b in biz_unit_ids])

    # ===== EXACT OLD REPORT LOGIC =====
    for label, start, end in [
        ("TZ-shifted (-7h)", OLD_START, OLD_END),
        ("No TZ shift", NO_TZ_START, NO_TZ_END),
    ]:
        print(f"\n{'='*70}")
        print(f"=== {label}: {start} to {end} ===")

        # Query transactions (same as old report)
        # OLD: SELECT * FROM transactions WHERE transaction_date BETWEEN ... AND transaction_type = 1
        #      AND `business-unit` IN (...) AND deleted_date IS NULL
        cur.execute(f"""
            SELECT * FROM transactions
            WHERE `transaction_date` BETWEEN %s AND %s
              AND transaction_type = 1
              AND `business-unit` IN ({biz_ids_str})
              AND deleted_date IS NULL
        """, (start, end))
        transactions = cur.fetchall()
        tx_by_id = {t['id']: t for t in transactions}
        print(f"  Transactions: {len(transactions)}")

        # Check: any transactions NOT in org 459?
        other_org_tx = [t for t in transactions if t['organization'] != OLD_ORG]
        if other_org_tx:
            print(f"  *** Transactions from OTHER orgs: {len(other_org_tx)}")
            for t in other_org_tx[:10]:
                print(f"      tx_id={t['id']}, org={t['organization']}, biz={t['business-unit']}, date={t['transaction_date']}")

        if len(transactions) == 0:
            print("  No transactions found.")
            continue

        tx_ids_str = ",".join([str(t['id']) for t in transactions])

        # Query records (same as old report — NO is_active filter)
        # OLD: SELECT * FROM transaction_records WHERE transaction_id IN (...) AND deleted_date IS NULL
        cur.execute(f"""
            SELECT * FROM transaction_records
            WHERE transaction_id IN ({tx_ids_str})
              AND deleted_date IS NULL
        """)
        records = cur.fetchall()
        print(f"  Records (no is_active filter): {len(records)}")

        # Check records with is_active != 1
        inactive_recs = [r for r in records if r.get('is_active') != 1]
        if inactive_recs:
            print(f"  *** Records with is_active != 1: {len(inactive_recs)}")
            inactive_weight = 0
            for r in inactive_recs[:20]:
                cur.execute("SELECT unit_weight, name_en FROM materials WHERE id = %s", (r['material'],))
                mat = cur.fetchone()
                uw = float(mat['unit_weight'] or 0) if mat else 0
                w = float(r['quantity'] or 0) * uw
                inactive_weight += w
                print(f"      rec_id={r['id']}, tx_id={r['transaction_id']}, journey={r['journey_id']}, "
                      f"qty={r['quantity']}, uw={uw}, w={w:.2f}, is_active={r.get('is_active')}, "
                      f"mat={mat['name_en'] if mat else '?'}, status={r['status']}")
            print(f"      Total inactive weight (raw, no ABS): {inactive_weight:.2f}")

        # Get materials
        cur.execute("SELECT * FROM materials WHERE deleted_date IS NULL")
        materials = cur.fetchall()
        mat_by_id = {m['id']: m for m in materials}

        # Journey_id dedup (last record wins, same as old report)
        last_hops = {}
        for r in records:
            key = f"{r['transaction_id']}_{r['journey_id']}"
            merged = {**r, **{f"mat_{k}": v for k, v in mat_by_id.get(r['material'], {}).items()}}
            last_hops[key] = merged

        print(f"  After dedup: {len(last_hops)}")

        # Non-rejected
        non_rejected = {k: v for k, v in last_hops.items() if v['status'] != 'rejected'}
        rejected = {k: v for k, v in last_hops.items() if v['status'] == 'rejected'}
        print(f"  Non-rejected: {len(non_rejected)}, Rejected: {len(rejected)}")

        # Calculate net_weight EXACTLY as old report: quantity * mat_unit_weight (no ABS!)
        total_no_abs = sum(
            float(v['quantity'] or 0) * float(v.get('mat_unit_weight') or 0)
            for v in non_rejected.values()
        )
        total_with_abs = sum(
            abs(float(v['quantity'] or 0)) * float(v.get('mat_unit_weight') or 0)
            for v in non_rejected.values()
        )

        diff_no_abs = total_no_abs - TARGET
        diff_with_abs = total_with_abs - TARGET
        match_no_abs = "<<< MATCH" if abs(diff_no_abs) < 0.1 else ""
        match_with_abs = "<<< MATCH" if abs(diff_with_abs) < 0.1 else ""

        print(f"\n  Total (no ABS, like old report): {total_no_abs:.2f} kg (diff: {diff_no_abs:+.2f}) {match_no_abs}")
        print(f"  Total (with ABS):                {total_with_abs:.2f} kg (diff: {diff_with_abs:+.2f}) {match_with_abs}")

        # Also check: with is_active=1 filter (like my earlier queries)
        active_only = {k: v for k, v in non_rejected.items() if v.get('is_active') == 1}
        total_active = sum(
            abs(float(v['quantity'] or 0)) * float(v.get('mat_unit_weight') or 0)
            for v in active_only.values()
        )
        print(f"  Total (with is_active=1 + ABS):  {total_active:.2f} kg (diff: {total_active - TARGET:+.2f})")

    # ===== Compare: organization filter vs business-unit filter =====
    print(f"\n{'='*70}")
    print("=== Comparing: t.organization=459 vs t.business-unit IN (biz_ids) ===")

    # With org filter
    cur.execute("""
        SELECT t.id FROM transactions t
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND t.transaction_date >= '2025-01-01' AND t.transaction_date <= '2025-12-31 23:59:59'
          AND t.deleted_date IS NULL
    """, (OLD_ORG,))
    org_tx_ids = set(r['id'] for r in cur.fetchall())

    # With biz-unit filter
    cur.execute(f"""
        SELECT t.id FROM transactions t
        WHERE t.`business-unit` IN ({biz_ids_str})
          AND t.transaction_type = 1
          AND t.transaction_date >= '2025-01-01' AND t.transaction_date <= '2025-12-31 23:59:59'
          AND t.deleted_date IS NULL
    """)
    biz_tx_ids = set(r['id'] for r in cur.fetchall())

    only_org = org_tx_ids - biz_tx_ids
    only_biz = biz_tx_ids - org_tx_ids
    print(f"  Org filter: {len(org_tx_ids)} transactions")
    print(f"  Biz filter: {len(biz_tx_ids)} transactions")
    print(f"  Only in org filter: {len(only_org)}")
    print(f"  Only in biz filter: {len(only_biz)}")

    if only_biz:
        print(f"\n  Transactions in biz filter but NOT org filter:")
        for tx_id in sorted(only_biz):
            cur.execute("SELECT id, organization, `business-unit`, transaction_date FROM transactions WHERE id = %s", (tx_id,))
            t = cur.fetchone()
            print(f"    tx_id={t['id']}, org={t['organization']}, biz={t['business-unit']}, date={t['transaction_date']}")

    if only_org:
        print(f"\n  Transactions in org filter but NOT biz filter:")
        for tx_id in sorted(only_org)[:10]:
            cur.execute("SELECT id, organization, `business-unit`, transaction_date FROM transactions WHERE id = %s", (tx_id,))
            t = cur.fetchone()
            print(f"    tx_id={t['id']}, org={t['organization']}, biz={t['business-unit']}, date={t['transaction_date']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
