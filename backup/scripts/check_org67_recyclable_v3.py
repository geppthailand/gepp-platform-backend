import psycopg2
import psycopg2.extras

PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# Check recyclable records WITHOUT migration_id (test data)
pg_cur.execute("""
    SELECT tr.id, tr.migration_id, tr.origin_quantity, tr.material_id,
           m.name_en, m.unit_weight, m.category_id,
           t.id AS tx_id, t.migration_id AS tx_migration_id,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NULL
      AND m.category_id = 1
""")
rows = pg_cur.fetchall()
print(f"Recyclable records WITHOUT migration_id: {len(rows)}")
total = 0
for r in rows:
    w = float(r["weight"] or 0)
    total += w
    print(f"  rec_id={r['id']}, tx_id={r['tx_id']}, mat={r['material_id']} ({r['name_en']}), qty={r['origin_quantity']}, weight={w:.2f}")
print(f"  Total: {total:.2f}")

# Also check total with and without migration_id filter
pg_cur.execute("""
    SELECT
        SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_all,
        SUM(CASE WHEN t.migration_id IS NOT NULL THEN tr.origin_quantity * COALESCE(m.unit_weight, 0) ELSE 0 END) AS total_migrated,
        SUM(CASE WHEN t.migration_id IS NULL THEN tr.origin_quantity * COALESCE(m.unit_weight, 0) ELSE 0 END) AS total_test
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND m.category_id = 1
""")
r = pg_cur.fetchone()
print(f"\nAll recyclable: {float(r['total_all']):.2f}")
print(f"Migrated only: {float(r['total_migrated']):.2f}")
print(f"Test/non-migrated: {float(r['total_test']):.2f}")

pg_conn.close()
