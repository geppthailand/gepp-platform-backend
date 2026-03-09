#!/usr/bin/env python3
"""Find the missing 13 kg for UOB. Expected: 2,013,145.42, Got: 2,013,132.42"""

import mysql.connector

MYSQL_CONFIG = {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "", "database": "Gepp_new"}
OLD_ORG = 435

mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)
mc = mysql_conn.cursor(dictionary=True)

# 1. Current migration result
mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND t.is_active = 1 AND t.deleted_date IS NULL
      AND tr.is_active = 1 AND tr.deleted_date IS NULL
""", (OLD_ORG,))
r = mc.fetchone()
print(f"Current (active tx, active rec):         {r['cnt']:>6} records, {r['qty']:>15} kg")

# 2. Include deleted records too (tr.deleted_date IS NOT NULL)
mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND t.is_active = 1 AND t.deleted_date IS NULL
""", (OLD_ORG,))
r = mc.fetchone()
print(f"Active tx, ALL records (incl deleted):   {r['cnt']:>6} records, {r['qty']:>15} kg")

# 3. Include inactive records (tr.is_active = 0)
mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND t.is_active = 1 AND t.deleted_date IS NULL
      AND tr.is_active = 0
""", (OLD_ORG,))
r = mc.fetchone()
print(f"Active tx, INACTIVE records only:        {r['cnt'] or 0:>6} records, {r['qty'] or 0:>15} kg")

# 4. Active tx, deleted records only
mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND t.is_active = 1 AND t.deleted_date IS NULL
      AND tr.is_active = 1 AND tr.deleted_date IS NOT NULL
""", (OLD_ORG,))
r = mc.fetchone()
print(f"Active tx, SOFT-DELETED records only:    {r['cnt'] or 0:>6} records, {r['qty'] or 0:>15} kg")

# 5. Show the deleted/inactive records detail
mc.execute("""
    SELECT tr.id, tr.transaction_id, ABS(tr.quantity) as qty, tr.material, tr.note,
           tr.is_active, tr.deleted_date
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND t.is_active = 1 AND t.deleted_date IS NULL
      AND (tr.is_active = 0 OR tr.deleted_date IS NOT NULL)
    ORDER BY tr.id
""", (OLD_ORG,))
extras = mc.fetchall()
total_extra = sum(float(r['qty']) for r in extras)
print(f"\nInactive/deleted records from active tx: {len(extras)} records, {total_extra} kg")
for r in extras:
    print(f"  rec_id={r['id']} tx_id={r['transaction_id']} qty={r['qty']} mat={r['material']} "
          f"is_active={r['is_active']} deleted={r['deleted_date']} note={r['note']}")

# 6. Check records referencing UOB BUs from OTHER orgs
mc.execute("""
    SELECT bu.id, bu.name_en FROM `business-unit` bu WHERE bu.organization = %s
""", (OLD_ORG,))
uob_bus = mc.fetchall()
bu_ids = [b['id'] for b in uob_bus]
print(f"\nUOB business units: {len(bu_ids)} ({bu_ids[:5]}...)")

if bu_ids:
    placeholders = ",".join(["%s"] * len(bu_ids))
    # Records FROM other orgs' transactions that have UOB as origin
    mc.execute(f"""
        SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.organization != %s
          AND t.is_active = 1 AND t.deleted_date IS NULL
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.`origin_business-unit` IN ({placeholders})
    """, [OLD_ORG] + bu_ids)
    r = mc.fetchone()
    print(f"Records from OTHER orgs with UOB origin: {r['cnt'] or 0} records, {r['qty'] or 0} kg")

    mc.execute(f"""
        SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        WHERE t.organization != %s
          AND t.is_active = 1 AND t.deleted_date IS NULL
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.`destination_business-unit` IN ({placeholders})
    """, [OLD_ORG] + bu_ids)
    r = mc.fetchone()
    print(f"Records from OTHER orgs with UOB dest:   {r['cnt'] or 0} records, {r['qty'] or 0} kg")

mysql_conn.close()
