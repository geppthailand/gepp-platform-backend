"""
Investigate Total Waste diff for org old=459 / new=141, year 2025.
Old report: 45,070.35  New: ?
My old DB query: 44,794.55 — need to find the missing 275.80 kg
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
DATE_FROM = "2025-01-01"
DATE_TO = "2025-12-31 23:59:59"


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # ========== OLD: Check without journey_id dedup ==========
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`, tr.is_active, tr.deleted_date AS rec_deleted,
               m.unit_weight, m.name_en AS mat_name,
               t.status AS tx_status, t.`business-unit` AS biz_unit, t.transaction_date,
               t.transaction_type, t.deleted_date AS tx_deleted
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    all_raw = mysql_cur.fetchall()

    print(f"ALL raw records (no filters): {len(all_raw)}")

    # Break down by transaction_type
    by_type = defaultdict(list)
    for r in all_raw:
        by_type[r["transaction_type"]].append(r)
    for t, recs in sorted(by_type.items()):
        total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in recs)
        print(f"  transaction_type={t}: {len(recs)} records, {total:.2f} kg")

    # Break down by is_active & deleted_date
    active_not_deleted = [r for r in all_raw if r["is_active"] == 1 and r["rec_deleted"] is None]
    inactive = [r for r in all_raw if r["is_active"] != 1]
    deleted = [r for r in all_raw if r["rec_deleted"] is not None]
    print(f"\n  active & not deleted: {len(active_not_deleted)}")
    print(f"  inactive: {len(inactive)}")
    print(f"  deleted: {len(deleted)}")

    # Filter: transaction_type=1, is_active=1, not deleted
    type1 = [r for r in all_raw if r["transaction_type"] == 1 and r["is_active"] == 1 and r["rec_deleted"] is None]
    print(f"\n  Type 1, active, not deleted: {len(type1)}")

    # With journey_id dedup
    last_hops = {}
    for r in type1:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r
    deduped = list(last_hops.values())
    non_rejected = [r for r in deduped if r["rec_status"] != "rejected"]
    rejected = [r for r in deduped if r["rec_status"] == "rejected"]

    dedup_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in deduped)
    non_rej_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in non_rejected)
    rej_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in rejected)

    print(f"\n  After journey_id dedup: {len(deduped)} records, {dedup_total:.2f} kg")
    print(f"  Non-rejected: {len(non_rejected)} records, {non_rej_total:.2f} kg")
    print(f"  Rejected: {len(rejected)} records, {rej_total:.2f} kg")

    # WITHOUT journey_id dedup
    no_dedup_non_rej = [r for r in type1 if r["rec_status"] != "rejected"]
    no_dedup_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in no_dedup_non_rej)
    print(f"\n  WITHOUT dedup, non-rejected: {len(no_dedup_non_rej)} records, {no_dedup_total:.2f} kg")

    # Check how many records have journey_id != NULL or duplicate keys
    journey_ids = [r["journey_id"] for r in type1]
    null_journey = sum(1 for j in journey_ids if j is None)
    print(f"\n  Records with NULL journey_id: {null_journey}")

    # Check if dedup removed anything
    if len(type1) != len(deduped):
        print(f"\n  DEDUP removed {len(type1) - len(deduped)} records:")
        dedup_keys = set()
        removed = []
        for r in type1:
            key = f"{r['transaction_id']}_{r['journey_id']}"
            if key in dedup_keys:
                removed.append(r)
            dedup_keys.add(key)
        for r in removed[:20]:
            qty = abs(float(r["quantity"] or 0))
            uw = float(r["unit_weight"] or 0)
            print(f"    rec_id={r['rec_id']}, tx_id={r['transaction_id']}, journey={r['journey_id']}, "
                  f"qty={qty}, uw={uw}, w={qty*uw:.2f}, mat={r['mat_name']}, biz={r['biz_unit']}")

    # Biz-unit breakdown (non-rejected, deduped)
    by_bu = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in non_rejected:
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["unit_weight"] or 0)
        by_bu[r["biz_unit"]]["count"] += 1
        by_bu[r["biz_unit"]]["weight"] += qty * uw

    print(f"\nOLD biz-unit breakdown (deduped, non-rejected):")
    for bu in sorted(by_bu, key=lambda b: -by_bu[b]["weight"]):
        print(f"  {bu}: {by_bu[bu]['count']} recs, {by_bu[bu]['weight']:.2f} kg")

    # ========== NEW: Check including soft-deleted ==========
    print(f"\n{'='*70}")
    print("NEW DB CHECKS")
    print(f"{'='*70}")

    # Active records
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
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    active = pg_cur.fetchone()
    print(f"\nActive (not deleted, not rejected): {active['cnt']} records, {float(active['total_weight'] or 0):.2f} kg")

    # Soft-deleted records
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity,
               tr.deleted_date AS rec_deleted, tr.status,
               tr.transaction_date,
               m.unit_weight, m.name_en AS mat_name,
               t.id AS tx_id, t.deleted_date AS tx_deleted, t.organization_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND (tr.deleted_date IS NOT NULL OR t.deleted_date IS NOT NULL)
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    deleted_new = pg_cur.fetchall()

    deleted_total = 0.0
    print(f"\nSoft-deleted records in new DB (2025): {len(deleted_new)}")
    for r in deleted_new:
        qty = float(r["origin_quantity"] or 0)
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        deleted_total += w
        reason = ""
        if r["rec_deleted"]:
            reason += f"rec_deleted={r['rec_deleted']}"
        if r["tx_deleted"]:
            reason += f" tx_deleted={r['tx_deleted']}"
        print(f"  rec_id={r['rec_id']}, migration_id={r['migration_id']}, weight={w:.2f}, "
              f"mat={r['mat_name']}, status={r['status']}, date={r['transaction_date']}, "
              f"tx_id={r['tx_id']} | {reason}")
    print(f"  Total deleted weight: {deleted_total:.2f} kg")

    # Rejected records
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity,
               tr.status, tr.transaction_date,
               m.unit_weight, m.name_en AS mat_name
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND tr.status = 'rejected'
          AND tr.transaction_date >= %s AND tr.transaction_date <= %s
    """, (NEW_ORG, DATE_FROM, DATE_TO))
    rejected_new = pg_cur.fetchall()
    rej_new_total = sum(float(r["origin_quantity"] or 0) * float(r["unit_weight"] or 0) for r in rejected_new)
    print(f"\nRejected records in new DB (2025): {len(rejected_new)}, {rej_new_total:.2f} kg")

    # ========== SUMMARY ==========
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"  Old report target:     45,070.35 kg")
    print(f"  Old DB (dedup, non-rej): {non_rej_total:.2f} kg")
    print(f"  New DB (active):       {float(active['total_weight'] or 0):.2f} kg")
    print(f"  New DB (deleted):      {deleted_total:.2f} kg")
    print(f"  New DB (active+del):   {float(active['total_weight'] or 0) + deleted_total:.2f} kg")
    print(f"  Diff (target - old DB): {45070.35 - non_rej_total:+.2f} kg")
    print(f"  Diff (target - new active): {45070.35 - float(active['total_weight'] or 0):+.2f} kg")

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
