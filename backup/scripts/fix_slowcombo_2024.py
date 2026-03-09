import psycopg2
import psycopg2.extras
from datetime import datetime

PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# These 2 transactions belong to old business_unit 14710 (Slowcombo - Office)
# which was deleted on 2025-02-10 in the old MySQL.
# The old report excludes them because it filters by active business_units.
# In the new PG, origin_id is NULL (location wasn't migrated) and they show up in the report.
# Fix: soft-delete them to match old behavior.

tx_ids = [59628, 59629]

print("=== Soft-deleting transactions with deleted origin location ===")
now = datetime.utcnow()

for tx_id in tx_ids:
    pg_cur.execute("SELECT id, migration_id, origin_id, status FROM transactions WHERE id = %s", (tx_id,))
    tx = pg_cur.fetchone()
    print(f"  TX {tx_id}: migration_id={tx['migration_id']}, origin_id={tx['origin_id']}, status={tx['status']}")

    # Soft-delete transaction
    pg_cur.execute("UPDATE transactions SET deleted_date = %s WHERE id = %s", (now, tx_id))

    # Soft-delete its records
    pg_cur.execute("""
        UPDATE transaction_records SET deleted_date = %s
        WHERE created_transaction_id = %s AND deleted_date IS NULL
    """, (now, tx_id))
    print(f"    -> Soft-deleted transaction and its records")

confirm = input("\nCommit? (yes/no): ")
if confirm.strip().lower() == 'yes':
    pg_conn.commit()
    print("Committed!")
else:
    pg_conn.rollback()
    print("Rolled back.")

pg_conn.close()
