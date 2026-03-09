"""
Compare GHG calculation records between old MySQL and new PostgreSQL databases
for UOB organization from 2025-01-01 to 2025-12-31
"""
import os
import pandas as pd
import pymysql
import psycopg2
from datetime import datetime
import csv

# Database configurations - adjust these as needed
OLD_DB_CONFIG = {
    'host': os.environ.get('OLD_DB_HOST', 'localhost'),
    'user': os.environ.get('OLD_DB_USER', 'root'),
    'password': os.environ.get('OLD_DB_PASS', ''),
    'database': os.environ.get('OLD_DB_NAME', 'gepp_db'),
    'port': int(os.environ.get('OLD_DB_PORT', '3306'))
}

NEW_DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASS', ''),
    'database': os.environ.get('DB_NAME', 'gepp_platform'),
    'port': int(os.environ.get('DB_PORT', '5432'))
}

# Organization IDs
OLD_ORG_ID = 435  # UOB in old database
NEW_ORG_ID = 117  # UOB in new database

# Date range
START_DATE = '2025-01-01'
END_DATE = '2025-12-31'

def number_2_decimal(value):
    """Match the old version's rounding function"""
    if value is None:
        return 0
    return round(value * 100) / 100

def fetch_old_data():
    """Fetch data from old MySQL database"""
    print("Connecting to old MySQL database...")
    conn = pymysql.connect(**OLD_DB_CONFIG)
    cur = conn.cursor(pymysql.cursors.DictCursor)

    # Fetch transactions
    print(f"Fetching old transactions for org_id={OLD_ORG_ID}...")
    cur.execute(f"""
        SELECT * FROM transactions
        WHERE organization = {OLD_ORG_ID}
        AND transaction_date BETWEEN '{START_DATE} 00:00:00' AND '{END_DATE} 23:59:59'
        AND deleted_date IS NULL
    """)
    transactions = cur.fetchall()
    transactions_by_id = {t['id']: t for t in transactions}
    print(f"Found {len(transactions)} transactions")

    if len(transactions) == 0:
        conn.close()
        return pd.DataFrame()

    # Fetch transaction records
    transaction_ids = [str(t['id']) for t in transactions]
    print(f"Fetching old transaction records...")
    cur.execute(f"""
        SELECT * FROM transaction_records
        WHERE transaction_id IN ({','.join(transaction_ids)})
        AND deleted_date IS NULL
    """)
    records = cur.fetchall()
    print(f"Found {len(records)} records")

    # Fetch materials
    print("Fetching materials...")
    cur.execute("SELECT * FROM materials WHERE id > 0 AND deleted_date IS NULL")
    materials = cur.fetchall()
    materials_by_id = {m['id']: m for m in materials}

    conn.close()

    # Process records like the old version does
    data = []
    for r in records:
        if r['transaction_id'] not in transactions_by_id:
            continue

        transaction = transactions_by_id[r['transaction_id']]
        material = materials_by_id.get(r['material'])

        if not material:
            continue

        # Calculate like old version
        quantity = r.get('quantity', 0) or 0
        unit_weight = material.get('unit_weight', 0) or 0
        calc_ghg = material.get('calc_ghg', 0) or 0
        net_weight = quantity * unit_weight
        net_ghg = net_weight * calc_ghg

        data.append({
            'transaction_id': r['transaction_id'],
            'journey_id': r['journey_id'],
            'record_key': f"{r['transaction_id']}_{r['journey_id']}",
            'status': r.get('status'),
            'quantity': quantity,
            'unit_weight': unit_weight,
            'calc_ghg': calc_ghg,
            'net_weight': net_weight,
            'net_ghg': net_ghg,
            'material_id': r['material'],
            'material_name': material.get('name_en', ''),
            'transaction_date': transaction.get('transaction_date')
        })

    df = pd.DataFrame(data)

    # Filter out rejected records like old version
    # In pandas, != "rejected" INCLUDES None/NULL values
    df_filtered = df[df['status'] != 'rejected']

    print(f"\nOLD DATABASE SUMMARY:")
    print(f"Total records: {len(df)}")
    print(f"Non-rejected records: {len(df_filtered)}")
    print(f"Rejected records: {len(df[df['status'] == 'rejected'])}")
    print(f"NULL status records: {len(df[df['status'].isna()])}")
    print(f"Total Weight: {number_2_decimal(df_filtered['net_weight'].sum())} kg")
    print(f"Total GHG: {number_2_decimal(df_filtered['net_ghg'].sum())} kgCO2e")

    return df_filtered

def fetch_new_data():
    """Fetch data from new PostgreSQL database"""
    print("\nConnecting to new PostgreSQL database...")
    conn = psycopg2.connect(**NEW_DB_CONFIG)
    cur = conn.cursor()

    # Fetch transaction records with materials
    print(f"Fetching new data for org_id={NEW_ORG_ID}...")
    query = """
        SELECT
            tr.id as record_id,
            t.id as transaction_id,
            tr.origin_quantity,
            m.unit_weight,
            m.calc_ghg,
            tr.status,
            m.id as material_id,
            m.name_en as material_name,
            t.transaction_date
        FROM transaction_records tr
        JOIN transactions t ON tr.created_transaction_id = t.id
        JOIN materials m ON tr.material_id = m.id
        WHERE t.organization_id = %s
        AND t.transaction_date >= %s
        AND t.transaction_date <= %s
        AND t.deleted_date IS NULL
        AND tr.deleted_date IS NULL
    """

    cur.execute(query, (NEW_ORG_ID, START_DATE, END_DATE))

    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()

    conn.close()

    data = []
    for row in rows:
        row_dict = dict(zip(columns, row))

        origin_quantity = row_dict.get('origin_quantity', 0) or 0
        unit_weight = row_dict.get('unit_weight', 0) or 0
        calc_ghg = row_dict.get('calc_ghg', 0) or 0
        net_weight = origin_quantity * unit_weight
        net_ghg = net_weight * calc_ghg

        data.append({
            'record_id': row_dict['record_id'],
            'transaction_id': row_dict['transaction_id'],
            'status': row_dict.get('status'),
            'quantity': origin_quantity,
            'unit_weight': unit_weight,
            'calc_ghg': calc_ghg,
            'net_weight': net_weight,
            'net_ghg': net_ghg,
            'material_id': row_dict['material_id'],
            'material_name': row_dict['material_name'],
            'transaction_date': row_dict['transaction_date']
        })

    df = pd.DataFrame(data)

    # Filter like new version - status != 'rejected' OR status IS NULL
    # This should match the pandas behavior
    df_filtered = df[(df['status'] != 'rejected') | (df['status'].isna())]

    print(f"\nNEW DATABASE SUMMARY:")
    print(f"Total records: {len(df)}")
    print(f"Non-rejected records: {len(df_filtered)}")
    print(f"Rejected records: {len(df[df['status'] == 'rejected'])}")
    print(f"NULL status records: {len(df[df['status'].isna()])}")
    print(f"Total Weight: {number_2_decimal(df_filtered['net_weight'].sum())} kg")
    print(f"Total GHG: {number_2_decimal(df_filtered['net_ghg'].sum())} kgCO2e")

    return df_filtered

def compare_and_export():
    """Compare old and new data and export to CSV"""

    # Fetch data from both databases
    old_df = fetch_old_data()
    new_df = fetch_new_data()

    if old_df.empty and new_df.empty:
        print("\nNo data found in both databases!")
        return

    # Calculate totals
    old_total_weight = number_2_decimal(old_df['net_weight'].sum()) if not old_df.empty else 0
    old_total_ghg = number_2_decimal(old_df['net_ghg'].sum()) if not old_df.empty else 0
    new_total_weight = number_2_decimal(new_df['net_weight'].sum()) if not new_df.empty else 0
    new_total_ghg = number_2_decimal(new_df['net_ghg'].sum()) if not new_df.empty else 0

    print("\n" + "="*80)
    print("COMPARISON SUMMARY")
    print("="*80)
    print(f"Date Range: {START_DATE} to {END_DATE}")
    print(f"Old DB (MySQL) - Org ID: {OLD_ORG_ID}")
    print(f"New DB (PostgreSQL) - Org ID: {NEW_ORG_ID}")
    print()
    print(f"Total Weight (kg):")
    print(f"  Old: {old_total_weight:,.2f}")
    print(f"  New: {new_total_weight:,.2f}")
    print(f"  Difference: {new_total_weight - old_total_weight:,.2f} kg")
    print()
    print(f"Total GHG (kgCO2e):")
    print(f"  Old: {old_total_ghg:,.2f}")
    print(f"  New: {new_total_ghg:,.2f}")
    print(f"  Difference: {new_total_ghg - old_total_ghg:,.2f} kgCO2e")
    print("="*80)

    # Export old records to CSV
    old_csv_file = 'ghg_comparison_old_records.csv'
    print(f"\nExporting old records to {old_csv_file}...")
    old_df_export = old_df.copy()
    old_df_export['net_weight'] = old_df_export['net_weight'].apply(number_2_decimal)
    old_df_export['net_ghg'] = old_df_export['net_ghg'].apply(number_2_decimal)
    old_df_export.to_csv(old_csv_file, index=False)
    print(f"Exported {len(old_df)} old records")

    # Export new records to CSV
    new_csv_file = 'ghg_comparison_new_records.csv'
    print(f"Exporting new records to {new_csv_file}...")
    new_df_export = new_df.copy()
    new_df_export['net_weight'] = new_df_export['net_weight'].apply(number_2_decimal)
    new_df_export['net_ghg'] = new_df_export['net_ghg'].apply(number_2_decimal)
    new_df_export.to_csv(new_csv_file, index=False)
    print(f"Exported {len(new_df)} new records")

    # Find differences
    print("\nAnalyzing differences...")

    # Group by transaction_id to compare
    old_by_tx = old_df.groupby('transaction_id').agg({
        'net_weight': 'sum',
        'net_ghg': 'sum',
        'quantity': 'count'
    }).rename(columns={'quantity': 'record_count'})

    new_by_tx = new_df.groupby('transaction_id').agg({
        'net_weight': 'sum',
        'net_ghg': 'sum',
        'quantity': 'count'
    }).rename(columns={'quantity': 'record_count'})

    # Find transactions only in old
    only_in_old = set(old_by_tx.index) - set(new_by_tx.index)
    only_in_new = set(new_by_tx.index) - set(old_by_tx.index)

    if only_in_old:
        print(f"\nTransactions ONLY in OLD database: {len(only_in_old)}")
        only_old_weight = old_df[old_df['transaction_id'].isin(only_in_old)]['net_weight'].sum()
        only_old_ghg = old_df[old_df['transaction_id'].isin(only_in_old)]['net_ghg'].sum()
        print(f"  Total weight: {number_2_decimal(only_old_weight)} kg")
        print(f"  Total GHG: {number_2_decimal(only_old_ghg)} kgCO2e")

    if only_in_new:
        print(f"\nTransactions ONLY in NEW database: {len(only_in_new)}")
        only_new_weight = new_df[new_df['transaction_id'].isin(only_in_new)]['net_weight'].sum()
        only_new_ghg = new_df[new_df['transaction_id'].isin(only_in_new)]['net_ghg'].sum()
        print(f"  Total weight: {number_2_decimal(only_new_weight)} kg")
        print(f"  Total GHG: {number_2_decimal(only_new_ghg)} kgCO2e")

    # Compare common transactions
    common_tx = set(old_by_tx.index) & set(new_by_tx.index)
    if common_tx:
        print(f"\nCommon transactions: {len(common_tx)}")
        differences = []
        for tx_id in common_tx:
            old_w = old_by_tx.loc[tx_id, 'net_weight']
            new_w = new_by_tx.loc[tx_id, 'net_weight']
            old_g = old_by_tx.loc[tx_id, 'net_ghg']
            new_g = new_by_tx.loc[tx_id, 'net_ghg']

            weight_diff = abs(new_w - old_w)
            ghg_diff = abs(new_g - old_g)

            if weight_diff > 0.01 or ghg_diff > 0.01:  # Significant difference
                differences.append({
                    'transaction_id': tx_id,
                    'old_weight': number_2_decimal(old_w),
                    'new_weight': number_2_decimal(new_w),
                    'weight_diff': number_2_decimal(new_w - old_w),
                    'old_ghg': number_2_decimal(old_g),
                    'new_ghg': number_2_decimal(new_g),
                    'ghg_diff': number_2_decimal(new_g - old_g),
                    'old_records': old_by_tx.loc[tx_id, 'record_count'],
                    'new_records': new_by_tx.loc[tx_id, 'record_count']
                })

        if differences:
            diff_csv_file = 'ghg_comparison_differences.csv'
            print(f"\nFound {len(differences)} transactions with differences")
            print(f"Exporting differences to {diff_csv_file}...")
            pd.DataFrame(differences).to_csv(diff_csv_file, index=False)
            print(f"Top 10 transactions with largest weight differences:")
            sorted_diff = sorted(differences, key=lambda x: abs(x['weight_diff']), reverse=True)[:10]
            for d in sorted_diff:
                print(f"  TX {d['transaction_id']}: Weight diff = {d['weight_diff']:+.2f} kg, GHG diff = {d['ghg_diff']:+.2f} kgCO2e")
        else:
            print("No significant differences found in common transactions!")

    print(f"\n✓ Export complete!")
    print(f"  - {old_csv_file} (old database records)")
    print(f"  - {new_csv_file} (new database records)")
    if 'differences' in locals() and differences:
        print(f"  - ghg_comparison_differences.csv (transactions with differences)")

if __name__ == '__main__':
    try:
        compare_and_export()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
