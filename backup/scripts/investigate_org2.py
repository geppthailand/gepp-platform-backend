"""
Investigate which business-units from old org=443 map to new org=125.
Then compare totals for those specific business-units.
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

    # 1. Get all new records with migration_id for org 125 in 2023
    print("Getting new records (org=125, 2023) with migration_id...")
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL
          AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s
          AND tr.transaction_date <= %s
          AND tr.migration_id IS NOT NULL
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    new_records = pg_cur.fetchall()
    migration_ids = [r["migration_id"] for r in new_records]
    print(f"  Found {len(migration_ids)} new records with migration_id")

    if not migration_ids:
        print("No migration_ids found!")
        return

    # 2. Look up which business-units these old records belong to
    placeholders = ",".join(["%s"] * len(migration_ids))
    mysql_cur.execute(f"""
        SELECT DISTINCT t.`business-unit` AS biz_unit
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE tr.id IN ({placeholders})
    """, migration_ids)
    biz_units = [r["biz_unit"] for r in mysql_cur.fetchall()]
    print(f"  These map to old business-units: {biz_units}")

    # 3. Now compute old total weight for ONLY these business-units in 2023
    if not biz_units:
        print("No business units found!")
        return

    bu_placeholders = ",".join(["%s"] * len(biz_units))
    print(f"\nFetching OLD records for business-units {biz_units}, org={OLD_ORG}, 2023...")
    mysql_cur.execute(f"""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`,
               m.unit_weight, m.calc_ghg, m.name_en AS mat_name, m.material_category_id,
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
          AND t.`business-unit` IN ({bu_placeholders})
    """, [OLD_ORG, DATE_FROM, DATE_TO] + biz_units)
    old_all = mysql_cur.fetchall()
    print(f"  Raw old records: {len(old_all)}")

    # Apply last-hop dedup
    last_hops = {}
    for r in old_all:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r

    # Filter non-rejected
    old_records = {r["rec_id"]: r for r in last_hops.values() if r["rec_status"] != "rejected"}

    old_total_weight = 0.0
    old_weights = {}
    for rec_id, r in old_records.items():
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        old_weights[rec_id] = {
            "qty": qty, "uw": uw, "weight": w, "status": r["rec_status"],
            "mat_name": r["mat_name"], "biz_unit": r["biz_unit"],
            "tx_date": str(r["transaction_date"]),
        }
        old_total_weight += w

    print(f"  After dedup: {len(last_hops)}, after reject filter: {len(old_records)}")
    print(f"  Old total weight (filtered biz-units): {old_total_weight:.2f} kg")

    # 4. Get new total weight
    pg_cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL
          AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s
          AND tr.transaction_date <= %s
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    new_total = float(pg_cur.fetchone()["total_weight"] or 0)
    print(f"  New total weight: {new_total:.2f} kg")
    print(f"\n  DIFFERENCE: {new_total - old_total_weight:+.2f} kg")

    # 5. Now do detailed comparison — find what's different
    print(f"\n{'='*80}")
    print("DETAILED COMPARISON")
    print(f"{'='*80}")

    # Build new weights map
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity,
               tr.material_id, tr.status AS rec_status,
               tr.transaction_date AS rec_tx_date,
               m.unit_weight, m.calc_ghg, m.name_en AS mat_name
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL
          AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= %s
          AND tr.transaction_date <= %s
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    new_all = pg_cur.fetchall()

    new_by_migration_id = {}
    new_weights = {}
    new_without_migration = []
    new_total_weight = 0.0
    for r in new_all:
        qty = float(r["origin_quantity"] or 0)
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        rec_id = r["rec_id"]
        mig_id = r["migration_id"]
        new_weights[rec_id] = {
            "qty": qty, "uw": uw, "weight": w,
            "migration_id": mig_id, "status": r["rec_status"],
            "mat_name": r["mat_name"], "tx_date": str(r["rec_tx_date"]),
        }
        new_total_weight += w
        if mig_id:
            new_by_migration_id[mig_id] = rec_id
        else:
            new_without_migration.append(rec_id)

    # A. Records in new but not matching old (extras)
    extra_in_new = []
    extra_weight = 0.0
    for new_id in new_without_migration:
        nw = new_weights[new_id]
        extra_in_new.append({"new_id": new_id, **nw})
        extra_weight += nw["weight"]
    for mig_id, new_id in new_by_migration_id.items():
        if mig_id not in old_weights:
            nw = new_weights[new_id]
            extra_in_new.append({"new_id": new_id, "old_id": mig_id, **nw})
            extra_weight += nw["weight"]

    # B. Records in old but missing in new
    missing_in_new = []
    missing_weight = 0.0
    for old_id, ow in old_weights.items():
        if old_id not in new_by_migration_id:
            missing_in_new.append({"old_id": old_id, **ow})
            missing_weight += ow["weight"]

    # C. Matched with weight diff
    weight_diffs = []
    for old_id, ow in old_weights.items():
        if old_id in new_by_migration_id:
            new_id = new_by_migration_id[old_id]
            nw = new_weights[new_id]
            diff = nw["weight"] - ow["weight"]
            if abs(diff) > 0.01:
                weight_diffs.append({
                    "old_id": old_id, "new_id": new_id,
                    "old_w": ow["weight"], "new_w": nw["weight"], "diff": diff,
                    "old_qty": ow["qty"], "new_qty": nw["qty"],
                    "old_uw": ow["uw"], "new_uw": nw["uw"],
                    "mat": ow.get("mat_name", "?"),
                })

    diff_total = sum(d["diff"] for d in weight_diffs)

    print(f"\nA. EXTRA IN NEW (not in old for these biz-units): {len(extra_in_new)} records, weight={extra_weight:.2f} kg")
    for r in sorted(extra_in_new, key=lambda x: -x["weight"])[:20]:
        old_id = r.get("old_id", "N/A")
        # If old_id is known, check why it's not in our old results
        reason = ""
        if old_id != "N/A":
            mysql_cur.execute("""
                SELECT t.`business-unit`, t.transaction_type, t.transaction_date, tr.status
                FROM transaction_records tr
                JOIN transactions t ON tr.transaction_id = t.id
                WHERE tr.id = %s
            """, (old_id,))
            check = mysql_cur.fetchone()
            if check:
                reason = f"biz_unit={check['business-unit']}, tx_type={check['transaction_type']}, date={check['transaction_date']}, status={check['status']}"
            else:
                reason = "NOT FOUND in old DB"
        print(f"   new_id={r['new_id']}, old_id={old_id}, weight={r['weight']:.2f}, "
              f"mat={r.get('mat_name','?')}, date={r.get('tx_date','?')}")
        if reason:
            print(f"     -> {reason}")

    print(f"\nB. IN OLD BUT MISSING IN NEW: {len(missing_in_new)} records, weight={missing_weight:.2f} kg")
    for r in sorted(missing_in_new, key=lambda x: -x["weight"])[:20]:
        print(f"   old_id={r['old_id']}, weight={r['weight']:.2f}, "
              f"mat={r.get('mat_name','?')}, biz_unit={r.get('biz_unit','?')}, date={r.get('tx_date','?')}")

    print(f"\nC. MATCHED WITH WEIGHT DIFF: {len(weight_diffs)} records, total diff={diff_total:.2f} kg")
    for d in sorted(weight_diffs, key=lambda x: -abs(x["diff"]))[:20]:
        reason = []
        if abs(d["old_qty"] - d["new_qty"]) > 0.001:
            reason.append(f"qty:{d['old_qty']:.4f}->{d['new_qty']:.4f}")
        if abs(d["old_uw"] - d["new_uw"]) > 0.001:
            reason.append(f"uw:{d['old_uw']:.3f}->{d['new_uw']:.3f}")
        print(f"   old_id={d['old_id']}, new_id={d['new_id']}, "
              f"old_w={d['old_w']:.2f}, new_w={d['new_w']:.2f}, diff={d['diff']:+.2f}, "
              f"{', '.join(reason) or 'rounding?'}, mat={d['mat']}")

    # SUMMARY
    print(f"\n{'='*80}")
    print(f"SUMMARY (old biz-units={biz_units}):")
    print(f"  Old total: {old_total_weight:.2f} kg ({len(old_records)} records)")
    print(f"  New total: {new_total_weight:.2f} kg ({len(new_all)} records)")
    print(f"  Diff:      {new_total_weight - old_total_weight:+.2f} kg")
    print(f"  Extra in new:    +{extra_weight:.2f} kg ({len(extra_in_new)} records)")
    print(f"  Missing in new:  -{missing_weight:.2f} kg ({len(missing_in_new)} records)")
    print(f"  Weight diffs:    {diff_total:+.2f} kg ({len(weight_diffs)} records)")
    print(f"  Net explained:   {extra_weight - missing_weight + diff_total:+.2f} kg")
    print(f"  Actual diff:     {new_total_weight - old_total_weight:+.2f} kg")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
