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

# Check old transactions 102346 and 102347
for old_tx_id in [102346, 102347]:
    mysql_cur.execute("""
        SELECT t.id, t.status, t.transaction_date, t.`business-unit`, t.transaction_type,
               t.deleted_date, t.total_quantity
        FROM transactions t WHERE t.id = %s
    """, (old_tx_id,))
    tx = mysql_cur.fetchone()
    print(f"=== Old TX {old_tx_id} ===")
    print(f"  status={tx['status']}, date={tx['transaction_date']}, biz_unit={tx['business-unit']}, "
          f"type={tx['transaction_type']}, deleted={tx['deleted_date']}, total_qty={tx['total_quantity']}")

    mysql_cur.execute("""
        SELECT tr.id, tr.status, tr.quantity, tr.journey_id, tr.material,
               m.unit_weight, m.name_en, m.material_category_id, m.deleted_date AS mat_deleted,
               tr.deleted_date AS rec_deleted
        FROM transaction_records tr
        JOIN materials m ON tr.material = m.id
        WHERE tr.transaction_id = %s
        ORDER BY tr.id
    """, (old_tx_id,))
    for r in mysql_cur.fetchall():
        w = float(r['quantity']) * float(r['unit_weight'])
        print(f"  rec={r['id']}, status={r['status']}, qty={r['quantity']}, journey={r['journey_id']}, "
              f"mat={r['material']}({r['name_en']}), cat={r['material_category_id']}, w={w:.2f}, "
              f"rec_del={r['rec_deleted']}, mat_del={r['mat_deleted']}")

    # Check if business-unit is in the active list
    biz_unit = tx['business-unit']
    mysql_cur.execute("SELECT id, name_en, name_th, deleted_date, organization FROM business_units WHERE id = %s", (biz_unit,))
    bu = mysql_cur.fetchone()
    if bu:
        print(f"  business_unit: id={bu['id']}, name={bu['name_en'] or bu['name_th']}, "
              f"deleted={bu['deleted_date']}, org={bu['organization']}")
    print()

# Also check the new side
print("=== NEW side ===")
for new_tx_id in [59628, 59629]:
    pg_cur.execute("""
        SELECT t.id, t.status, t.deleted_date, t.migration_id, t.organization_id, t.origin_id
        FROM transactions t WHERE t.id = %s
    """, (new_tx_id,))
    tx = pg_cur.fetchone()
    print(f"New TX {new_tx_id}: status={tx['status']}, deleted={tx['deleted_date']}, "
          f"migration_id={tx['migration_id']}, org={tx['organization_id']}, origin={tx['origin_id']}")

    pg_cur.execute("""
        SELECT tr.id, tr.status, tr.origin_quantity, tr.transaction_date, tr.material_id,
               tr.migration_id, tr.deleted_date,
               m.name_en, m.category_id, m.unit_weight,
               tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
        FROM transaction_records tr
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE tr.created_transaction_id = %s
        ORDER BY tr.id
    """, (new_tx_id,))
    for r in pg_cur.fetchall():
        print(f"  rec={r['id']}, status={r['status']}, qty={r['origin_quantity']}, date={r['transaction_date']}, "
              f"mat={r['name_en']}, cat={r['category_id']}, w={float(r['weight']):.2f}, "
              f"mig_id={r['migration_id']}, del={r['deleted_date']}")
    print()

# Check: the old report's date filter uses transaction_date with -7h offset
# 2024: start = 2024-01-01 00:00:00 -7h = 2023-12-31 17:00:00
#        end   = 2024-12-31 23:59:59 -7h = 2024-12-31 16:59:59
# But maybe the actual date is at the boundary?
print("=== Check transaction dates for boundary issues ===")
for old_tx_id in [102346, 102347]:
    mysql_cur.execute("SELECT id, transaction_date FROM transactions WHERE id = %s", (old_tx_id,))
    tx = mysql_cur.fetchone()
    print(f"Old TX {old_tx_id}: transaction_date = {tx['transaction_date']}")

# Check if these transactions' business-unit is in the active list for org 2391
mysql_cur.execute("SELECT id, name_th, name_en, deleted_date FROM business_units WHERE organization = 2391 AND deleted_date IS NULL")
active_bus = mysql_cur.fetchall()
print(f"\nActive business_units for org 2391: {[b['id'] for b in active_bus]}")

mysql_conn.close()
pg_conn.close()
