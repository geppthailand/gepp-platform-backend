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

# OLD: all distinct record statuses and their counts/weights
mysql_cur.execute(f"""
    SELECT tr.status, COUNT(*) AS cnt,
           SUM(tr.quantity * m.unit_weight) AS total_w
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2021-01-01' AND t.transaction_date < '2026-01-01'
    GROUP BY tr.status
""")
print("OLD record statuses:")
for r in mysql_cur.fetchall():
    print(f"  status='{r['status']}': {r['cnt']} records, total={float(r['total_w']):.2f}")

# OLD: distinct transaction statuses
mysql_cur.execute(f"""
    SELECT t.status, COUNT(DISTINCT t.id) AS tx_cnt,
           COUNT(tr.id) AS rec_cnt,
           SUM(tr.quantity * m.unit_weight) AS total_w
    FROM transactions t
    JOIN transaction_records tr ON tr.transaction_id = t.id
    JOIN materials m ON tr.material = m.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2021-01-01' AND t.transaction_date < '2026-01-01'
    GROUP BY t.status
""")
print("\nOLD transaction statuses:")
for r in mysql_cur.fetchall():
    print(f"  tx_status='{r['status']}': {r['tx_cnt']} txs, {r['rec_cnt']} records, total={float(r['total_w']):.2f}")

# NEW: same checks
pg_cur.execute("""
    SELECT tr.status, COUNT(*) AS cnt,
           SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_w
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
    GROUP BY tr.status
""")
print("\nNEW record statuses:")
for r in pg_cur.fetchall():
    print(f"  status='{r['status']}': {r['cnt']} records, total={float(r['total_w']):.2f}")

pg_cur.execute("""
    SELECT t.status, COUNT(DISTINCT t.id) AS tx_cnt,
           COUNT(tr.id) AS rec_cnt,
           SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_w
    FROM transactions t
    JOIN transaction_records tr ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
    GROUP BY t.status
""")
print("\nNEW transaction statuses:")
for r in pg_cur.fetchall():
    print(f"  tx_status='{r['status']}': {r['tx_cnt']} txs, {r['rec_cnt']} records, total={float(r['total_w']):.2f}")

mysql_conn.close()
pg_conn.close()
