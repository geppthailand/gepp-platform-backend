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

# NEW PG: check transactions 63947 and 63949
for tx_id in [63947, 63949]:
    pg_cur.execute("""
        SELECT t.id, t.status, t.deleted_date, t.migration_id, t.organization_id,
               t.origin_id
        FROM transactions t WHERE t.id = %s
    """, (tx_id,))
    tx = pg_cur.fetchone()
    print(f"=== NEW TX {tx_id} ===")
    print(f"  status={tx['status']}, deleted={tx['deleted_date']}, migration_id={tx['migration_id']}, "
          f"org={tx['organization_id']}")

    pg_cur.execute("""
        SELECT tr.id, tr.status, tr.origin_quantity, tr.migration_id,
               m.unit_weight, m.name_en, m.category_id,
               tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
        FROM transaction_records tr
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE tr.created_transaction_id = %s AND tr.deleted_date IS NULL
    """, (tx_id,))
    recs = pg_cur.fetchall()
    rec_total = 0
    for r in recs:
        w = float(r["weight"])
        rec_total += w
        print(f"  rec={r['id']}, status={r['status']}, migration_id={r['migration_id']}, "
              f"mat={r['name_en']}, cat={r['category_id']}, qty={r['origin_quantity']}, w={w:.2f}")
    print(f"  Records total: {rec_total:.2f}")

    # Check old MySQL equivalent
    if tx and tx['migration_id']:
        old_tx_id = int(tx['migration_id'])
        mysql_cur.execute("""
            SELECT t.id, t.status, t.deleted_date,
                   t.`business-unit`, t.transaction_type
            FROM transactions t WHERE t.id = %s
        """, (old_tx_id,))
        old_tx = mysql_cur.fetchone()
        if old_tx:
            print(f"\n  OLD TX {old_tx_id}: status={old_tx['status']}, deleted={old_tx['deleted_date']}, "
                  f"biz={old_tx['business-unit']}, type={old_tx['transaction_type']}")

            mysql_cur.execute("""
                SELECT tr.id, tr.status, tr.quantity, tr.journey_id, tr.material,
                       m.unit_weight, m.name_en, m.material_category_id
                FROM transaction_records tr
                JOIN materials m ON tr.material = m.id
                WHERE tr.transaction_id = %s AND tr.deleted_date IS NULL
            """, (old_tx_id,))
            old_recs = mysql_cur.fetchall()
            old_total = 0
            for r in old_recs:
                w = float(r["quantity"]) * float(r["unit_weight"])
                old_total += w
                print(f"    rec={r['id']}, status={r['status']}, journey={r['journey_id']}, "
                      f"mat={r['material']}({r['name_en']}), cat={r['material_category_id']}, w={w:.2f}")
            print(f"    Old records total: {old_total:.2f}")
    print()

mysql_conn.close()
pg_conn.close()
