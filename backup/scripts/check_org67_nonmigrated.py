import psycopg2
import psycopg2.extras

PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# Check ALL records without migration_id (any category) for 2021-2025
pg_cur.execute("""
    SELECT tr.id, tr.origin_quantity, m.unit_weight, m.category_id, m.name_en,
           mc.name_en AS cat_name,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight,
           tr.transaction_date, t.migration_id AS tx_mig, tr.migration_id AS tr_mig
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    LEFT JOIN material_categories mc ON m.category_id = mc.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NULL
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
""")
rows = pg_cur.fetchall()
total = sum(float(r["weight"] or 0) for r in rows)
print(f"Non-migrated records (2021-2025): {len(rows)}, total={total:.2f}")
for r in rows:
    w = float(r["weight"] or 0)
    print(f"  rec={r['id']}, cat={r['cat_name']}, mat={r['name_en']}, w={w:.2f}, date={r['transaction_date']}")

# Also check: total WITH vs WITHOUT migration_id filter
pg_cur.execute("""
    SELECT
        COUNT(*) AS cnt,
        SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_w
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
""")
r = pg_cur.fetchone()
print(f"\nAll records (2021-2025): {r['cnt']} records, total={float(r['total_w']):.2f}")

pg_cur.execute("""
    SELECT
        COUNT(*) AS cnt,
        SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_w
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
""")
r = pg_cur.fetchone()
print(f"Migrated only (2021-2025): {r['cnt']} records, total={float(r['total_w']):.2f}")

pg_conn.close()
