import psycopg2
import psycopg2.extras

PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# Check: are there records where tr.transaction_date differs from the parent transaction's date?
# The new report filters on tr.transaction_date, but old report filters on t.transaction_date
# If they differ, records at boundaries could be included/excluded differently

# First, check if transaction table even has transaction_date
pg_cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'transactions' AND column_name = 'transaction_date'
""")
print(f"transactions.transaction_date exists: {pg_cur.fetchone() is not None}")

# Check records where tr.transaction_date might place them outside 2021-2025
# but the parent tx might be inside (or vice versa)
pg_cur.execute("""
    SELECT tr.id, tr.transaction_date AS tr_date,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight,
           m.name_en, m.category_id
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND (
        (tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01')
      )
    ORDER BY tr.transaction_date DESC
    LIMIT 5
""")
print("\nLast 5 records by tr.transaction_date:")
for r in pg_cur.fetchall():
    print(f"  rec={r['id']}, tr_date={r['tr_date']}, w={float(r['weight']):.2f}")

# Check records at the very edge - Dec 31 2025
pg_cur.execute("""
    SELECT tr.id, tr.transaction_date AS tr_date,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight,
           m.name_en, tr.status
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND tr.transaction_date >= '2025-12-01'
    ORDER BY tr.transaction_date
""")
rows = pg_cur.fetchall()
print(f"\nRecords from Dec 2025+: {len(rows)}")
for r in rows:
    print(f"  rec={r['id']}, date={r['tr_date']}, w={float(r['weight']):.2f}, status={r['status']}")

# Check records at start - Jan 2021
pg_cur.execute("""
    SELECT tr.id, tr.transaction_date AS tr_date,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight,
           m.name_en, tr.status
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND tr.transaction_date < '2021-02-01'
    ORDER BY tr.transaction_date
    LIMIT 10
""")
rows = pg_cur.fetchall()
print(f"\nRecords before Feb 2021:")
for r in rows:
    print(f"  rec={r['id']}, date={r['tr_date']}, w={float(r['weight']):.2f}")

# KEY CHECK: What does the new report ACTUALLY return?
# The new report filters: tr.transaction_date >= date_from AND tr.transaction_date <= date_to
# If user passes date_from=2021-01-01 and date_to=2025-12-31
# Then: tr.transaction_date >= '2021-01-01' AND tr.transaction_date <= '2025-12-31'
# Records with date '2025-12-31 01:00:00' WOULD be included
# Records with date '2020-12-31 23:00:00' would NOT

# Old report: transaction_date BETWEEN '2020-12-31 17:00:00' AND '2025-12-31 16:59:59'
# (after -7h adjustment for 2021-01-01 to 2025-12-31 23:59:59)
# Records with date '2020-12-31 17:00:00' (= Thai Jan 1 00:00) WOULD be included
# Records with date '2025-12-31 17:00:00' (= Thai Jan 1 00:00) would NOT

# So check: are there records with dates between 2020-12-31 17:00 and 2021-01-01 00:00?
pg_cur.execute("""
    SELECT tr.id, tr.transaction_date AS tr_date,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight,
           m.name_en, m.category_id
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND tr.transaction_date >= '2020-12-31 17:00:00' AND tr.transaction_date < '2021-01-01 00:00:00'
""")
rows = pg_cur.fetchall()
total_start = sum(float(r["weight"]) for r in rows)
print(f"\nRecords in old's start boundary (2020-12-31 17:00 to 2021-01-01 00:00): {len(rows)}, total={total_start:.2f}")
for r in rows:
    print(f"  rec={r['id']}, date={r['tr_date']}, w={float(r['weight']):.2f}, cat={r['category_id']}")

# And records at end boundary: between 2025-12-31 17:00 and 2026-01-01
pg_cur.execute("""
    SELECT tr.id, tr.transaction_date AS tr_date,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight,
           m.name_en, m.category_id
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND tr.transaction_date >= '2025-12-31 17:00:00' AND tr.transaction_date < '2026-01-01 00:00:00'
""")
rows = pg_cur.fetchall()
total_end = sum(float(r["weight"]) for r in rows)
print(f"\nRecords in old's end boundary (2025-12-31 17:00 to 2026-01-01 00:00): {len(rows)}, total={total_end:.2f}")
for r in rows:
    print(f"  rec={r['id']}, date={r['tr_date']}, w={float(r['weight']):.2f}, cat={r['category_id']}")

pg_conn.close()
