# GHG Calculation Comparison Tool

This tool compares GHG (Greenhouse Gas) reduction calculations between the old MySQL database and new PostgreSQL database for UOB organization.

## Purpose

To identify record-by-record differences between:
- **Old Database**: MySQL (org_id = 435)
- **New Database**: PostgreSQL (org_id = 117)
- **Date Range**: 2025-01-01 to 2025-12-31

## Prerequisites

```bash
pip install pandas pymysql psycopg2-binary
```

## Configuration

Set up environment variables for both databases:

### Old MySQL Database
```bash
export OLD_DB_HOST=your_mysql_host
export OLD_DB_USER=your_mysql_user
export OLD_DB_PASS=your_mysql_password
export OLD_DB_NAME=your_mysql_database
export OLD_DB_PORT=3306
```

### New PostgreSQL Database
```bash
export DB_HOST=your_postgres_host
export DB_USER=your_postgres_user
export DB_PASS=your_postgres_password
export DB_NAME=gepp_platform
export DB_PORT=5432
```

## Running the Comparison

```bash
cd /Users/geppsa-ard/Documents/Workspace/gepp-platform
python compare_ghg_records.py
```

## Output Files

The script generates 3 CSV files:

1. **ghg_comparison_old_records.csv**
   - All non-rejected records from old MySQL database
   - Columns: transaction_id, journey_id, record_key, status, quantity, unit_weight, calc_ghg, net_weight, net_ghg, material_id, material_name, transaction_date

2. **ghg_comparison_new_records.csv**
   - All non-rejected records from new PostgreSQL database
   - Columns: record_id, transaction_id, status, quantity, unit_weight, calc_ghg, net_weight, net_ghg, material_id, material_name, transaction_date

3. **ghg_comparison_differences.csv**
   - Transactions that have different calculations between databases
   - Columns: transaction_id, old_weight, new_weight, weight_diff, old_ghg, new_ghg, ghg_diff, old_records, new_records

## Console Output

The script prints:
- Total records in each database
- Number of rejected vs non-rejected records
- Number of NULL status records
- Total Weight and GHG for each database
- Difference summary
- Transactions only in old database
- Transactions only in new database
- Top 10 transactions with largest differences

## Current Known Issue

- **Total Weight**: Old = 380,882.90 kg, New = 380,863.90 kg (difference: -19.00 kg)
- **GHG Reduction**: Values don't match exactly

This tool helps identify exactly which records are causing these discrepancies.

## Key Calculation Logic

### Old Version (MySQL + Pandas)
```python
# Pandas filter: status != "rejected" INCLUDES NULL status
nonrejt_fh = last_hops[last_hops["status"] != "rejected"]
net_weight = quantity * mat_unit_weight
net_ghg = net_weight * mat_calc_ghg
total_ghg = number_2_decimal(nonrejt_fh["net_ghg"].sum())
```

### New Version (PostgreSQL + SQLAlchemy)
```python
# SQL filter: status != 'rejected' OR status IS NULL
weight = origin_qty * unit_weight
record_ghg = weight * calc_ghg
ghg_reduction = round(ghg_reduction * 100) / 100
```

## Expected Match

Both calculations should produce EXACTLY the same results since they use the same formula and rounding method.
