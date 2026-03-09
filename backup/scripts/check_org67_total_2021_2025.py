import pymysql
import psycopg2
import psycopg2.extras
from decimal import Decimal

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

mysql_cur.execute("SELECT id FROM business_units WHERE organization = 384 AND deleted_date IS NULL")
biz_ids = [r["id"] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)

# OLD: total waste by category, 2021-2025
mysql_cur.execute(f"""
    SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status, tr.journey_id,
           tr.material, m.unit_weight, m.name_en, m.material_category_id,
           mc.name_en AS cat_name, t.transaction_date
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN material_categories mc ON m.material_category_id = mc.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2021-01-01' AND t.transaction_date < '2026-01-01'
""")
old_rows = mysql_cur.fetchall()

# Journey dedup
hops = {}
for r in old_rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    hops[key] = r

old_by_cat = {}
old_total = Decimal(0)
old_count = 0
for v in hops.values():
    if v["status"] != "rejected":
        w = Decimal(str(v["quantity"])) * Decimal(str(v["unit_weight"]))
        cat = v["cat_name"]
        old_by_cat[cat] = old_by_cat.get(cat, Decimal(0)) + w
        old_total += w
        old_count += 1

print(f"OLD (2021-2025): {old_count} records, total={float(old_total):.2f}")
for cat in sorted(old_by_cat.keys()):
    print(f"  {cat}: {float(old_by_cat[cat]):.2f}")

# NEW: total waste by category, 2021-2025
pg_cur.execute("""
    SELECT tr.id, tr.origin_quantity, m.unit_weight, m.category_id,
           mc.name_en AS cat_name,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    LEFT JOIN material_categories mc ON m.category_id = mc.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
""")
new_rows = pg_cur.fetchall()

new_by_cat = {}
new_total = Decimal(0)
for r in new_rows:
    w = Decimal(str(r["weight"]))
    cat = r["cat_name"] or "Unknown"
    new_by_cat[cat] = new_by_cat.get(cat, Decimal(0)) + w
    new_total += w

print(f"\nNEW (2021-2025): {len(new_rows)} records, total={float(new_total):.2f}")
for cat in sorted(new_by_cat.keys()):
    print(f"  {cat}: {float(new_by_cat[cat]):.2f}")

print(f"\nTotal diff: {float(new_total - old_total):+.2f}")

# Also check NEW without migration_id filter (what the report actually shows)
pg_cur.execute("""
    SELECT tr.id, tr.origin_quantity, m.unit_weight, m.category_id,
           mc.name_en AS cat_name,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    LEFT JOIN material_categories mc ON m.category_id = mc.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND tr.transaction_date >= '2021-01-01' AND tr.transaction_date < '2026-01-01'
""")
new_all_rows = pg_cur.fetchall()

new_all_by_cat = {}
new_all_total = Decimal(0)
for r in new_all_rows:
    w = Decimal(str(r["weight"]))
    cat = r["cat_name"] or "Unknown"
    new_all_by_cat[cat] = new_all_by_cat.get(cat, Decimal(0)) + w
    new_all_total += w

print(f"\nNEW (no migration filter, 2021-2025): {len(new_all_rows)} records, total={float(new_all_total):.2f}")
for cat in sorted(new_all_by_cat.keys()):
    print(f"  {cat}: {float(new_all_by_cat[cat]):.2f}")

mysql_conn.close()
pg_conn.close()
