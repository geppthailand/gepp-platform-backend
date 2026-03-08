import pymysql

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310, "user": "admin", "password": "GeppThailand123456$",
    "database": "Gepp_new", "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()

mysql_cur.execute("SELECT id FROM business_units WHERE organization = 384 AND deleted_date IS NULL")
biz_ids = [r["id"] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)

# Check for duplicate journey keys with DIFFERENT quantities/materials
mysql_cur.execute(f"""
    SELECT tr.id, tr.transaction_id, tr.journey_id, tr.quantity, tr.material, tr.status,
           m.unit_weight, m.name_en, m.material_category_id
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND m.material_category_id = 1
    ORDER BY tr.id
""")
rows = mysql_cur.fetchall()

# Group by journey key
from collections import defaultdict
journey_groups = defaultdict(list)
for r in rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    journey_groups[key].append(r)

# Find keys with multiple records
dups = {k: v for k, v in journey_groups.items() if len(v) > 1}
print(f"Total journey keys: {len(journey_groups)}")
print(f"Duplicate journey keys: {len(dups)}")

total_diff = 0
for key, records in sorted(dups.items()):
    # First vs last record weight diff
    first = records[0]
    last = records[-1]
    fw = float(first["quantity"]) * float(first["unit_weight"])
    lw = float(last["quantity"]) * float(last["unit_weight"])
    if abs(fw - lw) > 0.001:
        total_diff += (lw - fw)
        print(f"  key={key}: first rec={first['id']} mat={first['material']}({first['name_en']}) w={fw:.2f}, last rec={last['id']} mat={last['material']}({last['name_en']}) w={lw:.2f}, diff={lw-fw:+.2f}")

print(f"\nTotal diff from journey dedup (last-first): {total_diff:+.2f}")

# Also check: how many total records vs unique journey keys
print(f"\nTotal recyclable records: {len(rows)}")
print(f"Unique journey keys: {len(journey_groups)}")
print(f"Deduped (removed): {len(rows) - len(journey_groups)}")

mysql_conn.close()
