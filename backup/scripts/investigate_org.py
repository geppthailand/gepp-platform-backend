"""
Investigate Total Waste difference for org old=443 / new=125.
Year 2023 (1 Jan 2023 - 31 Dec 2023)
Old total: 526,992.71  New total: 527,569.71  Diff: +577.00

Strategy:
1. Get old records with transaction_date in 2023, apply last-hop dedup, filter non-rejected
2. Get new records with transaction_date in 2023, filter non-rejected
3. Match by migration_id and find differences
"""

import pymysql
import psycopg2
import psycopg2.extras
from decimal import Decimal

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

    # ========== OLD: Get records for org 443, year 2023 ==========
    # Old report filters on Transaction.transaction_date
    print(f"Fetching OLD records (org={OLD_ORG}, transaction_type=1, date={DATE_FROM} to {DATE_TO})...")
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.price, tr.status AS rec_status,
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
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    old_all = mysql_cur.fetchall()
    print(f"  Raw old records (before dedup): {len(old_all)}")

    # Apply last-hop dedup (same as reportUtils.get_filtered_transactions)
    last_hops = {}
    for r in old_all:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r  # later records overwrite earlier ones

    # Filter non-rejected
    old_records = {r["rec_id"]: r for r in last_hops.values() if r["rec_status"] != "rejected"}

    old_total_weight = 0.0
    old_total_ghg = 0.0
    old_weights = {}
    for rec_id, r in old_records.items():
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["unit_weight"] or 0)
        ghg = float(r["calc_ghg"] or 0)
        w = qty * uw
        old_weights[rec_id] = {
            "qty": qty, "uw": uw, "weight": w, "ghg": w * ghg,
            "status": r["rec_status"], "mat_name": r["mat_name"],
            "tx_date": str(r["transaction_date"]),
        }
        old_total_weight += w
        old_total_ghg += w * ghg

    print(f"  After last-hop dedup: {len(last_hops)} unique journey keys")
    print(f"  After non-rejected filter: {len(old_records)}")
    deduped_count = len(old_all) - len(last_hops)
    print(f"  Deduped out: {deduped_count}")
    rejected_count = len(last_hops) - len(old_records)
    print(f"  Rejected: {rejected_count}")
    print(f"  Old total weight: {old_total_weight:.2f} kg")
    print(f"  Old total GHG:    {old_total_ghg:.2f} kgCO2e")

    # ========== NEW: Get records for org 125, year 2023 ==========
    # New report filters on TransactionRecord.transaction_date
    print(f"\nFetching NEW records (org={NEW_ORG}, date={DATE_FROM} to {DATE_TO})...")
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity, tr.origin_weight_kg,
               tr.material_id, tr.status AS rec_status, tr.created_transaction_id,
               tr.transaction_date AS rec_tx_date,
               m.unit_weight, m.calc_ghg, m.name_en AS mat_name,
               t.status AS tx_status, t.organization_id
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

    new_total_weight = 0.0
    new_total_ghg = 0.0
    new_by_migration_id = {}
    new_without_migration = []
    new_weights = {}
    for r in new_all:
        qty = float(r["origin_quantity"] or 0)
        uw = float(r["unit_weight"] or 0)
        ghg = float(r["calc_ghg"] or 0)
        w = qty * uw
        rec_id = r["rec_id"]
        mig_id = r["migration_id"]
        new_weights[rec_id] = {
            "qty": qty, "uw": uw, "weight": w, "ghg": w * ghg,
            "migration_id": mig_id, "status": r["rec_status"],
            "mat_name": r["mat_name"], "tx_date": str(r["rec_tx_date"]),
        }
        new_total_weight += w
        new_total_ghg += w * ghg
        if mig_id:
            new_by_migration_id[mig_id] = rec_id
        else:
            new_without_migration.append(rec_id)

    print(f"  Total new records (non-rejected, 2023): {len(new_all)}")
    print(f"  New total weight: {new_total_weight:.2f} kg")
    print(f"  New total GHG:    {new_total_ghg:.2f} kgCO2e")
    print(f"  Records without migration_id: {len(new_without_migration)}")
    print(f"  Records with migration_id: {len(new_by_migration_id)}")

    # ========== COMPARE ==========
    print(f"\n{'='*80}")
    print(f"DIFFERENCE: {new_total_weight - old_total_weight:+.2f} kg "
          f"(old={old_total_weight:.2f}, new={new_total_weight:.2f})")
    print(f"GHG DIFF:   {new_total_ghg - old_total_ghg:+.2f} kgCO2e "
          f"(old={old_total_ghg:.2f}, new={new_total_ghg:.2f})")
    print(f"{'='*80}")

    # A. Records in NEW but not in OLD (extras — no migration_id)
    extra_in_new = []
    extra_weight = 0.0
    for new_id in new_without_migration:
        nw = new_weights[new_id]
        extra_in_new.append({"new_id": new_id, **nw})
        extra_weight += nw["weight"]

    # B. Migrated records in NEW that point to old IDs NOT in old_records (2023 filtered)
    migrated_but_not_in_old = []
    migrated_extra_weight = 0.0
    for mig_id, new_id in new_by_migration_id.items():
        if mig_id not in old_weights:
            nw = new_weights[new_id]
            migrated_but_not_in_old.append({"new_id": new_id, "old_id": mig_id, **nw})
            migrated_extra_weight += nw["weight"]

    print(f"\nA. EXTRA IN NEW (no migration_id): {len(extra_in_new)} records, weight={extra_weight:.2f} kg")
    if extra_in_new:
        for r in sorted(extra_in_new, key=lambda x: -x["weight"])[:20]:
            print(f"   new_id={r['new_id']}, weight={r['weight']:.2f}, "
                  f"mat={r.get('mat_name','?')}, status={r['status']}, date={r.get('tx_date','?')}")
        if len(extra_in_new) > 20:
            print(f"   ... and {len(extra_in_new)-20} more")

    print(f"\nB. MIGRATED BUT NOT IN OLD REPORT (2023): {len(migrated_but_not_in_old)} records, weight={migrated_extra_weight:.2f} kg")
    if migrated_but_not_in_old:
        # Check why they're not in old
        for r in sorted(migrated_but_not_in_old, key=lambda x: -x["weight"])[:30]:
            old_id = r["old_id"]
            old_raw = None
            for o in old_all:
                if o["rec_id"] == old_id:
                    old_raw = o
                    break
            reason = "not in old query (wrong tx_type/org/date or deleted)"
            if old_raw:
                if old_raw["rec_status"] == "rejected":
                    reason = "rejected in old"
                else:
                    key = f"{old_raw['transaction_id']}_{old_raw['journey_id']}"
                    if key in last_hops and last_hops[key]["rec_id"] != old_id:
                        reason = f"last-hop dedup (kept rec_id={last_hops[key]['rec_id']})"
                    else:
                        reason = f"old_status={old_raw['rec_status']}, tx_status={old_raw['tx_status']}"
            else:
                # Check if it exists in old DB at all (without date filter)
                mysql_cur.execute("""
                    SELECT tr.id, tr.status, t.transaction_date, t.transaction_type, t.organization
                    FROM transaction_records tr
                    JOIN transactions t ON tr.transaction_id = t.id
                    WHERE tr.id = %s
                """, (old_id,))
                old_check = mysql_cur.fetchone()
                if old_check:
                    reason = (f"exists in old but excluded: tx_type={old_check['transaction_type']}, "
                              f"org={old_check['organization']}, date={old_check['transaction_date']}, "
                              f"status={old_check['status']}")
                else:
                    reason = "old record NOT found in old DB"
            print(f"   new_id={r['new_id']}, old_id={old_id}, weight={r['weight']:.2f}, "
                  f"mat={r.get('mat_name','?')}, date={r.get('tx_date','?')}, reason={reason}")
        if len(migrated_but_not_in_old) > 30:
            print(f"   ... and {len(migrated_but_not_in_old)-30} more")

    # C. Records in OLD but not in NEW (missing)
    missing_in_new = []
    missing_weight = 0.0
    for old_id, ow in old_weights.items():
        if old_id not in new_by_migration_id:
            missing_in_new.append({"old_id": old_id, **ow})
            missing_weight += ow["weight"]

    print(f"\nC. IN OLD BUT MISSING IN NEW: {len(missing_in_new)} records, weight={missing_weight:.2f} kg")
    if missing_in_new:
        for r in sorted(missing_in_new, key=lambda x: -x["weight"])[:20]:
            print(f"   old_id={r['old_id']}, weight={r['weight']:.2f}, mat={r.get('mat_name','?')}, "
                  f"status={r['status']}, date={r.get('tx_date','?')}")
        if len(missing_in_new) > 20:
            print(f"   ... and {len(missing_in_new)-20} more")

    # D. Matched records with weight difference
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
    print(f"\nD. MATCHED WITH WEIGHT DIFF: {len(weight_diffs)} records, total diff={diff_total:.2f} kg")
    if weight_diffs:
        print(f"   {'old_id':>8} | {'new_id':>8} | {'old_w':>10} | {'new_w':>10} | {'diff':>10} | reason")
        print("   " + "-" * 90)
        for d in sorted(weight_diffs, key=lambda x: -abs(x["diff"]))[:30]:
            reason = []
            if abs(d["old_qty"] - d["new_qty"]) > 0.001:
                reason.append(f"qty:{d['old_qty']:.4f}->{d['new_qty']:.4f}")
            if abs(d["old_uw"] - d["new_uw"]) > 0.001:
                reason.append(f"uw:{d['old_uw']:.3f}->{d['new_uw']:.3f}")
            print(f"   {d['old_id']:>8} | {d['new_id']:>8} | {d['old_w']:>10.2f} | {d['new_w']:>10.2f} | "
                  f"{d['diff']:>+10.2f} | {', '.join(reason) or 'rounding?'} | {d['mat']}")
        if len(weight_diffs) > 30:
            print(f"   ... and {len(weight_diffs)-30} more")

    # E. Check date boundary mismatches — records in new with dates just outside 2023 in old
    print(f"\n{'='*80}")
    print("E. DATE BOUNDARY CHECK — new records in 2023 whose old record has different date")
    print("=" * 80)
    date_mismatches = []
    for mig_id, new_id in new_by_migration_id.items():
        if mig_id in old_weights:
            continue  # already matched, no issue
        # This new record (in 2023) maps to old record NOT in our 2023 old query
        # Check what date the old record has
        mysql_cur.execute("""
            SELECT tr.id, t.transaction_date, tr.status, t.transaction_type
            FROM transaction_records tr
            JOIN transactions t ON tr.transaction_id = t.id
            WHERE tr.id = %s
        """, (mig_id,))
        old_check = mysql_cur.fetchone()
        if old_check and old_check["transaction_type"] == 1:
            date_mismatches.append({
                "new_id": new_id,
                "old_id": mig_id,
                "old_date": str(old_check["transaction_date"]),
                "new_date": new_weights[new_id]["tx_date"],
                "weight": new_weights[new_id]["weight"],
                "old_status": old_check["status"],
            })
    if date_mismatches:
        print(f"  Found {len(date_mismatches)} records where date differs:")
        for dm in sorted(date_mismatches, key=lambda x: -x["weight"])[:30]:
            print(f"   new_id={dm['new_id']}, old_id={dm['old_id']}, "
                  f"old_date={dm['old_date']}, new_date={dm['new_date']}, "
                  f"weight={dm['weight']:.2f}, old_status={dm['old_status']}")
    else:
        print("  No date boundary mismatches found.")

    # ========== SUMMARY ==========
    print(f"\n{'='*80}")
    print("SUMMARY — explains the {:.2f} kg difference:".format(new_total_weight - old_total_weight))
    print(f"  Extra in new (no migration_id):  +{extra_weight:.2f} kg ({len(extra_in_new)} records)")
    print(f"  Migrated but not in old report:  +{migrated_extra_weight:.2f} kg ({len(migrated_but_not_in_old)} records)")
    print(f"  Missing in new:                  -{missing_weight:.2f} kg ({len(missing_in_new)} records)")
    print(f"  Per-record weight diff:          {diff_total:+.2f} kg ({len(weight_diffs)} records)")
    print(f"  Net explained:                   {extra_weight + migrated_extra_weight - missing_weight + diff_total:+.2f} kg")
    print(f"  Actual difference:               {new_total_weight - old_total_weight:+.2f} kg")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
