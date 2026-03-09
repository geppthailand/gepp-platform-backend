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

# Get active biz unit IDs for org 384
mysql_cur.execute("SELECT id FROM business_units WHERE organization = 384 AND deleted_date IS NULL")
active_biz = set(r["id"] for r in mysql_cur.fetchall())

# Get ALL new recyclable records for org 67
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

# For each, check if old record would be included in old report
extra_in_new = []
for nr in new_recs:
    if not nr["migration_id"]:
        continue
    old_rec_id = int(nr["migration_id"])
    mysql_cur.execute("""
        SELECT tr.id, tr.status, tr.deleted_date AS tr_del,
               t.id AS tx_id, t.transaction_type, t.`business-unit` AS biz_unit,
               t.deleted_date AS tx_del
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE tr.id = %s
    """, (old_rec_id,))
    old = mysql_cur.fetchone()
    if not old:
        extra_in_new.append((nr, "OLD RECORD NOT FOUND"))
        continue

    reasons = []
    if old["biz_unit"] not in active_biz:
        reasons.append(f"deleted_biz={old['biz_unit']}")
    if old["transaction_type"] != 1:
        reasons.append(f"tx_type={old['transaction_type']}")
    if old["status"] == "rejected":
        reasons.append("rejected")
    if old["tx_del"] is not None:
        reasons.append("tx_deleted")
    if old["tr_del"] is not None:
        reasons.append("tr_deleted")

    if reasons:
        extra_in_new.append((nr, ", ".join(reasons)))

print(f"New recyclable records excluded by old report: {len(extra_in_new)}")
total_extra = 0
for nr, reason in extra_in_new:
    w = float(nr["weight"])
    total_extra += w
    print(f"  new_rec={nr['id']}, migration_id={nr['migration_id']}, mat={nr['material_id']}({nr['name_en']}), "
          f"w={w:.2f}, reason={reason}")
print(f"Total extra weight: {total_extra:.2f}")

mysql_conn.close()
pg_conn.close()
