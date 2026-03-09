"""
Investigate the 94 kg category difference between General Waste and Waste To Energy
for org 459/141, year 2025.

Old report:  General=16,822.71  WTE=1,270.15
New report:  General=16,916.71  WTE=1,176.15
Diff: 94.00 moves from WTE to General in new report

Check how materials are categorized in both old and new systems.
"""

import pymysql
import psycopg2
import psycopg2.extras
from collections import defaultdict

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310,
    "user": "admin",
    "password": "GeppThailand123456$",
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


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # ===== OLD SYSTEM: How categories are used =====
    print("=" * 70)
    print("OLD SYSTEM: Material categories")
    mysql_cur.execute("SELECT id, name_en, name_th FROM material_categories WHERE deleted_date IS NULL ORDER BY id")
    old_cats = mysql_cur.fetchall()
    for c in old_cats:
        print(f"  cat_id={c['id']}: {c['name_en']} ({c['name_th']})")

    # Get all biz units for org 459
    mysql_cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (OLD_ORG,))
    biz_ids = [r['id'] for r in mysql_cur.fetchall()]
    biz_ids_str = ",".join([str(b) for b in biz_ids])

    # Get old report data (exact logic)
    mysql_cur.execute(f"""
        SELECT t.id FROM transactions t
        WHERE t.transaction_date BETWEEN '2025-01-01' AND '2025-12-31 23:59:59'
          AND t.transaction_type = 1
          AND t.`business-unit` IN ({biz_ids_str})
          AND t.deleted_date IS NULL
    """)
    tx_ids = [r['id'] for r in mysql_cur.fetchall()]
    tx_ids_str = ",".join([str(t) for t in tx_ids])

    mysql_cur.execute(f"""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status,
               tr.material, tr.journey_id,
               m.unit_weight, m.name_en AS mat_name, m.material_category_id AS cat_id,
               mc.name_en AS cat_name
        FROM transaction_records tr
        JOIN materials m ON tr.material = m.id
        LEFT JOIN material_categories mc ON m.material_category_id = mc.id
        WHERE tr.transaction_id IN ({tx_ids_str})
          AND tr.deleted_date IS NULL
    """)
    old_records = mysql_cur.fetchall()

    # Dedup
    last_hops = {}
    for r in old_records:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops[key] = r
    non_rej = [v for v in last_hops.values() if v['status'] != 'rejected']

    # Group by category
    print(f"\n{'='*70}")
    print(f"OLD SYSTEM: Category breakdown (org {OLD_ORG}, 2025)")
    by_cat = defaultdict(lambda: {"count": 0, "weight": 0.0, "materials": defaultdict(float)})
    for r in non_rej:
        w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
        cat = r['cat_name'] or f"cat_{r['cat_id']}"
        by_cat[cat]["count"] += 1
        by_cat[cat]["weight"] += w
        by_cat[cat]["materials"][r['mat_name']] += w

    total_old = 0
    for cat in sorted(by_cat, key=lambda c: -by_cat[c]["weight"]):
        total_old += by_cat[cat]["weight"]
        print(f"  {cat}: {by_cat[cat]['count']} recs, {by_cat[cat]['weight']:.2f} kg")
    print(f"  TOTAL: {total_old:.2f} kg")

    # ===== NEW SYSTEM: How categories are used =====
    print(f"\n{'='*70}")
    print("NEW SYSTEM: Material categories")
    pg_cur.execute("SELECT id, name_en, name_th FROM material_categories WHERE deleted_date IS NULL ORDER BY id")
    new_cats = pg_cur.fetchall()
    for c in new_cats:
        print(f"  cat_id={c['id']}: {c['name_en']} ({c['name_th']})")

    # Check GENERAL_WASTE main_material
    pg_cur.execute("SELECT id, name_en, code FROM main_materials WHERE code = 'GENERAL_WASTE'")
    gw_mm = pg_cur.fetchone()
    print(f"\nGENERAL_WASTE main_material: {dict(gw_mm) if gw_mm else 'NOT FOUND'}")
    gw_mm_id = gw_mm['id'] if gw_mm else None

    # Get new report data
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity AS qty,
               tr.status, tr.transaction_date,
               m.unit_weight, m.name_en AS mat_name,
               m.category_id AS mat_cat_id, m.main_material_id AS mat_mm_id,
               mc.name_en AS cat_name,
               mm.name_en AS mm_name, mm.code AS mm_code,
               tr.category_id AS rec_cat_id, tr.main_material_id AS rec_mm_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        LEFT JOIN material_categories mc ON m.category_id = mc.id
        LEFT JOIN main_materials mm ON m.main_material_id = mm.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2025-01-01' AND tr.transaction_date <= '2025-12-31 23:59:59'
    """, (NEW_ORG,))
    new_records = pg_cur.fetchall()

    # Group by category (raw, before WTE split)
    print(f"\n{'='*70}")
    print(f"NEW SYSTEM: Category breakdown BEFORE WTE split (org {NEW_ORG}, 2025)")
    by_cat_new = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in new_records:
        cat_id = r['mat_cat_id'] or r['rec_cat_id']
        cat_name = r['cat_name'] or f"cat_{cat_id}"
        w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
        by_cat_new[cat_name]["count"] += 1
        by_cat_new[cat_name]["weight"] += w

    total_new = 0
    for cat in sorted(by_cat_new, key=lambda c: -by_cat_new[c]["weight"]):
        total_new += by_cat_new[cat]["weight"]
        print(f"  {cat}: {by_cat_new[cat]['count']} recs, {by_cat_new[cat]['weight']:.2f} kg")
    print(f"  TOTAL: {total_new:.2f} kg")

    # Simulate WTE split
    print(f"\n{'='*70}")
    print("NEW SYSTEM: Simulating _split_waste_to_energy")

    # Build cat_mm_map
    cat_mm_map = defaultdict(float)
    material_map = defaultdict(float)
    for r in new_records:
        cat_id = r['mat_cat_id'] or r['rec_cat_id']
        mm_id = r['mat_mm_id'] or r['rec_mm_id']
        cat_name = r['cat_name'] or f"cat_{cat_id}"
        w = float(r['qty'] or 0) * float(r['unit_weight'] or 0)
        material_map[cat_name] += w
        if cat_id is not None and mm_id is not None:
            cat_mm_map[(int(cat_id), int(mm_id))] += w

    # Show all (cat_id=4, mm_id) pairs
    print(f"\nAll (cat_id=4, mm_id) pairs (General Waste sub-categories):")
    for (cid, mmid), w in sorted(cat_mm_map.items(), key=lambda x: -x[1]):
        if cid == 4:
            # Look up mm name
            pg_cur.execute("SELECT name_en, code FROM main_materials WHERE id = %s", (mmid,))
            mm_info = pg_cur.fetchone()
            mm_name = mm_info['name_en'] if mm_info else '?'
            mm_code = mm_info['code'] if mm_info else '?'
            is_gw = "<<< GENERAL_WASTE" if mmid == gw_mm_id else "-> WTE"
            print(f"  cat=4, mm_id={mmid} ({mm_name}, code={mm_code}): {w:.2f} kg {is_gw}")

    # Apply split
    wte_weight = 0.0
    for (cat_id, mm_id), weight in cat_mm_map.items():
        if cat_id == 4 and mm_id != gw_mm_id and weight > 0:
            wte_weight += weight

    print(f"\nWTE from General Waste split: {wte_weight:.2f} kg")

    # Check actual WTE category (cat_id=9)
    wte_cat_weight = 0.0
    for (cat_id, mm_id), weight in cat_mm_map.items():
        if cat_id == 9:
            wte_cat_weight += weight
    print(f"WTE from cat_id=9: {wte_cat_weight:.2f} kg")
    print(f"Total WTE: {wte_weight + wte_cat_weight:.2f} kg")

    gw_original = material_map.get('General Waste', 0) or material_map.get('ขยะทั่วไป', 0)
    print(f"\nGeneral Waste original: {gw_original:.2f}")
    print(f"General Waste after split: {gw_original - wte_weight:.2f}")

    # ===== Now check OLD system's category view =====
    print(f"\n{'='*70}")
    print("OLD SYSTEM: Detailed General Waste materials (cat_id=4 equivalent)")
    # Find which cat_id in old system maps to General Waste
    for r in non_rej:
        if r['cat_name'] and 'general' in r['cat_name'].lower():
            old_gw_cat_id = r['cat_id']
            break

    # Show materials under each category in old system
    by_cat_mat = defaultdict(lambda: defaultdict(float))
    for r in non_rej:
        w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
        cat = r['cat_name'] or f"cat_{r['cat_id']}"
        mat = r['mat_name']
        by_cat_mat[cat][mat] += w

    for cat in sorted(by_cat_mat, key=lambda c: -sum(by_cat_mat[c].values())):
        total = sum(by_cat_mat[cat].values())
        print(f"\n  {cat}: {total:.2f} kg")
        for mat in sorted(by_cat_mat[cat], key=lambda m: -by_cat_mat[cat][m]):
            if by_cat_mat[cat][mat] > 0.01:
                print(f"    {mat}: {by_cat_mat[cat][mat]:.2f} kg")

    # ===== Compare material-level between old and new =====
    print(f"\n{'='*70}")
    print("MATERIAL-LEVEL COMPARISON: Old vs New category assignment")

    # Build old material -> category mapping
    old_mat_cat = {}
    mysql_cur.execute("""
        SELECT m.id, m.name_en, m.material_category_id, mc.name_en AS cat_name, m.tags
        FROM materials m
        LEFT JOIN material_categories mc ON m.material_category_id = mc.id
        WHERE m.deleted_date IS NULL
    """)
    for r in mysql_cur.fetchall():
        old_mat_cat[r['id']] = {"name": r['name_en'], "cat_id": r['material_category_id'], "cat_name": r['cat_name'], "tags": r.get('tags')}

    # Build new material -> category mapping
    new_mat_cat = {}
    pg_cur.execute("""
        SELECT m.id, m.migration_id, m.name_en, m.category_id, mc.name_en AS cat_name,
               m.main_material_id, mm.name_en AS mm_name, mm.code AS mm_code
        FROM materials m
        LEFT JOIN material_categories mc ON m.category_id = mc.id
        LEFT JOIN main_materials mm ON m.main_material_id = mm.id
        WHERE m.deleted_date IS NULL
    """)
    for r in pg_cur.fetchall():
        mid = int(r['migration_id']) if r['migration_id'] else None
        if mid:
            new_mat_cat[mid] = {
                "new_id": r['id'], "name": r['name_en'],
                "cat_id": r['category_id'], "cat_name": r['cat_name'],
                "mm_id": r['main_material_id'], "mm_name": r['mm_name'], "mm_code": r['mm_code']
            }

    # Find materials where old cat != new cat (for materials used in 2025)
    used_materials = set(r['material'] for r in non_rej)
    print(f"\nMaterials with different categories between old and new:")
    for mat_id in sorted(used_materials):
        old = old_mat_cat.get(mat_id, {})
        new = new_mat_cat.get(mat_id, {})
        old_cat = old.get('cat_name', '?')
        new_cat = new.get('cat_name', '?')
        if old_cat != new_cat:
            # Get weight for this material
            mat_weight = sum(
                float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
                for r in non_rej if r['material'] == mat_id
            )
            print(f"  mat_id={mat_id} ({old.get('name', '?')}): "
                  f"old_cat='{old_cat}' -> new_cat='{new_cat}' "
                  f"(mm={new.get('mm_name', '?')}, code={new.get('mm_code', '?')}) "
                  f"weight={mat_weight:.2f} kg")

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
