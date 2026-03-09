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

# OLD: recyclable records, excluding 2026 data
mysql_cur.execute(f"""
    SELECT tr.id, tr.quantity, m.unit_weight, tr.status, tr.journey_id, tr.transaction_id,
           t.transaction_date
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND m.material_category_id = 1
      AND t.transaction_date < '2026-01-01'
""")
old_rows = mysql_cur.fetchall()

# Journey dedup
hops = {}
for r in old_rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    hops[key] = r

old_total = Decimal(0)
old_count = 0
old_records_by_id = {}
for v in hops.values():
    if v["status"] != "rejected":
        w = Decimal(str(v["quantity"])) * Decimal(str(v["unit_weight"]))
        old_total += w
        old_count += 1
        old_records_by_id[v["id"]] = {"weight": float(w), "qty": float(v["quantity"]), "uw": float(v["unit_weight"])}

print(f"OLD (pre-2026) recyclable: {old_count} records, total={float(old_total):.2f}")

# NEW: all recyclable records
pg_cur.execute("""
    SELECT tr.id, tr.migration_id, tr.origin_quantity, m.unit_weight,
           tr.origin_quantity * COALESCE(m.unit_weight, 0) AS weight
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND m.category_id = 1
""")
new_rows = pg_cur.fetchall()
new_total = Decimal(0)
for r in new_rows:
    new_total += Decimal(str(r["weight"]))
print(f"NEW recyclable: {len(new_rows)} records, total={float(new_total):.2f}")
print(f"Diff: {float(new_total - old_total):+.2f}")

# Check if any records have quantity/unit_weight mismatch
mismatch_count = 0
for r in new_rows:
    mid = int(r["migration_id"])
    if mid in old_records_by_id:
        old_w = old_records_by_id[mid]["weight"]
        new_w = float(r["weight"])
        if abs(old_w - new_w) > 0.001:
            mismatch_count += 1
            if mismatch_count <= 10:
                print(f"  Weight mismatch: rec={mid}, old={old_w:.4f}, new={new_w:.4f}, diff={new_w-old_w:+.4f}")

print(f"Weight mismatches: {mismatch_count}")

# Check for records in new not in old (by migration_id)
old_id_set = set(old_records_by_id.keys())
extra_in_new = []
for r in new_rows:
    mid = int(r["migration_id"])
    if mid not in old_id_set:
        extra_in_new.append(r)

print(f"\nRecords in new but not in old (pre-2026): {len(extra_in_new)}")
for r in extra_in_new:
    print(f"  new_rec={r['id']}, migration_id={r['migration_id']}, w={float(r['weight']):.2f}")

mysql_conn.close()
pg_conn.close()
