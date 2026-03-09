import psycopg2
import psycopg2.extras

PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# Check: are there recyclable records with t.migration_id NOT NULL but tr.migration_id IS NULL?
pg_cur.execute("""
    SELECT tr.id, tr.migration_id AS tr_mig, t.migration_id AS tx_mig,
           tr.origin_quantity, m.unit_weight, m.name_en, m.category_id,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND m.category_id = 1
      AND tr.migration_id IS NULL
""")
rows = pg_cur.fetchall()
print(f"Recyclable records with tx.migration_id but NO tr.migration_id: {len(rows)}")
total = 0
for r in rows:
    w = float(r["weight"] or 0)
    total += w
    print(f"  rec_id={r['id']}, tx_mig={r['tx_mig']}, mat={r['name_en']}, qty={r['origin_quantity']}, w={w:.2f}")
print(f"Total: {total:.2f}")

pg_conn.close()
