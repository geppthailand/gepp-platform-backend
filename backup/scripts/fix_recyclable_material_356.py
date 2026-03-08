import psycopg2
import psycopg2.extras

PG_CONFIG = {
    "host": "13.215.109.125", "port": 5432, "dbname": "postgres",
    "user": "postgres", "password": "6N0i8SKEVfd19B3",
}

pg_conn = psycopg2.connect(**PG_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)
pg_cur = pg_conn.cursor()

# Fix: Recyclable Material (id=356) is under Glass (main_material_id=2)
# Should be under Plastic (main_material_id=1)
# Affected org: bmadatabase@gepp.me (org_id=67), 416.50 kg total (391.5 in 2023, 25 in 2024)

print("=== Before fix ===")
pg_cur.execute("""
    SELECT m.id, m.name_en, m.main_material_id, mm.name_en AS main_mat_name
    FROM materials m
    LEFT JOIN main_materials mm ON m.main_material_id = mm.id
    WHERE m.id = 356
""")
row = pg_cur.fetchone()
print(f"  Material id={row['id']}, name='{row['name_en']}', "
      f"main_material_id={row['main_material_id']} ({row['main_mat_name']})")

# Apply fix
pg_cur.execute("UPDATE materials SET main_material_id = 1 WHERE id = 356")
print(f"\n=== Updated main_material_id from 2 (Glass) to 1 (Plastic) ===")

print("\n=== After fix ===")
pg_cur.execute("""
    SELECT m.id, m.name_en, m.main_material_id, mm.name_en AS main_mat_name
    FROM materials m
    LEFT JOIN main_materials mm ON m.main_material_id = mm.id
    WHERE m.id = 356
""")
row = pg_cur.fetchone()
print(f"  Material id={row['id']}, name='{row['name_en']}', "
      f"main_material_id={row['main_material_id']} ({row['main_mat_name']})")

confirm = input("\nCommit? (yes/no): ")
if confirm.strip().lower() == 'yes':
    pg_conn.commit()
    print("Committed!")
else:
    pg_conn.rollback()
    print("Rolled back.")

pg_conn.close()
