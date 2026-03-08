import pymysql
import psycopg2
import psycopg2.extras

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310, "user": "admin", "password": "GeppThailand123456$",
    "database": "Gepp_new", "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}
PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()
pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# Find org
pg_cur.execute("""
    SELECT DISTINCT organization_id FROM user_locations
    WHERE email = 'slowcombo@geppdata.me' AND is_user = true
""")
new_org_id = pg_cur.fetchone()['organization_id']

mysql_cur.execute("SELECT id, organization FROM users WHERE email = 'slowcombo@geppdata.me'")
old_user = mysql_cur.fetchone()
old_org_id = old_user['organization']

print(f"Old org={old_org_id}, New org={new_org_id}")

# Old: get business_units
mysql_cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (old_org_id,))
biz_ids = [r['id'] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)
print(f"Old business_units: {biz_ids}")

# Category mapping: old_cat_id -> name
cat_names = {1: 'Recyclables', 2: 'Organic', 3: 'General', 4: 'Hazardous', 5: 'Electronic', 6: 'WTE', 8: 'Bio Hazardous'}
# old -> new cat mapping
cat_old_to_new = {1: 1, 2: 3, 3: 4, 4: 5, 5: 2, 6: 9, 8: 6}

# =====================================================
# OLD: Recyclables (cat=1) records for 2024
# =====================================================
# The old report uses: transaction_type=1, fetchall adds deleted_date IS NULL,
# date range with -7h offset, journey dedup, non-rejected filter
# Date: 2024-01-01 to 2024-12-31 => adjusted -7h => 2023-12-31 17:00:00 to 2024-12-31 17:00:00

mysql_cur.execute(f"""
    SELECT t.id AS tx_id, t.status AS tx_status, t.transaction_date,
           tr.id AS rec_id, tr.status AS rec_status, tr.quantity,
           tr.journey_id, tr.material,
           m.unit_weight, m.name_en AS mat_name, m.material_category_id AS cat_id,
           tr.quantity * m.unit_weight AS weight
    FROM transactions t
    JOIN transaction_records tr ON tr.transaction_id = t.id
    JOIN materials m ON tr.material = m.id
    WHERE t.transaction_type = 1
      AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND m.deleted_date IS NULL
      AND t.transaction_date >= '2023-12-31 17:00:00'
      AND t.transaction_date < '2024-12-31 17:00:00'
      AND m.material_category_id = 1
    ORDER BY t.id, tr.journey_id, tr.id
""")
old_recs = mysql_cur.fetchall()

# Journey dedup: group by tx_id + journey_id, last record wins
from collections import OrderedDict
journey_map = OrderedDict()
for r in old_recs:
    key = f"{r['tx_id']}_{r['journey_id']}"
    journey_map[key] = r

# Filter non-rejected
old_deduped = [r for r in journey_map.values() if r['rec_status'] != 'rejected']
old_total = sum(float(r['weight']) for r in old_deduped)

print(f"\n=== OLD Recyclables 2024 ===")
print(f"Raw records: {len(old_recs)}, After journey dedup: {len(journey_map)}, Non-rejected: {len(old_deduped)}")
print(f"Total weight: {old_total:.2f}")

# =====================================================
# NEW: Recyclables (cat=1) records for 2024
# =====================================================
pg_cur.execute("""
    SELECT t.id AS tx_id, t.status AS tx_status,
           tr.id AS rec_id, tr.status AS rec_status,
           tr.origin_quantity, tr.transaction_date,
           tr.material_id, m.unit_weight, m.name_en AS mat_name,
           m.category_id AS cat_id,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transactions t
    JOIN transaction_records tr ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = %s
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2023-12-31 17:00:00'
      AND tr.transaction_date < '2024-12-31 17:00:00'
      AND m.category_id = 1
      AND (tr.status IS NULL OR tr.status != 'rejected')
    ORDER BY t.id, tr.id
""", (new_org_id,))
new_recs = pg_cur.fetchall()
new_total = sum(float(r['weight']) for r in new_recs)

print(f"\n=== NEW Recyclables 2024 ===")
print(f"Records: {len(new_recs)}")
print(f"Total weight: {new_total:.2f}")

diff = new_total - old_total
print(f"\nDifference: {diff:.2f} kg")

# =====================================================
# Find which records are in new but not old (or vice versa)
# =====================================================
# Build sets by migration_id
old_rec_ids = set()
for r in old_deduped:
    old_rec_ids.add(r['rec_id'])

# Check new records' migration_ids against old
print(f"\n=== Records in NEW but not in OLD deduped set ===")
extra_weight = 0
for r in new_recs:
    pg_cur.execute("SELECT migration_id FROM transaction_records WHERE id = %s", (r['rec_id'],))
    mig = pg_cur.fetchone()
    mig_id = int(mig['migration_id']) if mig and mig['migration_id'] else None
    if mig_id and mig_id not in old_rec_ids:
        extra_weight += float(r['weight'])
        print(f"  new_rec={r['rec_id']}, migration_id={mig_id}, tx={r['tx_id']}, "
              f"mat={r['mat_name']}, qty={r['origin_quantity']}, w={float(r['weight']):.2f}, "
              f"rec_status={r['rec_status']}, tx_status={r['tx_status']}")

        # Check why it's not in old - check the old record
        if mig_id:
            mysql_cur.execute("""
                SELECT tr.id, tr.status, tr.quantity, tr.journey_id, tr.transaction_id,
                       t.status AS tx_status, t.deleted_date AS tx_deleted, tr.deleted_date AS rec_deleted,
                       m.material_category_id, m.deleted_date AS mat_deleted
                FROM transaction_records tr
                JOIN transactions t ON tr.transaction_id = t.id
                JOIN materials m ON tr.material = m.id
                WHERE tr.id = %s
            """, (mig_id,))
            old_r = mysql_cur.fetchone()
            if old_r:
                print(f"    OLD: rec_id={old_r['id']}, status={old_r['status']}, qty={old_r['quantity']}, "
                      f"journey={old_r['journey_id']}, tx={old_r['transaction_id']}, "
                      f"tx_status={old_r['tx_status']}, tx_del={old_r['tx_deleted']}, "
                      f"rec_del={old_r['rec_deleted']}, cat={old_r['material_category_id']}, "
                      f"mat_del={old_r['mat_deleted']}")

                # Check if this record was deduped by journey
                key = f"{old_r['transaction_id']}_{old_r['journey_id']}"
                if key in journey_map:
                    winner = journey_map[key]
                    if winner['rec_id'] != old_r['id']:
                        print(f"    -> DEDUPED by journey! Winner rec_id={winner['rec_id']} "
                              f"(qty={winner['quantity']}, w={float(winner['weight']):.2f})")

print(f"\nExtra weight in new: {extra_weight:.2f}")

# Also check old records not in new
print(f"\n=== Records in OLD deduped but not in NEW ===")
new_migration_ids = set()
for r in new_recs:
    pg_cur.execute("SELECT migration_id FROM transaction_records WHERE id = %s", (r['rec_id'],))
    mig = pg_cur.fetchone()
    if mig and mig['migration_id']:
        new_migration_ids.add(int(mig['migration_id']))

missing_weight = 0
for r in old_deduped:
    if r['rec_id'] not in new_migration_ids:
        missing_weight += float(r['weight'])
        print(f"  old_rec={r['rec_id']}, tx={r['tx_id']}, mat={r['mat_name']}, "
              f"qty={r['quantity']}, w={float(r['weight']):.2f}, "
              f"journey={r['journey_id']}, status={r['rec_status']}")

print(f"\nMissing weight from old: {missing_weight:.2f}")

mysql_conn.close()
pg_conn.close()
