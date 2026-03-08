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

# Check what dates are stored for boundary records
# Old report with user dates 2021-01-01 to 2025-12-31:
#   query start: 2020-12-31 17:00:00 (subtracts 7h)
#   query end:   2025-12-31 16:59:59 (subtracts 7h from 2025-12-31 23:59:59)
# Actually - check what end_date the frontend sends. It might send just 2025-12-31

# Let me check records near boundaries in old MySQL
print("=== OLD: Records near end of 2025 (transaction_date) ===")
mysql_cur.execute(f"""
    SELECT t.id AS tx_id, t.transaction_date, tr.id AS rec_id, tr.quantity,
           m.unit_weight, m.material_category_id, m.name_en, tr.status
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2025-12-30' AND t.transaction_date <= '2025-12-31 23:59:59'
    ORDER BY t.transaction_date
""")
for r in mysql_cur.fetchall():
    w = float(r["quantity"]) * float(r["unit_weight"])
    print(f"  tx={r['tx_id']}, rec={r['rec_id']}, date={r['transaction_date']}, "
          f"mat={r['name_en']}, cat={r['material_category_id']}, w={w:.2f}, status={r['status']}")

print("\n=== OLD: Records near start of 2021 (transaction_date) ===")
mysql_cur.execute(f"""
    SELECT t.id AS tx_id, t.transaction_date, tr.id AS rec_id, tr.quantity,
           m.unit_weight, m.material_category_id, m.name_en, tr.status
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2020-12-31' AND t.transaction_date <= '2021-01-02'
    ORDER BY t.transaction_date
""")
for r in mysql_cur.fetchall():
    w = float(r["quantity"]) * float(r["unit_weight"])
    print(f"  tx={r['tx_id']}, rec={r['rec_id']}, date={r['transaction_date']}, "
          f"mat={r['name_en']}, cat={r['material_category_id']}, w={w:.2f}, status={r['status']}")

# Check same in new PG
print("\n=== NEW: Records near end of 2025 (transaction_date on record) ===")
pg_cur.execute("""
    SELECT t.id AS tx_id, tr.transaction_date AS tr_date, tr.id AS rec_id,
           tr.origin_quantity, m.unit_weight, m.category_id, m.name_en, tr.status
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND tr.transaction_date >= '2025-12-30' AND tr.transaction_date <= '2025-12-31 23:59:59'
    ORDER BY tr.transaction_date
""")
for r in pg_cur.fetchall():
    w = float(r["origin_quantity"]) * float(r["unit_weight"] or 0)
    print(f"  tx={r['tx_id']}, rec={r['rec_id']}, date={r['tr_date']}, "
          f"mat={r['name_en']}, cat={r['category_id']}, w={w:.2f}, status={r['status']}")

print("\n=== NEW: Records near start of 2021 ===")
pg_cur.execute("""
    SELECT t.id AS tx_id, tr.transaction_date AS tr_date, tr.id AS rec_id,
           tr.origin_quantity, m.unit_weight, m.category_id, m.name_en, tr.status
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND tr.transaction_date >= '2020-12-31' AND tr.transaction_date <= '2021-01-02'
    ORDER BY tr.transaction_date
""")
for r in pg_cur.fetchall():
    w = float(r["origin_quantity"]) * float(r["unit_weight"] or 0)
    print(f"  tx={r['tx_id']}, rec={r['rec_id']}, date={r['tr_date']}, "
          f"mat={r['name_en']}, cat={r['category_id']}, w={w:.2f}, status={r['status']}")

# Compare a few sample records' transaction_date between old and new
print("\n=== Sample date comparison ===")
pg_cur.execute("""
    SELECT tr.id, tr.migration_id, tr.transaction_date
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    WHERE t.organization_id = 67 AND t.migration_id IS NOT NULL
    ORDER BY tr.id LIMIT 5
""")
for r in pg_cur.fetchall():
    mysql_cur.execute("SELECT t.transaction_date FROM transaction_records tr JOIN transactions t ON tr.transaction_id = t.id WHERE tr.id = %s", (int(r["migration_id"]),))
    old = mysql_cur.fetchone()
    print(f"  rec migration_id={r['migration_id']}: old_tx_date={old['transaction_date'] if old else '?'}, new_tr_date={r['transaction_date']}")

mysql_conn.close()
pg_conn.close()
