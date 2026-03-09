"""
Compare ALL materials calc_ghg and unit_weight between old MySQL and remote PG.
Fix any mismatches.
"""

import pymysql
import psycopg2
import psycopg2.extras
import sys

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

DRY_RUN = "--apply" not in sys.argv


def main():
    if DRY_RUN:
        print("*** DRY RUN - pass --apply to actually fix ***\n")

    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # 1. All old materials
    mysql_cur.execute("""
        SELECT id, name_en, unit_weight, calc_ghg
        FROM materials WHERE is_active = 1 AND deleted_date IS NULL
    """)
    old_mats = {r["id"]: r for r in mysql_cur.fetchall()}

    # 2. All new materials
    pg_cur.execute("SELECT id, name_en, unit_weight, calc_ghg FROM materials WHERE is_active = TRUE")
    new_mats = {r["id"]: r for r in pg_cur.fetchall()}

    # 3. Compare materials that exist in BOTH (same ID)
    print("=" * 80)
    print("A. MATERIALS WITH SAME ID — calc_ghg or unit_weight MISMATCH")
    print("=" * 80)
    same_id_fixes = []
    for mid, old_m in old_mats.items():
        new_m = new_mats.get(mid)
        if not new_m:
            continue
        old_uw = float(old_m["unit_weight"] or 0)
        new_uw = float(new_m["unit_weight"] or 0)
        old_ghg = float(old_m["calc_ghg"] or 0)
        new_ghg = float(new_m["calc_ghg"] or 0)

        if abs(old_uw - new_uw) > 0.0001 or abs(old_ghg - new_ghg) > 0.0001:
            same_id_fixes.append({
                "id": mid,
                "name": old_m["name_en"],
                "old_uw": old_uw, "new_uw": new_uw,
                "old_ghg": old_ghg, "new_ghg": new_ghg,
            })

    print(f"  Found: {len(same_id_fixes)} mismatches\n")
    if same_id_fixes:
        print(f"  {'id':>6} | {'name':<35} | {'old_uw':>8} | {'new_uw':>8} | {'old_ghg':>8} | {'new_ghg':>8}")
        print("  " + "-" * 105)
        for m in same_id_fixes:
            uw_flag = " !!!" if abs(m["old_uw"] - m["new_uw"]) > 0.0001 else ""
            ghg_flag = " !!!" if abs(m["old_ghg"] - m["new_ghg"]) > 0.0001 else ""
            print(f"  {m['id']:>6} | {(m['name'] or '')[:35]:<35} | {m['old_uw']:>8.3f} | {m['new_uw']:>8.3f}{uw_flag:4} | {m['old_ghg']:>8.3f} | {m['new_ghg']:>8.3f}{ghg_flag}")

    # 4. Materials that exist in new but NOT in old (remapped during migration)
    print(f"\n{'=' * 80}")
    print("B. NEW MATERIALS (not in old DB) WITH NULL/0 unit_weight or calc_ghg")
    print("=" * 80)

    pg_cur.execute("""
        SELECT DISTINCT tr.material_id, m.name_en, m.unit_weight, m.calc_ghg
        FROM transaction_records tr
        JOIN materials m ON tr.material_id = m.id
        WHERE tr.migration_id IS NOT NULL
          AND m.id NOT IN %s
          AND (m.unit_weight IS NULL OR m.unit_weight = 0
               OR m.calc_ghg IS NULL)
    """, (tuple(old_mats.keys()) if old_mats else (0,),))
    remapped_broken = pg_cur.fetchall()

    remap_fixes = []
    for r in remapped_broken:
        mid = r["material_id"]
        # Trace to old material via migration_id
        pg_cur.execute("""
            SELECT migration_id FROM transaction_records
            WHERE material_id = %s AND migration_id IS NOT NULL LIMIT 1
        """, (mid,))
        sample = pg_cur.fetchone()
        if not sample:
            continue
        mysql_cur.execute("""
            SELECT m.id, m.name_en, m.unit_weight, m.calc_ghg
            FROM transaction_records tr
            JOIN materials m ON tr.material = m.id
            WHERE tr.id = %s
        """, (sample["migration_id"],))
        old_vals = mysql_cur.fetchone()
        if old_vals:
            remap_fixes.append({
                "new_mat_id": mid,
                "name": r["name_en"],
                "cur_uw": float(r["unit_weight"] or 0),
                "cur_ghg": float(r["calc_ghg"] or 0),
                "fix_uw": float(old_vals["unit_weight"] or 0),
                "fix_ghg": float(old_vals["calc_ghg"] or 0),
                "old_mat_id": old_vals["id"],
                "old_name": old_vals["name_en"],
            })

    print(f"  Found: {len(remap_fixes)} broken remapped materials\n")
    for rf in remap_fixes:
        print(f"  Material {rf['new_mat_id']:>4} ({rf['name']:<30}): "
              f"uw {rf['cur_uw']} -> {rf['fix_uw']}, ghg {rf['cur_ghg']} -> {rf['fix_ghg']}  "
              f"(from old #{rf['old_mat_id']} {rf['old_name']})")

    # 5. Count total affected records
    all_fix_ids = [f["id"] for f in same_id_fixes] + [f["new_mat_id"] for f in remap_fixes]
    if all_fix_ids:
        placeholders = ",".join(["%s"] * len(all_fix_ids))
        pg_cur.execute(f"""
            SELECT COUNT(*) as cnt FROM transaction_records
            WHERE material_id IN ({placeholders})
              AND (migration_id IS NOT NULL OR TRUE)
        """, all_fix_ids)
        total_affected = pg_cur.fetchone()["cnt"]
        print(f"\n  Total records using these materials: {total_affected}")

    # 6. Apply
    total_fixes = len(same_id_fixes) + len(remap_fixes)
    if total_fixes == 0:
        print("\nNothing to fix!")
    elif DRY_RUN:
        print(f"\n*** DRY RUN — {total_fixes} materials to fix. Run with --apply ***")
    else:
        print(f"\nApplying {total_fixes} fixes to REMOTE DB ({REMOTE_PG_CONFIG['host']})...")

        for f in same_id_fixes:
            pg_cur.execute("""
                UPDATE materials SET unit_weight = %s, calc_ghg = %s WHERE id = %s
            """, (f["old_uw"], f["old_ghg"], f["id"]))
            print(f"  [same-id] Fixed #{f['id']} ({f['name']}): "
                  f"uw={f['old_uw']}, ghg={f['old_ghg']}")

        for rf in remap_fixes:
            pg_cur.execute("""
                UPDATE materials SET unit_weight = %s, calc_ghg = %s WHERE id = %s
            """, (rf["fix_uw"], rf["fix_ghg"], rf["new_mat_id"]))
            print(f"  [remap]   Fixed #{rf['new_mat_id']} ({rf['name']}): "
                  f"uw={rf['fix_uw']}, ghg={rf['fix_ghg']}")

        pg_conn.commit()
        print(f"\nCommitted {total_fixes} material fixes.")

        # Verify
        print(f"\n{'=' * 80}")
        print("VERIFICATION")
        print("=" * 80)
        pg_cur.execute("""
            SELECT COUNT(*) as cnt
            FROM transaction_records tr
            JOIN materials m ON tr.material_id = m.id
            WHERE tr.migration_id IS NOT NULL
              AND (m.unit_weight IS NULL OR m.unit_weight = 0)
        """)
        print(f"  Records with 0/NULL unit_weight: {pg_cur.fetchone()['cnt']}")

        pg_cur.execute("""
            SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight,0) * COALESCE(m.calc_ghg,0)) as ghg
            FROM transaction_records tr
            LEFT JOIN materials m ON tr.material_id = m.id
            WHERE tr.migration_id IS NOT NULL
              AND (tr.status != 'rejected' OR tr.status IS NULL)
              AND tr.deleted_date IS NULL
        """)
        print(f"  Total GHG (migrated, non-rejected): {float(pg_cur.fetchone()['ghg'] or 0):.2f} kgCO2e")

    mysql_cur.close()
    mysql_conn.close()
    pg_cur.close()
    pg_conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
