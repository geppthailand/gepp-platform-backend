#!/usr/bin/env python3
"""
Diagnose missing 103 kg for UOB (old org=435, new org=117).
Compare MySQL vs PostgreSQL transaction_records quantities.
"""

import mysql.connector
import psycopg2
import psycopg2.extras

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
}

LOCAL_PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "postgres",
    "user": "geppsa-ard",
    "password": "",
}

OLD_ORG_ID = 435
NEW_ORG_ID = 117


def main():
    mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor(dictionary=True)

    pg_conn = psycopg2.connect(**LOCAL_PG_CONFIG)
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ====================================================================
    # 1. MySQL: Total quantity for UOB (org=435)
    # ====================================================================
    print("=" * 70)
    print(f"UOB - Old Org: {OLD_ORG_ID}, New Org: {NEW_ORG_ID}")
    print("=" * 70)

    # All active transaction_records for UOB's active transactions
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity)) as total_qty, COUNT(*) as cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.organization = %s
          AND t.is_active = 1 AND t.deleted_date IS NULL
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
    """, (OLD_ORG_ID,))
    mysql_total = mysql_cur.fetchone()
    print(f"\nMySQL (active tx + active records):")
    print(f"  Records: {mysql_total['cnt']}, Total quantity: {mysql_total['total_qty']}")

    # ====================================================================
    # 2. PostgreSQL: Total quantity for UOB (org=117)
    # ====================================================================
    pg_cur.execute("""
        SELECT SUM(origin_quantity) as total_qty, COUNT(*) as cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        WHERE t.organization_id = %s
          AND tr.migration_id IS NOT NULL
    """, (NEW_ORG_ID,))
    pg_total = pg_cur.fetchone()
    print(f"\nPostgreSQL (migrated records):")
    print(f"  Records: {pg_total['cnt']}, Total quantity: {pg_total['total_qty']}")

    diff_qty = float(mysql_total['total_qty'] or 0) - float(pg_total['total_qty'] or 0)
    diff_cnt = int(mysql_total['cnt'] or 0) - int(pg_total['cnt'] or 0)
    print(f"\nDifference: {diff_qty} kg, {diff_cnt} records")

    # ====================================================================
    # 3. Check: records skipped due to material mismatch
    # ====================================================================
    print(f"\n{'='*70}")
    print("Checking causes of missing records...")
    print("=" * 70)

    # Get material map (same logic as migration script)
    mysql_cur.execute("""
        SELECT id, name_en, name_th FROM materials
        WHERE is_active = 1 AND deleted_date IS NULL
    """)
    old_materials = {m["id"]: m for m in mysql_cur.fetchall()}

    pg_cur.execute("""
        SELECT id, name_en, name_th FROM materials
        WHERE is_active = TRUE AND deleted_date IS NULL
    """)
    new_materials = pg_cur.fetchall()
    new_by_name = {}
    for m in new_materials:
        name = (m["name_en"] or "").strip().lower()
        if name:
            new_by_name[name] = m

    matched_mat_ids = set()
    for om in old_materials.values():
        old_name = (om["name_en"] or "").strip().lower()
        if old_name in new_by_name:
            matched_mat_ids.add(om["id"])

    # Records with unmatched materials for UOB
    mysql_cur.execute("""
        SELECT tr.id, tr.material, tr.quantity, tr.journey_id, tr.transaction_id, tr.note
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.organization = %s
          AND t.is_active = 1 AND t.deleted_date IS NULL
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
        ORDER BY tr.id
    """, (OLD_ORG_ID,))
    uob_records = mysql_cur.fetchall()

    skipped_material = []
    for rec in uob_records:
        if rec["material"] not in matched_mat_ids:
            mat_info = old_materials.get(rec["material"], {})
            skipped_material.append({
                "id": rec["id"],
                "material_id": rec["material"],
                "material_name": mat_info.get("name_en", "???"),
                "quantity": float(rec["quantity"]),
                "transaction_id": rec["transaction_id"],
                "journey_id": rec["journey_id"],
                "note": rec["note"],
            })

    if skipped_material:
        total_skipped_qty = sum(r["quantity"] for r in skipped_material)
        print(f"\n[CAUSE 1] Records skipped due to UNMATCHED MATERIAL: {len(skipped_material)} records, {total_skipped_qty} kg")
        # Group by material
        by_mat = {}
        for r in skipped_material:
            key = (r["material_id"], r["material_name"])
            if key not in by_mat:
                by_mat[key] = {"count": 0, "qty": 0}
            by_mat[key]["count"] += 1
            by_mat[key]["qty"] += r["quantity"]
        for (mat_id, mat_name), info in sorted(by_mat.items()):
            print(f"  Material {mat_id} ({mat_name}): {info['count']} records, {info['qty']} kg")

        print(f"\n  Detail (each skipped record):")
        for r in skipped_material:
            print(f"    rec_id={r['id']} tx_id={r['transaction_id']} mat={r['material_id']}({r['material_name']}) qty={r['quantity']} note={r['note']}")
    else:
        print("\n[CAUSE 1] No records skipped due to unmatched materials")

    # ====================================================================
    # 4. Check: records lost to deduplication
    # ====================================================================
    mysql_cur.execute("""
        SELECT tr.id, tr.transaction_id, tr.journey_id, tr.quantity, tr.material, tr.note
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.organization = %s
          AND t.is_active = 1 AND t.deleted_date IS NULL
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
        ORDER BY tr.transaction_id, tr.journey_id, tr.id
    """, (OLD_ORG_ID,))
    all_uob = mysql_cur.fetchall()

    seen = set()
    deduped = []
    for rec in all_uob:
        key = (rec["transaction_id"], rec["journey_id"])
        if key in seen:
            deduped.append(rec)
        else:
            seen.add(key)

    if deduped:
        total_dedup_qty = sum(abs(float(r["quantity"])) for r in deduped)
        print(f"\n[CAUSE 2] Records lost to DEDUPLICATION: {len(deduped)} records, {total_dedup_qty} kg")
        for r in deduped:
            mat_info = old_materials.get(r["material"], {})
            print(f"    rec_id={r['id']} tx_id={r['transaction_id']} journey={r['journey_id']} "
                  f"mat={r['material']}({mat_info.get('name_en','???')}) qty={r['quantity']} note={r['note']}")
    else:
        print("\n[CAUSE 2] No records lost to deduplication")

    # ====================================================================
    # 5. Check: quantity comparison per-record (abs vs raw)
    # ====================================================================
    # Migration uses abs(quantity), check if any negative quantities exist
    mysql_cur.execute("""
        SELECT COUNT(*) as cnt, SUM(tr.quantity) as raw_sum, SUM(ABS(tr.quantity)) as abs_sum
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.organization = %s
          AND t.is_active = 1 AND t.deleted_date IS NULL
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.quantity < 0
    """, (OLD_ORG_ID,))
    neg = mysql_cur.fetchone()
    if neg["cnt"] > 0:
        print(f"\n[INFO] Records with NEGATIVE quantity: {neg['cnt']} records")
        print(f"  Raw sum of negatives: {neg['raw_sum']}, Abs sum: {neg['abs_sum']}")
        print(f"  Migration uses ABS(), so these become positive → adds {float(neg['abs_sum']) + float(neg['raw_sum'])} extra kg")

    # ====================================================================
    # 6. Final reconciliation
    # ====================================================================
    print(f"\n{'='*70}")
    print("RECONCILIATION")
    print("=" * 70)

    mysql_qty = float(mysql_total['total_qty'] or 0)
    pg_qty = float(pg_total['total_qty'] or 0)
    mat_lost = sum(r["quantity"] for r in skipped_material) if skipped_material else 0
    dedup_lost = sum(abs(float(r["quantity"])) for r in deduped) if deduped else 0

    print(f"MySQL total qty (ABS):      {mysql_qty:.2f} kg")
    print(f"PG migrated qty:            {pg_qty:.2f} kg")
    print(f"Difference:                 {mysql_qty - pg_qty:.2f} kg")
    print(f"")
    print(f"Explained losses:")
    print(f"  Unmatched materials:      {mat_lost:.2f} kg")
    print(f"  Deduplication:            {dedup_lost:.2f} kg")
    print(f"  Total explained:          {mat_lost + dedup_lost:.2f} kg")
    unexplained = (mysql_qty - pg_qty) - (mat_lost + dedup_lost)
    if abs(unexplained) > 0.01:
        print(f"  Unexplained:              {unexplained:.2f} kg")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
