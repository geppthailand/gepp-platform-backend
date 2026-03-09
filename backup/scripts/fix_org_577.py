"""
Fix the +577 kg difference for org 125.
6 records from old biz_unit 14022 were incorrectly migrated into org 125.
Soft-delete them (and their parent transactions) on the new PG DB.

Records to soft-delete (identified from investigation):
  rec_id=80766 (migration_id=58546, Clear Plastic PET, 500kg)
  rec_id=80767 (migration_id=58547, Opague Plastic HDPE, 20kg)
  rec_id=80768 (migration_id=58548, Foodwaste, 23kg)
  rec_id=80769 (migration_id=58549, Wood, 2kg)
  rec_id=80770 (migration_id=58550, Waste to Energy Material, 30kg)
  rec_id=80771 (migration_id=58551, Breakable Plastic PS, 2kg)
Parent transactions: tx_id=25030, tx_id=25031
"""

import psycopg2
import psycopg2.extras
import sys
from datetime import datetime, timezone

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

NEW_ORG = 125
REC_IDS = [80766, 80767, 80768, 80769, 80770, 80771]
TX_IDS = [25030, 25031]
DRY_RUN = "--apply" not in sys.argv


def main():
    if DRY_RUN:
        print("*** DRY RUN — pass --apply to actually fix ***\n")

    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # 1. Verify these records exist and belong to org 125
    print("Verifying records...")
    placeholders = ",".join(["%s"] * len(REC_IDS))
    pg_cur.execute(f"""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity,
               tr.deleted_date AS rec_deleted,
               m.unit_weight, m.name_en AS mat_name,
               tr.transaction_date, tr.created_transaction_id,
               t.organization_id, t.deleted_date AS tx_deleted
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE tr.id IN ({placeholders})
    """, REC_IDS)
    rows = pg_cur.fetchall()

    total_weight = 0.0
    for r in rows:
        qty = float(r["origin_quantity"] or 0)
        uw = float(r["unit_weight"] or 0)
        w = qty * uw
        total_weight += w
        already_deleted = "ALREADY DELETED" if r["rec_deleted"] else ""
        print(f"  rec_id={r['rec_id']}, migration_id={r['migration_id']}, weight={w:.2f}, "
              f"mat={r['mat_name']}, org={r['organization_id']}, tx_id={r['created_transaction_id']} "
              f"{already_deleted}")
        if r["organization_id"] != NEW_ORG:
            print(f"  *** WARNING: org_id={r['organization_id']} != {NEW_ORG}!")
    print(f"  Total weight: {total_weight:.2f} kg")

    # 2. Show before total
    pg_cur.execute("""
        SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL
          AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2023-01-01'
          AND tr.transaction_date <= '2023-12-31 23:59:59'
    """, (NEW_ORG,))
    before_total = float(pg_cur.fetchone()["total_weight"] or 0)
    print(f"\n  Before fix (2023 total): {before_total:.2f} kg")

    # 3. Apply
    if DRY_RUN:
        print(f"\n*** DRY RUN — would soft-delete {len(REC_IDS)} records and {len(TX_IDS)} transactions ***")
    else:
        now = datetime.now(timezone.utc)

        print(f"\nSoft-deleting {len(REC_IDS)} transaction_records...")
        for rec_id in REC_IDS:
            pg_cur.execute("UPDATE transaction_records SET deleted_date = %s WHERE id = %s", (now, rec_id))
            print(f"  Soft-deleted rec_id={rec_id}")

        print(f"\nSoft-deleting {len(TX_IDS)} parent transactions...")
        for tx_id in TX_IDS:
            pg_cur.execute("UPDATE transactions SET deleted_date = %s WHERE id = %s", (now, tx_id))
            print(f"  Soft-deleted tx_id={tx_id}")

        pg_conn.commit()
        print("  Committed!")

        # 4. Verify
        pg_cur.execute("""
            SELECT SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_weight
            FROM transaction_records tr
            JOIN transactions t ON tr.created_transaction_id = t.id
            LEFT JOIN materials m ON tr.material_id = m.id
            WHERE t.organization_id = %s
              AND t.deleted_date IS NULL
              AND tr.deleted_date IS NULL
              AND (tr.status != 'rejected' OR tr.status IS NULL)
              AND tr.transaction_date >= '2023-01-01'
              AND tr.transaction_date <= '2023-12-31 23:59:59'
        """, (NEW_ORG,))
        after_total = float(pg_cur.fetchone()["total_weight"] or 0)
        print(f"\n  Before: {before_total:.2f} kg")
        print(f"  After:  {after_total:.2f} kg")
        print(f"  Removed: {before_total - after_total:.2f} kg")
        print(f"  Target:  526,992.71 kg")
        print(f"  Diff:    {after_total - 526992.71:+.2f} kg")

    pg_cur.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
