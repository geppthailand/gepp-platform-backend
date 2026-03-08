import pymysql
import pandas as pd
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

# Simulate old report exactly: fetch transactions, fetch records, do dedup, create DataFrame
# Step 1: fetch transactions (with deleted_date IS NULL auto-appended by fetchall)
mysql_cur.execute(f"""
    SELECT * FROM transactions
    WHERE `transaction_date` BETWEEN '2020-12-31 17:00:00' AND '2025-12-31 16:59:59'
      AND transaction_type = 1
      AND `business-unit` IN ({biz_str})
      AND deleted_date IS NULL
""")
transactions = mysql_cur.fetchall()
print(f"Transactions: {len(transactions)}")

tx_ids = [t["id"] for t in transactions]
tx_str = ",".join(str(t) for t in tx_ids)

# Step 2: fetch records
mysql_cur.execute(f"""
    SELECT * FROM transaction_records
    WHERE transaction_id IN ({tx_str})
      AND deleted_date IS NULL
""")
records = mysql_cur.fetchall()
print(f"Records: {len(records)}")

# Step 3: fetch materials
mysql_cur.execute("SELECT * FROM materials WHERE id > 0")
materials = mysql_cur.fetchall()
materials_by_id = {m["id"]: m for m in materials}
mat_prefix = {m["id"]: {f"mat_{k}": v for k, v in m.items()} for m in materials}

# Step 4: fetch categories
mysql_cur.execute("SELECT * FROM material_categories WHERE id > 0")
categories = mysql_cur.fetchall()
cat_prefix = {c["id"]: {f"cat_{k}": v for k, v in c.items()} for c in categories}

# Step 5: journey dedup (same as old report)
last_hops = {}
for r in records:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    last_hops[key] = {**r, **mat_prefix[r['material']]}
    lr = last_hops[key]
    last_hops[key] = {**lr, **cat_prefix[lr['mat_material_category_id']]}

print(f"Last hops (after dedup): {len(last_hops)}")

# Step 6: create DataFrame like old report
df = pd.DataFrame(last_hops).T
df["net_weight"] = df["quantity"] * df["mat_unit_weight"]

# Step 7: filter non-rejected
nonrejt = df[df["status"] != "rejected"]

total = nonrejt["net_weight"].sum()
print(f"\nPandas total (old report style): {total:.2f}")
print(f"number_2_decimal: {round(total * 100) / 100:.2f}")

# Category breakdown
cat_groups = nonrejt.groupby("cat_name_en")["net_weight"].sum()
print(f"\nCategory breakdown:")
for cat, w in cat_groups.items():
    print(f"  {cat}: {w:.2f}")

# Also check with pure Python (no pandas)
py_total = 0
for v in last_hops.values():
    if v["status"] != "rejected":
        py_total += float(v["quantity"]) * float(v["mat_unit_weight"])
print(f"\nPure Python total: {py_total:.2f}")
print(f"Diff pandas vs python: {total - py_total:.6f}")

mysql_conn.close()
