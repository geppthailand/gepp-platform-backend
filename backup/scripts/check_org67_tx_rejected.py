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

# OLD: find transactions with status=rejected but having non-rejected records
mysql_cur.execute(f"""
    SELECT t.id AS tx_id, t.status AS tx_status,
           tr.id AS rec_id, tr.status AS rec_status, tr.quantity, tr.journey_id,
           tr.material, m.unit_weight, m.name_en, m.material_category_id
    FROM transactions t
    JOIN transaction_records tr ON tr.transaction_id = t.id
    JOIN materials m ON tr.material = m.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2021-01-01' AND t.transaction_date < '2026-01-01'
      AND t.status = 'rejected'
      AND tr.status != 'rejected'
""")
rows = mysql_cur.fetchall()
total = sum(float(r["quantity"]) * float(r["unit_weight"]) for r in rows)
print(f"OLD: Tx rejected but record NOT rejected: {len(rows)} records, total={total:.2f}")
for r in rows:
    w = float(r["quantity"]) * float(r["unit_weight"])
    print(f"  tx={r['tx_id']}(tx_status={r['tx_status']}), rec={r['rec_id']}(rec_status={r['rec_status']}), "
          f"mat={r['material']}({r['name_en']}), cat={r['material_category_id']}, w={w:.2f}")

# NEW: check same - transaction status vs record status
pg_cur.execute("""
    SELECT t.id AS tx_id, t.status AS tx_status,
           tr.id AS rec_id, tr.status AS rec_status, tr.migration_id,
           tr.origin_quantity, m.unit_weight, m.name_en, m.category_id,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transactions t
    JOIN transaction_records tr ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
      AND t.status = 'rejected'
      AND (tr.status != 'rejected' OR tr.status IS NULL)
""")
new_rows = pg_cur.fetchall()
new_total = sum(float(r["weight"]) for r in new_rows)
print(f"\nNEW: Tx rejected but record NOT rejected: {len(new_rows)} records, total={new_total:.2f}")
for r in new_rows:
    print(f"  tx={r['tx_id']}(tx_status={r['tx_status']}), rec={r['rec_id']}(rec_status={r['rec_status']}), "
          f"migration_id={r['migration_id']}, mat={r['name_en']}, cat={r['category_id']}, w={float(r['weight']):.2f}")

mysql_conn.close()
pg_conn.close()
