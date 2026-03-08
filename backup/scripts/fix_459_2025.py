"""
Fix org 459/141 year 2025: 275.80 kg gap.
Transaction 141858 (new id 97809) has wrong transaction_date in new DB.
Old MySQL: 2025-12-31 05:00:00 UTC
New PG:    2026-01-05 05:00:00 UTC (wrong)

Fix: Update transaction_date to 2025-12-31 05:00:00 UTC for both
transaction and its 4 records.
"""

import psycopg2
import psycopg2.extras

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

CORRECT_DATE = "2025-12-31 05:00:00+00"
NEW_TX_ID = 97809
NEW_REC_IDS = [160328, 160329, 160330, 160331]


def main():
    conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()

    # Show BEFORE
    print("=== BEFORE ===")
    cur.execute("SELECT id, migration_id, transaction_date FROM transactions WHERE id = %s", (NEW_TX_ID,))
    print(f"Transaction: {dict(cur.fetchone())}")
    for rid in NEW_REC_IDS:
        cur.execute("SELECT id, migration_id, origin_quantity, transaction_date FROM transaction_records WHERE id = %s", (rid,))
        print(f"Record: {dict(cur.fetchone())}")

    # Fix transaction
    cur.execute("UPDATE transactions SET transaction_date = %s WHERE id = %s", (CORRECT_DATE, NEW_TX_ID))
    print(f"\nUpdated transaction {NEW_TX_ID} -> {CORRECT_DATE}")

    # Fix records
    for rid in NEW_REC_IDS:
        cur.execute("UPDATE transaction_records SET transaction_date = %s WHERE id = %s", (CORRECT_DATE, rid))
        print(f"Updated record {rid} -> {CORRECT_DATE}")

    conn.commit()

    # Show AFTER
    print("\n=== AFTER ===")
    cur.execute("SELECT id, migration_id, transaction_date FROM transactions WHERE id = %s", (NEW_TX_ID,))
    print(f"Transaction: {dict(cur.fetchone())}")
    for rid in NEW_REC_IDS:
        cur.execute("SELECT id, migration_id, origin_quantity, transaction_date FROM transaction_records WHERE id = %s", (rid,))
        print(f"Record: {dict(cur.fetchone())}")

    # Verify new total
    cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight,
               COUNT(*) AS cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = 141
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2025-01-01' AND tr.transaction_date <= '2025-12-31 23:59:59'
    """)
    result = cur.fetchone()
    new_total = float(result['total_weight'] or 0)
    print(f"\nNew total for org 141, year 2025: {new_total:.2f} kg")
    print(f"Target: 45,070.35 kg")
    print(f"Match: {'YES' if abs(new_total - 45070.35) < 0.1 else 'NO'} (diff={new_total - 45070.35:+.2f})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
