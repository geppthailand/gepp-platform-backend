"""
Investigate the 275.80 kg gap between old report (45,070.35) and old DB query (44,794.55).
Check deleted records, different filters, and old report logic.
"""

import pymysql
from collections import defaultdict

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

OLD_ORG = 459
DATE_FROM = "2025-01-01"
DATE_TO = "2025-12-31 23:59:59"


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()

    # 1. Check the 78 deleted records
    print("=== DELETED RECORDS (deleted_date IS NOT NULL) ===")
    mysql_cur.execute("""
        SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status AS rec_status,
               tr.material, tr.`journey_id`, tr.is_active, tr.deleted_date,
               m.unit_weight, m.name_en AS mat_name,
               t.status AS tx_status, t.`business-unit` AS biz_unit,
               t.transaction_date, t.deleted_date AS tx_deleted
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND t.transaction_type = 1
          AND tr.deleted_date IS NOT NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
        ORDER BY tr.deleted_date DESC
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    deleted_recs = mysql_cur.fetchall()
    del_total = sum(abs(float(r["quantity"] or 0)) * float(r["unit_weight"] or 0) for r in deleted_recs)
    print(f"Count: {len(deleted_recs)}, Total weight: {del_total:.2f} kg")
    by_bu_del = defaultdict(lambda: {"count": 0, "weight": 0.0})
    for r in deleted_recs:
        qty = abs(float(r["quantity"] or 0))
        uw = float(r["unit_weight"] or 0)
        by_bu_del[r["biz_unit"]]["count"] += 1
        by_bu_del[r["biz_unit"]]["weight"] += qty * uw
    for bu in sorted(by_bu_del, key=lambda b: -by_bu_del[b]["weight"]):
        print(f"  biz={bu}: {by_bu_del[bu]['count']} recs, {by_bu_del[bu]['weight']:.2f} kg")

    # 2. Try different filter combinations to match 45,070.35
    target = 45070.35

    print(f"\n=== TRYING DIFFERENT FILTER COMBINATIONS (target={target:.2f}) ===")

    # A: All type=1, active=1, no deleted_date filter
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity) * m.unit_weight) AS total
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    r = mysql_cur.fetchone()
    print(f"A. type=1, is_active=1, NO deleted_date filter: {float(r['total'] or 0):.2f} kg")

    # B: All type=1, no is_active filter, no deleted_date filter
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity) * m.unit_weight) AS total
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    r = mysql_cur.fetchone()
    print(f"B. type=1, no is_active, no deleted_date: {float(r['total'] or 0):.2f} kg")

    # C: All type=1, is_active=1, deleted_date IS NULL, but NO journey_id dedup, NO status filter
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity) * m.unit_weight) AS total
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    r = mysql_cur.fetchone()
    print(f"C. type=1, active, not deleted, NO dedup: {float(r['total'] or 0):.2f} kg (same as dedup since all unique)")

    # D: Check if old report uses t.deleted_date IS NULL filter
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity) * m.unit_weight) AS total
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.deleted_date IS NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    r = mysql_cur.fetchone()
    print(f"D. + t.deleted_date IS NULL: {float(r['total'] or 0):.2f} kg")

    # E: Check without transaction_type filter
    mysql_cur.execute("""
        SELECT t.transaction_type, COUNT(*) AS cnt,
               SUM(ABS(tr.quantity) * m.unit_weight) AS total
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
        GROUP BY t.transaction_type
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    print(f"\nE. By transaction_type:")
    for r in mysql_cur.fetchall():
        print(f"  type={r['transaction_type']}: {r['cnt']} recs, {float(r['total'] or 0):.2f} kg")

    # F: Check records where transaction_date is in a different field
    # Maybe old report uses tr.created_date instead of t.transaction_date?
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity) * m.unit_weight) AS total, COUNT(*) AS cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.created_date >= %s AND tr.created_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    r = mysql_cur.fetchone()
    print(f"\nF. Using tr.created_date for date range: {r['cnt']} recs, {float(r['total'] or 0):.2f} kg")

    # G: Check if old report might use tr.updated_date
    mysql_cur.execute("""
        SELECT SUM(ABS(tr.quantity) * m.unit_weight) AS total, COUNT(*) AS cnt
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.updated_date >= %s AND tr.updated_date <= %s
    """, (OLD_ORG, DATE_FROM, DATE_TO))
    r = mysql_cur.fetchone()
    print(f"G. Using tr.updated_date for date range: {r['cnt']} recs, {float(r['total'] or 0):.2f} kg")

    # H: Records where t.transaction_date is 2025 but also check for records
    # that might have a different date field in 2025
    mysql_cur.execute("""
        SELECT tr.id, tr.transaction_id, ABS(tr.quantity) * m.unit_weight AS weight,
               tr.quantity, m.unit_weight, m.name_en,
               t.transaction_date, tr.created_date, t.`business-unit`
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND tr.created_date >= %s AND tr.created_date <= %s
          AND (t.transaction_date < %s OR t.transaction_date > %s)
    """, (OLD_ORG, DATE_FROM, DATE_TO, DATE_FROM, DATE_TO))
    diff_date = mysql_cur.fetchall()
    print(f"\nH. Records created in 2025 but tx_date NOT in 2025: {len(diff_date)}")
    for r in diff_date[:20]:
        print(f"  rec_id={r['id']}, tx_id={r['transaction_id']}, weight={float(r['weight'] or 0):.2f}, "
              f"mat={r['name_en']}, tx_date={r['transaction_date']}, created={r['created_date']}, "
              f"biz={r['business-unit']}")

    # I: Check records with tx_date in 2025 but created NOT in 2025
    mysql_cur.execute("""
        SELECT tr.id, tr.transaction_id, ABS(tr.quantity) * m.unit_weight AS weight,
               m.name_en, t.transaction_date, tr.created_date, t.`business-unit`
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= %s AND t.transaction_date <= %s
          AND (tr.created_date < %s OR tr.created_date > %s)
    """, (OLD_ORG, DATE_FROM, DATE_TO, DATE_FROM, DATE_TO))
    diff_date2 = mysql_cur.fetchall()
    print(f"\nI. Records with tx_date in 2025 but created NOT in 2025: {len(diff_date2)}")
    for r in diff_date2[:10]:
        print(f"  rec_id={r['id']}, tx_id={r['transaction_id']}, weight={float(r['weight'] or 0):.2f}, "
              f"mat={r['name_en']}, tx_date={r['transaction_date']}, created={r['created_date']}")

    # J: Check if the old report code uses a specific biz-unit list
    # Get all biz-units for this org
    mysql_cur.execute("""
        SELECT DISTINCT t.`business-unit` AS bu
        FROM transactions t
        WHERE t.organization = %s
        ORDER BY t.`business-unit`
    """, (OLD_ORG,))
    all_bus = [r["bu"] for r in mysql_cur.fetchall()]
    print(f"\nJ. All business-units for org {OLD_ORG}: {all_bus}")

    # K: Check if there are records in 2024 that might have been counted in 2025 report
    # (late December records with transaction_date close to midnight)
    mysql_cur.execute("""
        SELECT tr.id, ABS(tr.quantity) * m.unit_weight AS weight,
               t.transaction_date, t.`business-unit`, m.name_en
        FROM transaction_records tr
        JOIN transactions t ON tr.transaction_id = t.id
        JOIN materials m ON tr.material = m.id
        WHERE t.organization = %s AND t.transaction_type = 1
          AND tr.is_active = 1 AND tr.deleted_date IS NULL
          AND t.transaction_date >= '2024-12-31' AND t.transaction_date < '2025-01-02'
        ORDER BY t.transaction_date
    """, (OLD_ORG,))
    boundary = mysql_cur.fetchall()
    print(f"\nK. Records near 2024/2025 boundary: {len(boundary)}")
    for r in boundary[:20]:
        print(f"  rec_id={r['id']}, weight={float(r['weight'] or 0):.2f}, date={r['transaction_date']}, "
              f"biz={r['business-unit']}, mat={r['name_en']}")

    mysql_cur.close()
    mysql_conn.close()


if __name__ == "__main__":
    main()
