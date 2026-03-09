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

old_org_id = 2391
new_org_id = 2069

# Category mapping: old->new
cat_names = {1: 'Recyclables', 2: 'Organic', 3: 'General', 4: 'Hazardous', 5: 'Electronic', 6: 'WTE', 8: 'Bio Hazardous'}
cat_old_to_new = {1: 1, 2: 3, 3: 4, 4: 5, 5: 2, 6: 9, 8: 6}

mysql_cur.execute("SELECT id FROM business_units WHERE organization = %s AND deleted_date IS NULL", (old_org_id,))
biz_ids = [r['id'] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)

# OLD: by category
from collections import OrderedDict
mysql_cur.execute(f"""
    SELECT t.id AS tx_id, tr.id AS rec_id, tr.status AS rec_status, tr.quantity,
           tr.journey_id, m.unit_weight, m.material_category_id AS cat_id,
           tr.quantity * m.unit_weight AS weight
    FROM transactions t
    JOIN transaction_records tr ON tr.transaction_id = t.id
    JOIN materials m ON tr.material = m.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL AND m.deleted_date IS NULL
      AND t.transaction_date >= '2023-12-31 17:00:00' AND t.transaction_date < '2024-12-31 17:00:00'
    ORDER BY t.id, tr.journey_id, tr.id
""")
old_recs = mysql_cur.fetchall()

# Journey dedup
journey_map = OrderedDict()
for r in old_recs:
    key = f"{r['tx_id']}_{r['journey_id']}"
    journey_map[key] = r

old_deduped = [r for r in journey_map.values() if r['rec_status'] != 'rejected']

old_by_cat = {}
for r in old_deduped:
    cat = r['cat_id']
    old_by_cat.setdefault(cat, 0)
    old_by_cat[cat] += float(r['weight'])

# NEW: by category
pg_cur.execute("""
    SELECT m.category_id AS cat_id,
           SUM(tr.origin_quantity * COALESCE(m.unit_weight, 0)) AS total_w
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = %s AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2023-12-31 17:00:00' AND tr.transaction_date < '2024-12-31 17:00:00'
      AND (tr.status IS NULL OR tr.status != 'rejected')
    GROUP BY m.category_id
""", (new_org_id,))
new_by_cat = {}
for r in pg_cur.fetchall():
    new_by_cat[r['cat_id']] = float(r['total_w'])

print(f"{'Category':<20} {'Old (kg)':>12} {'New (kg)':>12} {'Diff':>10}")
print("-" * 56)
all_cats = sorted(set(list(old_by_cat.keys()) + [cat_old_to_new.get(k, k) for k in old_by_cat.keys()]))
for old_cat in sorted(old_by_cat.keys()):
    new_cat = cat_old_to_new.get(old_cat, old_cat)
    old_w = old_by_cat.get(old_cat, 0)
    new_w = new_by_cat.get(new_cat, 0)
    diff = new_w - old_w
    name = cat_names.get(old_cat, f'Cat {old_cat}')
    flag = " ***" if abs(diff) > 0.01 else ""
    print(f"{name:<20} {old_w:>12.2f} {new_w:>12.2f} {diff:>10.2f}{flag}")

old_total = sum(old_by_cat.values())
new_total = sum(new_by_cat.values())
print("-" * 56)
print(f"{'TOTAL':<20} {old_total:>12.2f} {new_total:>12.2f} {new_total - old_total:>10.2f}")

mysql_conn.close()
pg_conn.close()
