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

emails = [
    'bmadatabase@gepp.me',
    'ktb@geppdata.me',
    'slowcombo@geppdata.me',
    'sisb@gepp.me',
    'oklin.thailand@gmail.com',
]

# Step 1: Find organizations for these emails
pg_cur.execute("""
    SELECT DISTINCT ul.organization_id, ul.email, ul.name_en
    FROM user_locations ul
    WHERE ul.email = ANY(%s) AND ul.is_user = true
""", (emails,))
user_orgs = pg_cur.fetchall()
print("=== Organizations for these emails ===")
org_ids = set()
for r in user_orgs:
    print(f"  email={r['email']}, org_id={r['organization_id']}, name={r['name_en']}")
    org_ids.add(r['organization_id'])

print(f"\nOrg IDs: {sorted(org_ids)}")

# Step 2: For each org, find transactions that are soft-deleted in new PG but NOT deleted in old MySQL
total_fix_tx = 0
total_fix_tr = 0

for org_id in sorted(org_ids):
    # Get all soft-deleted transactions in new PG for this org (that have migration_id)
    pg_cur.execute("""
        SELECT t.id, t.migration_id, t.deleted_date, t.origin_id, t.status
        FROM transactions t
        WHERE t.organization_id = %s
          AND t.deleted_date IS NOT NULL
          AND t.migration_id IS NOT NULL
    """, (org_id,))
    deleted_txs = pg_cur.fetchall()

    if not deleted_txs:
        continue

    # Check each against old MySQL
    wrongly_deleted_tx_ids = []
    for tx in deleted_txs:
        old_tx_id = int(tx['migration_id'])
        mysql_cur.execute("""
            SELECT id, deleted_date, status FROM transactions WHERE id = %s
        """, (old_tx_id,))
        old_tx = mysql_cur.fetchone()
        if old_tx and old_tx['deleted_date'] is None:
            # Old is NOT deleted but new IS deleted -> wrongly cascade-deleted
            wrongly_deleted_tx_ids.append(tx['id'])

    if not wrongly_deleted_tx_ids:
        continue

    # Also find wrongly deleted transaction_records
    pg_cur.execute("""
        SELECT tr.id, tr.migration_id, tr.deleted_date
        FROM transaction_records tr
        WHERE tr.created_transaction_id = ANY(%s)
          AND tr.deleted_date IS NOT NULL
          AND tr.migration_id IS NOT NULL
    """, (wrongly_deleted_tx_ids,))
    deleted_recs = pg_cur.fetchall()

    wrongly_deleted_tr_ids = []
    for tr in deleted_recs:
        old_tr_id = int(tr['migration_id'])
        mysql_cur.execute("""
            SELECT id, deleted_date FROM transaction_records WHERE id = %s
        """, (old_tr_id,))
        old_tr = mysql_cur.fetchone()
        if old_tr and old_tr['deleted_date'] is None:
            wrongly_deleted_tr_ids.append(tr['id'])

    print(f"\n=== Org {org_id}: {len(wrongly_deleted_tx_ids)} wrongly deleted transactions, {len(wrongly_deleted_tr_ids)} wrongly deleted records ===")
    total_fix_tx += len(wrongly_deleted_tx_ids)
    total_fix_tr += len(wrongly_deleted_tr_ids)

    # Show sample
    for tx_id in wrongly_deleted_tx_ids[:5]:
        pg_cur.execute("SELECT id, migration_id, deleted_date, origin_id FROM transactions WHERE id = %s", (tx_id,))
        t = pg_cur.fetchone()
        print(f"  tx={t['id']}, migration_id={t['migration_id']}, deleted={t['deleted_date']}, origin={t['origin_id']}")
    if len(wrongly_deleted_tx_ids) > 5:
        print(f"  ... and {len(wrongly_deleted_tx_ids) - 5} more")

print(f"\n=== TOTAL: {total_fix_tx} transactions, {total_fix_tr} records to restore ===")

# Step 3: Fix — remove deleted_date from wrongly deleted transactions and records
if total_fix_tx > 0 or total_fix_tr > 0:
    confirm = input("\nProceed with fix? (yes/no): ")
    if confirm.strip().lower() == 'yes':
        for org_id in sorted(org_ids):
            pg_cur.execute("""
                SELECT t.id
                FROM transactions t
                WHERE t.organization_id = %s
                  AND t.deleted_date IS NOT NULL
                  AND t.migration_id IS NOT NULL
            """, (org_id,))
            deleted_txs = pg_cur.fetchall()

            for tx in deleted_txs:
                old_tx_id_str = None
                pg_cur.execute("SELECT migration_id FROM transactions WHERE id = %s", (tx['id'],))
                row = pg_cur.fetchone()
                if row and row['migration_id']:
                    old_tx_id = int(row['migration_id'])
                    mysql_cur.execute("SELECT deleted_date FROM transactions WHERE id = %s", (old_tx_id,))
                    old = mysql_cur.fetchone()
                    if old and old['deleted_date'] is None:
                        # Restore transaction
                        pg_cur.execute("UPDATE transactions SET deleted_date = NULL WHERE id = %s", (tx['id'],))

                        # Restore records that are also not deleted in old
                        pg_cur.execute("""
                            SELECT tr.id, tr.migration_id
                            FROM transaction_records tr
                            WHERE tr.created_transaction_id = %s AND tr.deleted_date IS NOT NULL AND tr.migration_id IS NOT NULL
                        """, (tx['id'],))
                        for tr in pg_cur.fetchall():
                            old_tr_id = int(tr['migration_id'])
                            mysql_cur.execute("SELECT deleted_date FROM transaction_records WHERE id = %s", (old_tr_id,))
                            old_tr = mysql_cur.fetchone()
                            if old_tr and old_tr['deleted_date'] is None:
                                pg_cur.execute("UPDATE transaction_records SET deleted_date = NULL WHERE id = %s", (tr['id'],))

        pg_conn.commit()
        print("Fix applied successfully!")
    else:
        print("Aborted.")

mysql_conn.close()
pg_conn.close()
