#!/bin/bash
# Migration Validation Script
# Validates SQL syntax and Python script functionality

set -e  # Exit on any error

echo "============================================"
echo "MATERIALS MIGRATION VALIDATION"
echo "============================================"

# Check if required files exist
echo "📁 Checking migration files..."

STRUCTURE_FILE="20250922_100000_020_restructure_materials_tables.sql"
DATA_FILE="20250922_110000_021_migrate_materials_data_from_csv.sql"
PYTHON_SCRIPT="migrate_materials.py"
CSV_FILE="../data/New Mainmat_Submat.csv"

for file in "$STRUCTURE_FILE" "$DATA_FILE" "$PYTHON_SCRIPT"; do
    if [[ -f "$file" ]]; then
        echo "  ✅ $file exists"
    else
        echo "  ❌ $file missing"
        exit 1
    fi
done

if [[ -f "$CSV_FILE" ]]; then
    echo "  ✅ CSV file exists: $CSV_FILE"
else
    echo "  ⚠️  CSV file not found: $CSV_FILE"
    echo "     This is optional for SQL validation"
fi

# Validate Python script syntax
echo ""
echo "🐍 Validating Python script..."
python -m py_compile "$PYTHON_SCRIPT"
echo "  ✅ Python syntax valid"

# Test Python script help
python "$PYTHON_SCRIPT" --help > /dev/null
echo "  ✅ Python script executable"

# Validate SQL syntax (basic check)
echo ""
echo "📊 Validating SQL files..."

# Check for common SQL syntax issues
validate_sql() {
    local file=$1
    echo "  Checking $file..."

    # Check for unclosed quotes
    if grep -n "'" "$file" | grep -v "'''" | grep -c "'" | grep -q "[13579]$"; then
        echo "  ⚠️  Potential unclosed quotes in $file"
    fi

    # Check for missing semicolons on major statements
    if grep -E "^(CREATE|ALTER|DROP|INSERT)" "$file" | grep -v ";" | head -1; then
        echo "  ⚠️  Potential missing semicolons in $file"
    fi

    # Check for basic structure
    if [[ "$file" == *"restructure"* ]]; then
        if grep -q "CREATE TABLE.*material_categories" "$file" && \
           grep -q "RENAME TO main_materials" "$file" && \
           grep -q "CREATE TABLE materials" "$file"; then
            echo "    ✅ Structure migration looks good"
        else
            echo "    ❌ Structure migration missing key elements"
            exit 1
        fi
    fi

    if [[ "$file" == *"migrate_materials_data"* ]]; then
        if grep -q "INSERT INTO material_categories" "$file" && \
           grep -q "INSERT INTO main_materials" "$file" && \
           grep -q "INSERT INTO materials" "$file"; then
            echo "    ✅ Data migration looks good"
        else
            echo "    ❌ Data migration missing key elements"
            exit 1
        fi
    fi
}

validate_sql "$STRUCTURE_FILE"
validate_sql "$DATA_FILE"

# Check CSV structure if file exists
if [[ -f "$CSV_FILE" ]]; then
    echo ""
    echo "📋 Validating CSV structure..."

    # Check header
    header=$(head -1 "$CSV_FILE")
    expected="ID,name_th,Category,Main material,unit_name_th,unit_name_en,unit_weight,color,calc_ghg,name_en"

    if [[ "$header" == "$expected" ]]; then
        echo "  ✅ CSV header correct"
    else
        echo "  ❌ CSV header mismatch"
        echo "     Expected: $expected"
        echo "     Got:      $header"
        exit 1
    fi

    # Count records
    record_count=$(tail -n +2 "$CSV_FILE" | wc -l | tr -d ' ')
    echo "  ✅ CSV contains $record_count material records"

    # Check for Thai text encoding
    if grep -q "ขยะ" "$CSV_FILE"; then
        echo "  ✅ Thai text encoding looks good"
    else
        echo "  ⚠️  No Thai text found in CSV"
    fi
fi

# Check migration log table compatibility
echo ""
echo "📝 Checking migration log compatibility..."

for sql_file in "$STRUCTURE_FILE" "$DATA_FILE"; do
    if grep -q "INSERT INTO migration_log" "$sql_file"; then
        echo "  ✅ $sql_file includes migration logging"
    else
        echo "  ⚠️  $sql_file missing migration logging"
    fi
done

echo ""
echo "🔍 Summary of migration changes:"
echo "  • Creates material_categories table (4 categories)"
echo "  • Renames material_main → main_materials (11 main materials)"
echo "  • Restructures materials table (98 materials from CSV)"
echo "  • Adds environmental intelligence (GHG factors)"
echo "  • Adds business intelligence (units, colors, tags)"
echo "  • Creates performance indexes"
echo "  • Includes data backup and verification"

echo ""
echo "============================================"
echo "✅ MIGRATION VALIDATION COMPLETED"
echo "============================================"
echo ""
echo "🚀 Ready to execute migration:"
echo "   1. Dry run: python migrate_materials.py --dry-run"
echo "   2. Execute: python migrate_materials.py"
echo "   3. Verify:  python migrate_materials.py --verify-only"
echo ""
echo "📖 See MATERIALS_MIGRATION_README.md for detailed instructions"