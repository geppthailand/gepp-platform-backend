import pymysql
from collections import defaultdict

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

# Get ALL records (including rejected) for 2021-2025, same as old report
mysql_cur.execute(f"""
    SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status, tr.journey_id,
           tr.material, m.unit_weight, m.name_en, m.material_category_id
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND t.transaction_date >= '2021-01-01' AND t.transaction_date < '2026-01-01'
    ORDER BY tr.id
""")
all_rows = mysql_cur.fetchall()
print(f"Total records (including rejected): {len(all_rows)}")

# Find journey keys shared between rejected and non-rejected
by_key = defaultdict(list)
for r in all_rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    by_key[key].append(r)

overwrite_cases = []
for key, records in by_key.items():
    statuses = [r["status"] for r in records]
    has_rejected = any(s == "rejected" for s in statuses)
    has_nonrejected = any(s != "rejected" for s in statuses)
    if has_rejected and has_nonrejected:
        overwrite_cases.append((key, records))

print(f"Journey keys with both rejected and non-rejected records: {len(overwrite_cases)}")

# Simulate old report dedup (all records, last wins, then filter rejected)
last_hops_old = {}
for r in all_rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    last_hops_old[key] = r

# Filter rejected after dedup
old_report_total = 0
old_report_count = 0
old_report_by_cat = {}
for v in last_hops_old.values():
    if v["status"] != "rejected":
        w = float(v["quantity"]) * float(v["unit_weight"])
        old_report_total += w
        old_report_count += 1
        cat = v["material_category_id"]
        old_report_by_cat[cat] = old_report_by_cat.get(cat, 0) + w

print(f"\nOLD REPORT style (dedup ALL then filter rejected): {old_report_count} records, total={old_report_total:.2f}")

# Simulate my script (filter rejected first, then dedup)
last_hops_mine = {}
for r in all_rows:
    if r["status"] != "rejected":
        key = f"{r['transaction_id']}_{r['journey_id']}"
        last_hops_mine[key] = r

my_total = 0
my_count = 0
for v in last_hops_mine.values():
    w = float(v["quantity"]) * float(v["unit_weight"])
    my_total += w
    my_count += 1

print(f"MY SCRIPT style (filter rejected first then dedup): {my_count} records, total={my_total:.2f}")
print(f"Diff: {my_total - old_report_total:+.2f}")

# Show the overwrite cases
if overwrite_cases:
    print(f"\nOverwrite cases detail:")
    for key, records in overwrite_cases:
        last = records[-1]
        print(f"  key={key}:")
        for r in records:
            w = float(r["quantity"]) * float(r["unit_weight"])
            marker = " <-- LAST (kept in dedup)" if r is last else ""
            print(f"    rec={r['rec_id']}, status={r['status']}, mat={r['material']}({r['name_en']}), w={w:.2f}{marker}")

mysql_conn.close()
