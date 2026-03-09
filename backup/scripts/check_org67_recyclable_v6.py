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

# Check DELETED business units for org 384
mysql_cur.execute("SELECT id, name_en, deleted_date FROM business_units WHERE organization = 384 AND deleted_date IS NOT NULL")
deleted_bus = mysql_cur.fetchall()
print(f"Deleted business units for org 384: {len(deleted_bus)}")
for b in deleted_bus:
    print(f"  id={b['id']}, name={b['name_en']}, deleted={b['deleted_date']}")

# Check if any recyclable records exist for deleted biz units
if deleted_bus:
    del_biz_str = ",".join(str(b["id"]) for b in deleted_bus)
    mysql_cur.execute(f"""
        SELECT tr.id, tr.quantity, tr.material, m.unit_weight, m.name_en,
               t.`business-unit` AS biz_unit, tr.status
        FROM transaction_records tr
        JOIN materials m ON tr.material = m.id
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.transaction_type = 1 AND t.`business-unit` IN ({del_biz_str})
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND m.material_category_id = 1 AND tr.status != 'rejected'
    """)
    del_recs = mysql_cur.fetchall()
    total_del = sum(float(r["quantity"]) * float(r["unit_weight"]) for r in del_recs)
    print(f"\nRecyclable records from DELETED biz units: {len(del_recs)}, total weight: {total_del:.2f}")
    for r in del_recs:
        w = float(r["quantity"]) * float(r["unit_weight"])
        print(f"  rec={r['id']}, biz={r['biz_unit']}, mat={r['material']}({r['name_en']}), w={w:.2f}")

    # Check if these records were migrated to new PG
    if del_recs:
        del_rec_ids = [r["id"] for r in del_recs]
        pg_cur.execute("""
            SELECT tr.id, tr.migration_id, tr.origin_quantity, m.unit_weight, m.name_en, m.category_id
            FROM transaction_records tr
            LEFT JOIN materials m ON tr.material_id = m.id
            WHERE tr.migration_id = ANY(%s) AND tr.deleted_date IS NULL
        """, ([str(rid) for rid in del_rec_ids],))
        migrated = pg_cur.fetchall()
        print(f"\nOf those, migrated to new PG: {len(migrated)}")
        for r in migrated:
            w = float(r["origin_quantity"]) * float(r["unit_weight"] or 0)
            print(f"  new_rec migration_id={r['migration_id']}, mat={r['name_en']}, cat={r['category_id']}, w={w:.2f}")

mysql_conn.close()
pg_conn.close()
