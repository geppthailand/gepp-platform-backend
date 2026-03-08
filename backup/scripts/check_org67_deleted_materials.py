import pymysql

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310, "user": "admin", "password": "GeppThailand123456$",
    "database": "Gepp_new", "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()

mysql_cur.execute("SELECT id FROM business_units WHERE organization = 384 AND deleted_date IS NULL")
biz_ids = [r["id"] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)

# Check: are there records referencing DELETED materials?
# The old report's fetchall for materials adds "AND deleted_date IS NULL"
# So deleted materials won't be in materials_by_id_prefix, causing KeyError
# Unless they're handled somehow

# Find records whose material has deleted_date IS NOT NULL
mysql_cur.execute(f"""
    SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status, tr.journey_id,
           tr.material, m.unit_weight, m.name_en, m.material_category_id, m.deleted_date AS mat_deleted
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2021-01-01' AND t.transaction_date < '2026-01-01'
      AND m.deleted_date IS NOT NULL
""")
deleted_mat_recs = mysql_cur.fetchall()
print(f"Records referencing DELETED materials: {len(deleted_mat_recs)}")
total_deleted = 0
for r in deleted_mat_recs:
    w = float(r["quantity"]) * float(r["unit_weight"])
    total_deleted += w
    print(f"  rec={r['rec_id']}, tx={r['transaction_id']}, mat={r['material']}({r['name_en']}), "
          f"cat={r['material_category_id']}, qty={r['quantity']}, w={w:.2f}, status={r['status']}, "
          f"mat_deleted={r['mat_deleted']}")
print(f"Total weight from deleted materials: {total_deleted:.2f}")

# Also check: materials with deleted_date set
mysql_cur.execute("""
    SELECT id, name_en, material_category_id, deleted_date, unit_weight
    FROM materials
    WHERE deleted_date IS NOT NULL
    ORDER BY id
""")
deleted_mats = mysql_cur.fetchall()
print(f"\nTotal deleted materials: {len(deleted_mats)}")
# Only show ones referenced by org 384 records
mat_ids_in_recs = set(r["material"] for r in deleted_mat_recs)
for m in deleted_mats:
    if m["id"] in mat_ids_in_recs:
        print(f"  id={m['id']}, name={m['name_en']}, cat={m['material_category_id']}, "
              f"deleted={m['deleted_date']}, unit_weight={m['unit_weight']}")

mysql_conn.close()
