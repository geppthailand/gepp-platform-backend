"""
Fix org 459/141: Soft-delete 48 records from biz_unit 14036 (2021-2022)
that were deleted in old MySQL (deleted_date=2023-11-15) but active in new PG.
Total: 4,812.47 kg
"""

import psycopg2
import psycopg2.extras
from datetime import datetime

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

# These record IDs in new PG correspond to records whose old MySQL transactions
# were deleted on 2023-11-15 09:21:11
NEW_REC_IDS = [
    164544, 164545, 164546, 164547, 164548, 164549, 164550, 164551,
    164552, 164553, 164554, 164555, 164556, 164557, 164558, 164559,
    164560, 164561, 164562, 164563, 164564, 164565, 164566, 164567,
    164568, 164569, 164570, 164571, 164572, 164573, 164574, 164575,
    164576, 164577, 164578, 164579, 164580, 164581, 164582, 164583,
    164584, 164585, 164586, 164587, 164588, 164589, 164590, 164591,
]

DELETE_DATE = "2023-11-15 09:21:11+07"


def main():
    conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()

    # BEFORE: count and total
    placeholders = ",".join(["%s"] * len(NEW_REC_IDS))
    cur.execute(f"""
        SELECT COUNT(*) AS cnt,
               SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total
        FROM transaction_records tr
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE tr.id IN ({placeholders}) AND tr.deleted_date IS NULL
    """, NEW_REC_IDS)
    before = cur.fetchone()
    print(f"BEFORE: {before['cnt']} active records, {float(before['total'] or 0):.2f} kg")

    # Get unique transaction IDs for these records
    cur.execute(f"""
        SELECT DISTINCT created_transaction_id FROM transaction_records
        WHERE id IN ({placeholders})
    """, NEW_REC_IDS)
    tx_ids = [r['created_transaction_id'] for r in cur.fetchall()]
    print(f"Transactions to soft-delete: {tx_ids}")

    # Soft-delete records
    cur.execute(f"""
        UPDATE transaction_records SET deleted_date = %s
        WHERE id IN ({placeholders})
    """, [DELETE_DATE] + NEW_REC_IDS)
    print(f"Soft-deleted {cur.rowcount} records")

    # Soft-delete transactions
    tx_placeholders = ",".join(["%s"] * len(tx_ids))
    cur.execute(f"""
        UPDATE transactions SET deleted_date = %s
        WHERE id IN ({tx_placeholders})
    """, [DELETE_DATE] + tx_ids)
    print(f"Soft-deleted {cur.rowcount} transactions")

    conn.commit()

    # AFTER: verify totals for 2021-2025
    cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total,
               COUNT(*) AS cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = 141
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date <= '2025-12-31 23:59:59'
    """)
    after = cur.fetchone()
    new_total = float(after['total'] or 0)
    print(f"\nAFTER (2021-2025): {after['cnt']} records, {new_total:.2f} kg")
    print(f"Target: 339,317.05 kg")
    print(f"Match: {'YES' if abs(new_total - 339317.05) < 0.1 else 'NO'} (diff={new_total - 339317.05:+.2f})")

    # Also verify per year
    cur.execute("""
        SELECT EXTRACT(YEAR FROM tr.transaction_date) AS yr,
               COUNT(*) AS cnt,
               SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = 141
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date <= '2025-12-31 23:59:59'
        GROUP BY yr ORDER BY yr
    """)
    print("\nPer year:")
    for r in cur.fetchall():
        print(f"  {int(r['yr'])}: {r['cnt']} recs, {float(r['total']):.2f} kg")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
