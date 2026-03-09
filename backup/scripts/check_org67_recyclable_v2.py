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

# Get active biz units for org 384
mysql_cur.execute("SELECT id FROM business_units WHERE organization = 384 AND deleted_date IS NULL")
biz_ids = [r["id"] for r in mysql_cur.fetchall()]
biz_str = ",".join(str(b) for b in biz_ids)

# OLD: get all recyclable records with journey dedup
mysql_cur.execute(f"""
    SELECT tr.id AS rec_id, tr.transaction_id, tr.quantity, tr.status, tr.journey_id,
           tr.material, m.unit_weight, m.name_en
    FROM transaction_records tr
    JOIN materials m ON tr.material = m.id
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE t.transaction_type = 1 AND t.`business-unit` IN ({biz_str})
      AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND m.material_category_id = 1
""")
old_rows = mysql_cur.fetchall()

# Journey dedup
hops = {}
for r in old_rows:
    key = f"{r['transaction_id']}_{r['journey_id']}"
    hops[key] = r

old_records = {}
for v in hops.values():
    if v["status"] != "rejected":
        w = float(v["quantity"]) * float(v["unit_weight"])
        old_records[v["rec_id"]] = {"weight": w, "mat": v["material"], "name": v["name_en"], "qty": float(v["quantity"])}

old_total = sum(r["weight"] for r in old_records.values())
print(f"OLD Recyclable total: {old_total:.2f} ({len(old_records)} records)")

# NEW: get all recyclable records with migration_id
pg_cur.execute("""
    SELECT tr.id AS rec_id, tr.migration_id, tr.origin_quantity, tr.status,
           tr.material_id, m.unit_weight, m.name_en,
           t.id AS tx_id, t.migration_id AS tx_migration_id
    FROM transaction_records tr
    JOIN transactions t ON tr.created_transaction_id = t.id
    LEFT JOIN materials m ON tr.material_id = m.id
    WHERE t.organization_id = 67 AND t.deleted_date IS NULL AND tr.deleted_date IS NULL
      AND (tr.status != 'rejected' OR tr.status IS NULL)
      AND t.migration_id IS NOT NULL
      AND m.category_id = 1
""")
new_rows = pg_cur.fetchall()

new_by_migration = {}
new_total = 0
for r in new_rows:
    w = float(r["origin_quantity"]) * float(r["unit_weight"] or 0)
    new_total += w
    if r["migration_id"]:
        mid = int(r["migration_id"])
        new_by_migration[mid] = {"weight": w, "mat": r["material_id"], "name": r["name_en"], "qty": float(r["origin_quantity"]), "rec_id": r["rec_id"]}

print(f"NEW Recyclable total: {new_total:.2f} ({len(new_rows)} records)")
print(f"Diff: {new_total - old_total:+.2f}")

# Find records in NEW not in OLD (by migration_id matching old rec_id)
new_only = []
for mid, nr in new_by_migration.items():
    if mid not in old_records:
        new_only.append((mid, nr))

if new_only:
    print(f"\nRecords in NEW (migration_id) not in OLD ({len(new_only)}):")
    for mid, nr in sorted(new_only, key=lambda x: -x[1]["weight"])[:20]:
        print(f"  old_rec_id={mid}, new_rec_id={nr['rec_id']}, mat={nr['mat']} ({nr['name']}), qty={nr['qty']}, weight={nr['weight']:.2f}")

# Find records in OLD not in NEW
old_ids = set(old_records.keys())
new_migration_ids = set(new_by_migration.keys())
old_only = old_ids - new_migration_ids
if old_only:
    print(f"\nRecords in OLD not in NEW ({len(old_only)}):")
    for oid in sorted(old_only):
        r = old_records[oid]
        print(f"  old_rec_id={oid}, mat={r['mat']} ({r['name']}), qty={r['qty']}, weight={r['weight']:.2f}")

# Find records with weight mismatch
mismatches = []
for mid, nr in new_by_migration.items():
    if mid in old_records:
        ow = old_records[mid]["weight"]
        nw = nr["weight"]
        if abs(ow - nw) > 0.001:
            mismatches.append((mid, old_records[mid], nr))

if mismatches:
    print(f"\nRecords with weight mismatch ({len(mismatches)}):")
    for mid, oldr, newr in sorted(mismatches, key=lambda x: abs(x[1]["weight"] - x[2]["weight"]), reverse=True)[:20]:
        print(f"  rec_id={mid}: old_mat={oldr['mat']}({oldr['name']}) w={oldr['weight']:.2f}, new_mat={newr['mat']}({newr['name']}) w={newr['weight']:.2f}, diff={newr['weight']-oldr['weight']:+.2f}")

mysql_conn.close()
pg_conn.close()
