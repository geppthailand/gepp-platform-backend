import pymysql

MYSQL_CONFIG = {
    "host": "geppprod.c0laqiewxlub.ap-southeast-1.rds.amazonaws.com",
    "port": 3310, "user": "admin", "password": "GeppThailand123456$",
    "database": "Gepp_new", "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

mysql_conn = pymysql.connect(**MYSQL_CONFIG)
mysql_cur = mysql_conn.cursor()

# Check the 15 missing old records - what transaction/biz unit
rec_ids = [153434,153435,153436,153437,153438,153439,153440,153441,153442,153443,153444,153445,153446,153447,153448]
rec_str = ",".join(str(r) for r in rec_ids)

mysql_cur.execute(f"""
    SELECT tr.id, tr.transaction_id, tr.quantity, tr.material, tr.journey_id,
           t.`business-unit` AS biz_unit, t.transaction_type, t.deleted_date AS tx_del,
           bu.name_en AS bu_name, bu.deleted_date AS bu_del, bu.organization
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    LEFT JOIN business_units bu ON t.`business-unit` = bu.id
    WHERE tr.id IN ({rec_str})
""")
for r in mysql_cur.fetchall():
    print(f"rec={r['id']}, tx={r['transaction_id']}, biz={r['biz_unit']}({r['bu_name']}), org={r['organization']}, journey={r['journey_id']}, bu_del={r['bu_del']}")

# Now let's check: does the old report use a specific year filter?
# Let's see what the old report total would be if we reproduce it more carefully
# The old report's fetchall auto-appends deleted_date IS NULL
# Let's check what transaction dates these 15 records have
print("\n--- Transaction dates for 15 missing records ---")
mysql_cur.execute(f"""
    SELECT tr.id, t.created_date, t.transaction_date
    FROM transaction_records tr
    JOIN transactions t ON tr.transaction_id = t.id
    WHERE tr.id IN ({rec_str})
""")
for r in mysql_cur.fetchall():
    print(f"  rec={r['id']}, created={r['created_date']}, tx_date={r['transaction_date']}")

# Check if there are records with journey_id that causes dedup differently
# The old report groups by transaction_id + material (journey dedup keeps last hop)
# Let me check if these 15 records have journey duplicates
print("\n--- Journey info for 15 missing records ---")
mysql_cur.execute(f"""
    SELECT tr.id, tr.transaction_id, tr.journey_id, tr.material,
           (SELECT COUNT(*) FROM transaction_records tr2
            WHERE tr2.transaction_id = tr.transaction_id AND tr2.journey_id = tr.journey_id
            AND tr2.deleted_date IS NULL) AS same_journey_count
    FROM transaction_records tr
    WHERE tr.id IN ({rec_str})
""")
for r in mysql_cur.fetchall():
    print(f"  rec={r['id']}, tx={r['transaction_id']}, journey={r['journey_id']}, mat={r['material']}, same_journey={r['same_journey_count']}")

mysql_conn.close()
