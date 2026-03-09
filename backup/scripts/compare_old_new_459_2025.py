"""
Compare transaction records between old MySQL and new PostgreSQL for org 459/141, year 2025.
Find which records exist in one but not the other to explain the 275.80 kg gap.
Old report: 45,070.35 | New report: 44,794.55
"""

import pymysql
import psycopg2
import psycopg2.extras
from collections import defaultdict

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310,
    "user": "admin",
    "password": "GeppThailand123456$",
    "database": "Gepp_new",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

REMOTE_PG_CONFIG = {
    "host": "13.215.109.125",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "6N0i8SKEVfd19B3",
}

OLD_ORG = 459
NEW_ORG = 141


def main():
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    pg_conn = psycopg2.connect(**REMOTE_PG_CONFIG, cursor_factory=psycopg2.extras.DictCursor)
    pg_cur = pg_conn.cursor()

    # ===== OLD DB: Exact old report logic =====
    # Get biz units
    mysql_cur.execute("""
        SELECT id FROM business_units
        WHERE organization = %s AND deleted_date IS NULL
    """, (OLD_ORG,))
    biz_unit_ids = [r['id'] for r in mysql_cur.fetchall()]
    biz_ids_str = ",".join([str(b) for b in biz_unit_ids])

    # Transactions (old report logic: biz-unit filter, deleted_date IS NULL, type=1)
    mysql_cur.execute(f"""
        SELECT t.id, t.`business-unit` AS biz_unit, t.transaction_date, t.organization
        FROM transactions t
        WHERE t.transaction_date BETWEEN '2025-01-01' AND '2025-12-31 23:59:59'
          AND t.transaction_type = 1
          AND t.`business-unit` IN ({biz_ids_str})
          AND t.deleted_date IS NULL
    """)
    old_transactions = mysql_cur.fetchall()
    old_tx_ids = [t['id'] for t in old_transactions]
    old_tx_by_id = {t['id']: t for t in old_transactions}
    print(f"OLD DB: {len(old_transactions)} transactions")

    # Records (old report: no is_active filter, deleted_date IS NULL)
    if old_tx_ids:
        tx_ids_str = ",".join([str(t) for t in old_tx_ids])
        mysql_cur.execute(f"""
            SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status,
                   tr.material, tr.journey_id, tr.is_active,
                   m.unit_weight, m.name_en AS mat_name
            FROM transaction_records tr
            JOIN materials m ON tr.material = m.id
            WHERE tr.transaction_id IN ({tx_ids_str})
              AND tr.deleted_date IS NULL
        """)
        old_records = mysql_cur.fetchall()
    else:
        old_records = []

    # Dedup by journey_id (last wins)
    old_last_hops = {}
    for r in old_records:
        key = f"{r['transaction_id']}_{r['journey_id']}"
        old_last_hops[key] = r
    old_non_rej = {k: v for k, v in old_last_hops.items() if v['status'] != 'rejected'}

    old_total = sum(float(v['quantity'] or 0) * float(v['unit_weight'] or 0) for v in old_non_rej.values())
    print(f"OLD DB: {len(old_records)} raw records -> {len(old_last_hops)} dedup -> {len(old_non_rej)} non-rejected")
    print(f"OLD DB total: {old_total:.2f} kg")

    # Build old record lookup by rec_id
    old_rec_ids = set(v['rec_id'] for v in old_non_rej.values())

    # ===== NEW DB: Current new report logic =====
    pg_cur.execute("""
        SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity AS quantity,
               tr.status, tr.material_id, tr.transaction_date AS rec_tx_date,
               tr.created_transaction_id,
               m.unit_weight, m.name_en AS mat_name, m.migration_id AS mat_migration_id,
               t.id AS new_tx_id, t.organization_id, t.migration_id AS tx_migration_id
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
          AND (tr.status != 'rejected' OR tr.status IS NULL)
          AND tr.transaction_date >= '2025-01-01' AND tr.transaction_date <= '2025-12-31 23:59:59'
    """, (NEW_ORG,))
    new_records = pg_cur.fetchall()
    new_total = sum(float(r['quantity'] or 0) * float(r['unit_weight'] or 0) for r in new_records)
    print(f"\nNEW DB: {len(new_records)} records")
    print(f"NEW DB total: {new_total:.2f} kg")

    # Build migration_id lookup for new records
    new_by_migration_id = {}
    for r in new_records:
        if r['migration_id']:
            new_by_migration_id[int(r['migration_id'])] = r

    # ===== COMPARE by migration_id (old rec_id = new migration_id) =====
    print(f"\n{'='*70}")
    print("COMPARISON (old rec_id <-> new migration_id)")

    # Records in OLD but not in NEW
    old_only = []
    for v in old_non_rej.values():
        if v['rec_id'] not in new_by_migration_id:
            old_only.append(v)

    old_only_weight = sum(float(r['quantity'] or 0) * float(r['unit_weight'] or 0) for r in old_only)
    print(f"\nRecords in OLD but NOT in NEW: {len(old_only)}, weight: {old_only_weight:.2f} kg")
    for r in sorted(old_only, key=lambda x: -abs(float(x['quantity'] or 0) * float(x['unit_weight'] or 0))):
        w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
        tx = old_tx_by_id.get(r['transaction_id'], {})
        print(f"  rec_id={r['rec_id']}, tx_id={r['transaction_id']}, "
              f"qty={r['quantity']}, uw={r['unit_weight']}, w={w:.2f}, "
              f"mat={r['mat_name']}, biz={tx.get('biz_unit')}, "
              f"date={tx.get('transaction_date')}, is_active={r['is_active']}")

    # Records in NEW but not in OLD
    new_migration_ids = set(new_by_migration_id.keys())
    new_only = []
    for r in new_records:
        mid = int(r['migration_id']) if r['migration_id'] else None
        if mid and mid not in old_rec_ids:
            new_only.append(r)
        elif not mid:
            new_only.append(r)

    new_only_weight = sum(float(r['quantity'] or 0) * float(r['unit_weight'] or 0) for r in new_only)
    print(f"\nRecords in NEW but NOT in OLD: {len(new_only)}, weight: {new_only_weight:.2f} kg")
    for r in sorted(new_only, key=lambda x: -abs(float(x['quantity'] or 0) * float(x['unit_weight'] or 0)))[:30]:
        w = float(r['quantity'] or 0) * float(r['unit_weight'] or 0)
        print(f"  rec_id={r['rec_id']}, migration_id={r['migration_id']}, "
              f"qty={r['quantity']}, uw={r['unit_weight']}, w={w:.2f}, "
              f"mat={r['mat_name']}, date={r['rec_tx_date']}, status={r['status']}")

    # Records in BOTH — check for weight differences
    matched_old_weight = 0
    matched_new_weight = 0
    weight_diffs = []
    for v in old_non_rej.values():
        if v['rec_id'] in new_by_migration_id:
            nr = new_by_migration_id[v['rec_id']]
            old_w = float(v['quantity'] or 0) * float(v['unit_weight'] or 0)
            new_w = float(nr['quantity'] or 0) * float(nr['unit_weight'] or 0)
            matched_old_weight += old_w
            matched_new_weight += new_w
            if abs(old_w - new_w) > 0.01:
                weight_diffs.append((v, nr, old_w, new_w))

    print(f"\nMatched records: old_weight={matched_old_weight:.2f}, new_weight={matched_new_weight:.2f}, diff={matched_old_weight - matched_new_weight:+.2f}")

    if weight_diffs:
        print(f"\nWeight differences in matched records: {len(weight_diffs)}")
        for v, nr, ow, nw in sorted(weight_diffs, key=lambda x: -abs(x[2]-x[3]))[:20]:
            print(f"  rec_id={v['rec_id']}: old_w={ow:.2f}, new_w={nw:.2f}, diff={ow-nw:+.2f}")
            print(f"    old: qty={v['quantity']}, uw={v['unit_weight']}, mat={v['mat_name']}")
            print(f"    new: qty={nr['quantity']}, uw={nr['unit_weight']}, mat={nr['mat_name']}")

    # ===== ALSO: Check what old report on PRODUCTION would return =====
    # The old report live shows 45,070.35. Check if production MySQL has more records.
    # We can check by looking at new PG for records that have migration_id but aren't in local MySQL.
    print(f"\n{'='*70}")
    print("CHECKING: New PG records with migration_id not found in local MySQL")
    pg_cur.execute("""
        SELECT tr.id, tr.migration_id, tr.origin_quantity, tr.status,
               tr.transaction_date, tr.deleted_date AS tr_del,
               m.unit_weight, m.name_en,
               t.organization_id, t.deleted_date AS tx_del
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        LEFT JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
          AND tr.transaction_date >= '2025-01-01' AND tr.transaction_date <= '2025-12-31 23:59:59'
          AND tr.migration_id IS NOT NULL
        ORDER BY tr.migration_id
    """, (NEW_ORG,))
    all_new_with_mig = pg_cur.fetchall()

    # Check each against local MySQL
    missing_from_local = []
    for r in all_new_with_mig:
        mid = int(r['migration_id'])
        mysql_cur.execute("SELECT id, is_active, deleted_date, status FROM transaction_records WHERE id = %s", (mid,))
        local = mysql_cur.fetchone()
        if not local:
            missing_from_local.append(r)

    print(f"New PG records with migration_id NOT found in local MySQL: {len(missing_from_local)}")
    miss_weight = 0
    for r in missing_from_local:
        w = float(r['origin_quantity'] or 0) * float(r['unit_weight'] or 0)
        miss_weight += w
        print(f"  new_id={r['id']}, migration_id={r['migration_id']}, qty={r['origin_quantity']}, "
              f"uw={r['unit_weight']}, w={w:.2f}, mat={r['name_en']}, "
              f"date={r['transaction_date']}, status={r['status']}, "
              f"tr_del={r['tr_del']}, tx_del={r['tx_del']}")
    print(f"Total missing weight: {miss_weight:.2f} kg")

    # ===== SUMMARY =====
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"  Old report (production): 45,070.35 kg")
    print(f"  Old DB (local MySQL):    {old_total:.2f} kg")
    print(f"  New DB (PostgreSQL):     {new_total:.2f} kg")
    print(f"  Gap (production - local): {45070.35 - old_total:+.2f} kg")
    print(f"  Gap (production - new):   {45070.35 - new_total:+.2f} kg")
    print(f"  Old-only weight:         {old_only_weight:.2f} kg")
    print(f"  New-only weight:         {new_only_weight:.2f} kg")
    print(f"  Net diff (old_only - new_only): {old_only_weight - new_only_weight:+.2f} kg")

    mysql_cur.close(); mysql_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
