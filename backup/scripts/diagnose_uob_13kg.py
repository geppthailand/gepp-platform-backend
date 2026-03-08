#!/usr/bin/env python3
"""Find the missing 13 kg for UOB (org 435). Expected: 2,013,145.42, Got: 2,013,132.42"""

import mysql.connector
import psycopg2
import psycopg2.extras

MYSQL_CONFIG = {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "", "database": "Gepp_new"}
LOCAL_PG_CONFIG = {"host": "localhost", "port": 5432, "dbname": "postgres", "user": "geppsa-ard", "password": ""}
OLD_ORG = 435

mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)
mc = mysql_conn.cursor(dictionary=True)

# 1. All records (no tx filter) vs with tx filter
mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND tr.is_active = 1 AND tr.deleted_date IS NULL
""", (OLD_ORG,))
r1 = mc.fetchone()
print(f"All active records (ANY tx status):     {r1['cnt']} records, {r1['qty']} kg")

mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND t.is_active = 1 AND t.deleted_date IS NULL
      AND tr.is_active = 1 AND tr.deleted_date IS NULL
""", (OLD_ORG,))
r2 = mc.fetchone()
print(f"Active records (active tx only):        {r2['cnt']} records, {r2['qty']} kg")

diff = float(r1['qty']) - float(r2['qty'])
diff_cnt = r1['cnt'] - r2['cnt']
print(f"Difference (inactive/deleted tx):       {diff_cnt} records, {diff} kg")

# 2. Show those records from inactive/deleted transactions
mc.execute("""
    SELECT tr.id, tr.transaction_id, tr.quantity, tr.material, tr.note,
           t.is_active as tx_active, t.deleted_date as tx_deleted
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.organization = %s
      AND tr.is_active = 1 AND tr.deleted_date IS NULL
      AND (t.is_active = 0 OR t.deleted_date IS NOT NULL)
    ORDER BY tr.id
""", (OLD_ORG,))
orphans = mc.fetchall()
print(f"\nRecords from inactive/deleted transactions ({len(orphans)}):")
for r in orphans:
    print(f"  rec_id={r['id']} tx_id={r['transaction_id']} qty={r['quantity']} mat={r['material']} "
          f"tx_active={r['tx_active']} tx_deleted={r['tx_deleted']} note={r['note']}")

# 3. Also check: all records without joining transactions at all
mc.execute("""
    SELECT SUM(ABS(tr.quantity)) as qty, COUNT(*) as cnt
    FROM transaction_records tr
    WHERE tr.is_active = 1 AND tr.deleted_date IS NULL
      AND tr.transaction_id IN (
          SELECT id FROM transactions WHERE organization = %s
      )
""", (OLD_ORG,))
r3 = mc.fetchone()
print(f"\nSame query alt form:                    {r3['cnt']} records, {r3['qty']} kg")

# 4. Check if there are records referencing UOB business units but different org's transactions
mc.execute("""
    SELECT COUNT(*) as cnt, SUM(ABS(tr.quantity)) as qty
    FROM transaction_records tr
    WHERE tr.is_active = 1 AND tr.deleted_date IS NULL
      AND (tr.`origin_business-unit` IN (
              SELECT id FROM `business-unit` WHERE organization = %s
           )
           OR tr.`destination_business-unit` IN (
              SELECT id FROM `business-unit` WHERE organization = %s
           ))
""", (OLD_ORG, OLD_ORG))
r4 = mc.fetchone()
print(f"\nRecords touching UOB business units:    {r4['cnt']} records, {r4['qty']} kg")

mysql_conn.close()
