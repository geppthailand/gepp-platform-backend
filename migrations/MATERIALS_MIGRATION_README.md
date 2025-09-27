# Materials Migration Guide

## Overview
This migration restructures the materials table architecture from a two-tier to a three-tier system with enhanced environmental and business intelligence features.

## Migration Structure

### Before (Old Structure)
```
material_main (table)
└── materials (table)
    ├── material_main_id (FK)
    ├── name_en, name_th, name_local
    ├── code, description
    └── basic fields only
```

### After (New Structure)
```
material_categories (NEW)
├── id, name_en, name_th, code, description
└── Enhanced categorization

main_materials (RENAMED from material_main)
├── id, name_en, name_th, name_local, code
└── Base material types

materials (RESTRUCTURED)
├── category_id (FK to material_categories)
├── main_material_id (FK to main_materials)
├── Enhanced fields:
│   ├── tags (search/filtering)
│   ├── unit_name_th, unit_name_en
│   ├── unit_weight (calculations)
│   ├── color (hex codes for UI)
│   ├── calc_ghg (environmental impact)
│   └── name_th, name_en
└── Environmental & business intelligence
```

## Migration Files

### 1. Structure Migration
**File**: `20250922_100000_020_restructure_materials_tables.sql`
- Creates `material_categories` table
- Renames `material_main` → `main_materials`
- Restructures `materials` table with new columns
- Creates performance indexes
- Updates foreign key references

### 2. Data Migration
**File**: `20250922_110000_021_migrate_materials_data_from_csv.sql`
- Populates `material_categories` with 4 categories
- Populates `main_materials` with 11 main material types
- Migrates 98 materials from CSV data
- Creates proper relationships
- Includes data verification

### 3. Automated Script
**File**: `migrate_materials.py`
- Python automation script
- CSV data analysis
- Migration execution
- Data verification
- Rollback capabilities

## CSV Data Analysis

### Source File
`data/New Mainmat_Submat.csv` contains 98 materials with structure:
```csv
ID,name_th,Category,Main material,unit_name_th,unit_name_en,unit_weight,color,calc_ghg,name_en
```

### Categories (4 total)
1. **ขยะรีไซเคิล** (Recyclable Waste) - 84 materials
2. **ขยะอิเล็กทรอนิกส์** (Electronic Waste) - 12 materials
3. **ขยะอินทรีย์** (Organic Waste) - 3 materials
4. **ขยะทั่วไป** (General Waste) - 1 material

### Main Materials (11 total)
1. **พลาสติก** (Plastic) - 24 materials
2. **แก้ว** (Glass) - 16 materials
3. **โลหะ** (Metal) - 20 materials
4. **กระดาษ** (Paper) - 8 materials
5. **อื่นๆ** (Others) - 10 materials
6. **อุปกรณ์คอมพิวเตอร์** (Computer Equipment) - 6 materials
7. **เครื่องใช้ไฟฟ้า** (Electrical Appliances) - 5 materials
8. **สายไฟ** (Electrical Wire) - 4 materials
9. **เศษอาหารและพืช** (Food and Plant Waste) - 3 materials
10. **โทรคมนาคม** (Telecommunication) - 1 material
11. **ขยะทั่วไป** (General Waste) - 1 material

## Migration Execution

### Option 1: Manual SQL Execution
```bash
# 1. Execute structure migration
psql -f 20250922_100000_020_restructure_materials_tables.sql

# 2. Execute data migration
psql -f 20250922_110000_021_migrate_materials_data_from_csv.sql
```

### Option 2: Automated Script
```bash
# Dry run (see what would happen)
python migrate_materials.py --dry-run

# Verify existing data
python migrate_materials.py --verify-only

# Execute migration
python migrate_materials.py

# Custom database URL
python migrate_materials.py --db-url "postgresql://user:pass@host:port/db"
```

### Option 3: Using Run Migration Script
```bash
# Add to run_migrations.sh
./run_migrations.sh
```

## Migration Features

### Data Backup
- Automatically creates backup table: `materials_backup_YYYYMMDD_HHMMSS`
- Preserves original data before restructuring
- Allows rollback if needed

### Color Code Enhancement
- Standardizes hex color formats
- Adds '#' prefix if missing
- Defaults to `#808080` for missing colors
- Supports UI color coding

### Environmental Intelligence
- `calc_ghg`: GHG calculation factors per material
- Supports environmental impact calculations
- Different factors by material type:
  - Plastic: 1.031 kg CO2/kg
  - Metal: 1.832 kg CO2/kg
  - Paper: 5.674 kg CO2/kg
  - Glass: 0.276 kg CO2/kg
  - Aluminum: 9.127 kg CO2/kg

### Unit Management
- Standardized unit naming (TH/EN)
- Unit weight for calculations
- Special units:
  - `กิโลกรัม` / `Kilogram` (most common)
  - `ลัง` / `Carton` (for packaging)
  - `เครื่อง` / `Price per unit` (electronics)
  - `ตามราคาประเมิน...` / `Estimate price...` (special cases)

## Verification Steps

### 1. Table Structure Verification
```sql
-- Check tables exist
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('material_categories', 'main_materials', 'materials');

-- Check column structure
\d material_categories
\d main_materials
\d materials
```

### 2. Data Count Verification
```sql
-- Expected counts
SELECT
    (SELECT COUNT(*) FROM material_categories WHERE is_active = true) as categories,
    (SELECT COUNT(*) FROM main_materials WHERE is_active = true) as main_materials,
    (SELECT COUNT(*) FROM materials WHERE is_active = true) as materials;
-- Expected: 4, 11, 98
```

### 3. Relationship Verification
```sql
-- Check all materials have proper relationships
SELECT COUNT(*) FROM materials
WHERE category_id IS NULL OR main_material_id IS NULL;
-- Expected: 0

-- Sample data verification
SELECT
    cat.name_th as category,
    mm.name_th as main_material,
    m.name_th as material,
    m.color,
    m.calc_ghg
FROM materials m
JOIN material_categories cat ON m.category_id = cat.id
JOIN main_materials mm ON m.main_material_id = mm.id
LIMIT 10;
```

### 4. Index Verification
```sql
-- Check indexes exist
SELECT indexname FROM pg_indexes
WHERE tablename IN ('material_categories', 'main_materials', 'materials')
ORDER BY tablename, indexname;
```

## Performance Considerations

### Indexes Created
- `idx_material_categories_is_active`
- `idx_material_categories_code`
- `idx_main_materials_is_active`
- `idx_main_materials_code`
- `idx_materials_category_id`
- `idx_materials_main_material_id`
- `idx_materials_is_active`
- `idx_materials_tags_gin` (GIN index for text search)

### Query Optimization
```sql
-- Efficient category filtering
SELECT * FROM materials m
JOIN material_categories cat ON m.category_id = cat.id
WHERE cat.code = 'RECYCLABLE';

-- Fast text search on tags
SELECT * FROM materials
WHERE to_tsvector('english', tags) @@ to_tsquery('plastic & bottle');
```

## Rollback Strategy

### If Migration Fails
1. **Restore from backup**:
   ```sql
   -- Find backup table
   SELECT table_name FROM information_schema.tables
   WHERE table_name LIKE 'materials_backup_%';

   -- Restore data
   DROP TABLE materials;
   ALTER TABLE materials_backup_YYYYMMDD_HHMMSS RENAME TO materials;
   ```

2. **Revert table rename**:
   ```sql
   ALTER TABLE main_materials RENAME TO material_main;
   ```

3. **Drop new tables**:
   ```sql
   DROP TABLE IF EXISTS material_categories CASCADE;
   ```

### Data Recovery
- All original data preserved in backup tables
- Foreign key relationships maintained
- Can restore to previous state completely

## Post-Migration Updates Required

### 1. Application Code Updates
- Update SQLAlchemy models (already done)
- Update API endpoints to use new structure
- Update frontend components for new fields

### 2. Foreign Key Updates
- Update any existing references to `material_main` → `main_materials`
- Update transaction records foreign keys
- Update EPR system references

### 3. Business Logic Updates
- Implement category-based filtering
- Add environmental impact calculations
- Update material search functionality

## Testing Checklist

- [ ] Tables created successfully
- [ ] Data migrated correctly (98 materials)
- [ ] All relationships properly established
- [ ] No orphaned records
- [ ] Indexes created and functional
- [ ] Color codes properly formatted
- [ ] GHG factors correctly assigned
- [ ] Unit weights properly set
- [ ] Tags generated for search
- [ ] Backup tables created
- [ ] Foreign key references updated
- [ ] SQLAlchemy models compatible
- [ ] API endpoints functional
- [ ] Frontend displays correctly

## Support and Troubleshooting

### Common Issues

1. **Foreign Key Violations**
   - Check existing data references
   - Update old `material_main_id` references

2. **Missing Colors**
   - Default to `#808080` applied
   - Can be updated manually later

3. **Encoding Issues**
   - Ensure UTF-8 encoding for Thai text
   - Check CSV file encoding

4. **Performance Issues**
   - Verify indexes are created
   - Check query execution plans

### Contact
For migration support, refer to the database documentation or contact the development team.

---

**Migration Version**: v0.0.1
**Last Updated**: September 22, 2025
**Status**: Ready for production deployment