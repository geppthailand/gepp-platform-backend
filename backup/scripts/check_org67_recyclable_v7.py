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

# Get all new recyclable records (cat 1) for org 67 with migration_id
pg_cur.execute("""
    SELECT tr.id, tr.migration_id, tr.origin_quantity, tr.material_id,
           m.unit_weight, m.name_en, m.category_id,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND m.category_id = 1
""")
new_recs = pg_cur.fetchall()
print(f"New recyclable records: {len(new_recs)}")

# For each new record, check what category the corresponding old record has
mismatch_count = 0
mismatch_weight = 0
for nr in new_recs:
    if nr["migration_id"]:
        old_rec_id = int(nr["migration_id"])
        mysql_cur.execute("""
            SELECT tr.id, tr.material, m.material_category_id, m.name_en
            FROM transaction_records tr
            JOIN materials m ON tr.material = m.id
            WHERE tr.id = %s
        """, (old_rec_id,))
        old_rec = mysql_cur.fetchone()
        if old_rec and old_rec["material_category_id"] != 1:
            w = float(nr["weight"])
            mismatch_count += 1
            mismatch_weight += w
            print(f"  MISMATCH: new_rec={nr['id']} (migration_id={nr['migration_id']}), "
                  f"new_mat={nr['material_id']}({nr['name_en']}) cat={nr['category_id']}, "
                  f"old_mat={old_rec['material']}({old_rec['name_en']}) old_cat={old_rec['material_category_id']}, "
                  f"weight={w:.2f}")

print(f"\nTotal mismatches: {mismatch_count}, total weight: {mismatch_weight:.2f}")

mysql_conn.close()
pg_conn.close()
