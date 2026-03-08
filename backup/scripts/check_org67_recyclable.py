import pymysql
import psycopg2
import psycopg2.extras

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310, "user": "admin", "password": "GeppThailand123456$",
    "database": "Gepp_new", "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}
PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()
pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

mysql_cur.execute("SELECT id FROM business_units WHERE organization = 384 AND deleted_date IS NULL")
biz_ids = [r["id"] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)

# OLD recyclables with journey dedup
mysql_cur.execute(f"""
    SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status, tr.journey_id,
           tr.material, m.unit_weight, m.name_en, m.material_category_id
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND m.material_category_id = 1
""")
rows = mysql_cur.fetchall()
hops = {}
for r in rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    hops[key] = r

old_by_mat = {}
for v in hops.values():
    if v["status"] != "rejected":
        w = float(v["quantity"]) * float(v["unit_weight"])
        mid = v["material"]
        old_by_mat[mid] = old_by_mat.get(mid, 0) + w

old_total = sum(old_by_mat.values())
print(f"OLD Recyclable total: {old_total:.2f}")

# NEW recyclables by material
pg_cur.execute("""
    SELECT m.id AS mat_id, SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_w
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL) AND t.migration_id IS NOT NULL
      AND m.category_id = 1
    GROUP BY m.id
""")
new_by_mat = {}
for r in pg_cur.fetchall():
    new_by_mat[r["mat_id"]] = float(r["total_w"])
new_total = sum(new_by_mat.values())
print(f"NEW Recyclable total: {new_total:.2f}")
print(f"Diff: {new_total - old_total:+.2f}")

# Find diffs
all_mats = set(old_by_mat.keys()) | set(new_by_mat.keys())
for mid in sorted(all_mats):
    ow = old_by_mat.get(mid, 0)
    nw = new_by_mat.get(mid, 0)
    if abs(ow - nw) > 0.01:
        pg_cur.execute("SELECT name_en FROM materials WHERE id = %s", (mid,))
        name_r = pg_cur.fetchone()
        name = name_r["name_en"] if name_r else "?"
        print(f"  mat={mid} ({name}): old={ow:.2f}, new={nw:.2f}, diff={nw-ow:+.2f}")

mysql_conn.close()
pg_conn.close()
