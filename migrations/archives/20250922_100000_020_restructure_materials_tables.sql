-- Migration: 20250922_100000_020_restructure_materials_tables.sql
-- Description: Restructure materials table architecture
-- 1. Create material_categories table
-- 2. Rename material_main to main_materials
-- 3. Restructure materials table columns
-- Date: 2025-09-22
-- Author: Claude Code Assistant

-- ======================================
-- CREATE MATERIAL_CATEGORIES TABLE
-- ======================================

CREATE TABLE IF NOT EXISTS material_categories (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    -- Category details
    name_en VARCHAR(255),
    name_th VARCHAR(255),
    code VARCHAR(50),
    description TEXT
);

-- Add comments
COMMENT ON TABLE material_categories IS 'Material categories for classification and organization';
COMMENT ON COLUMN material_categories.name_en IS 'Category name in English';
COMMENT ON COLUMN material_categories.name_th IS 'Category name in Thai';
COMMENT ON COLUMN material_categories.code IS 'Unique category code';
COMMENT ON COLUMN material_categories.description IS 'Category description';

-- ======================================
-- RENAME MATERIAL_MAIN TO MAIN_MATERIALS
-- ======================================

-- Check if material_main table exists and rename it
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'material_main') THEN
        -- Rename the table
        ALTER TABLE material_main RENAME TO main_materials;

        -- Update any existing indexes
        ALTER INDEX IF EXISTS material_main_pkey RENAME TO main_materials_pkey;

        -- Update any existing sequences
        ALTER SEQUENCE IF EXISTS material_main_id_seq RENAME TO main_materials_id_seq;

        RAISE NOTICE 'Successfully renamed material_main to main_materials';
    ELSE
        RAISE NOTICE 'material_main table does not exist, creating main_materials table';

        -- Create main_materials table if it doesn't exist
        CREATE TABLE main_materials (
            id BIGSERIAL PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
            deleted_date TIMESTAMP WITH TIME ZONE,

            -- Main material details
            name_en VARCHAR(255),
            name_th VARCHAR(255),
            name_local VARCHAR(255),
            code VARCHAR(50)
        );

        COMMENT ON TABLE main_materials IS 'Main material types (renamed from material_main)';
    END IF;
END $$;

-- ======================================
-- HANDLE FOREIGN KEY CONSTRAINTS
-- ======================================

-- Temporarily drop foreign key constraints that reference materials table
DO $$
DECLARE
    constraint_record RECORD;
BEGIN
    -- Find all foreign key constraints that reference the materials table
    FOR constraint_record IN
        SELECT
            tc.table_name,
            tc.constraint_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND ccu.table_name = 'materials'
    LOOP
        -- Drop the constraint temporarily
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                      constraint_record.table_name, constraint_record.constraint_name);

        RAISE NOTICE 'Temporarily dropped constraint % from table %',
                     constraint_record.constraint_name, constraint_record.table_name;
    END LOOP;
END $$;

-- ======================================
-- BACKUP EXISTING MATERIALS DATA
-- ======================================

-- Create backup of existing materials table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'materials') THEN
        -- Create backup table with timestamp
        EXECUTE 'CREATE TABLE materials_backup_' || to_char(NOW(), 'YYYYMMDD_HH24MISS') || ' AS SELECT * FROM materials';
        RAISE NOTICE 'Created backup of existing materials table';
    END IF;
END $$;

-- ======================================
-- RESTRUCTURE MATERIALS TABLE
-- ======================================

-- Drop and recreate materials table with new structure
DROP TABLE IF EXISTS materials;

CREATE TABLE materials (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    -- Foreign key relationships
    category_id BIGINT REFERENCES material_categories(id),
    main_material_id BIGINT REFERENCES main_materials(id),

    -- Material properties
    tags TEXT,
    unit_name_th VARCHAR(255),
    unit_name_en VARCHAR(255),
    unit_weight DECIMAL(10,4),
    color VARCHAR(7), -- Hex color codes
    calc_ghg DECIMAL(10,4),

    -- Material names
    name_th VARCHAR(255),
    name_en VARCHAR(255)
);

-- Add comments
COMMENT ON TABLE materials IS 'Enhanced materials table with category and environmental data';
COMMENT ON COLUMN materials.category_id IS 'Reference to material category';
COMMENT ON COLUMN materials.main_material_id IS 'Reference to main material type';
COMMENT ON COLUMN materials.tags IS 'Material tags for filtering and search';
COMMENT ON COLUMN materials.unit_name_th IS 'Unit name in Thai';
COMMENT ON COLUMN materials.unit_name_en IS 'Unit name in English';
COMMENT ON COLUMN materials.unit_weight IS 'Weight per unit for calculations';
COMMENT ON COLUMN materials.color IS 'Hex color code for UI display';
COMMENT ON COLUMN materials.calc_ghg IS 'GHG calculation factor per unit';
COMMENT ON COLUMN materials.name_th IS 'Material name in Thai';
COMMENT ON COLUMN materials.name_en IS 'Material name in English';

-- ======================================
-- CREATE INDEXES
-- ======================================

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_material_categories_is_active ON material_categories(is_active);
CREATE INDEX IF NOT EXISTS idx_material_categories_code ON material_categories(code);

CREATE INDEX IF NOT EXISTS idx_main_materials_is_active ON main_materials(is_active);
CREATE INDEX IF NOT EXISTS idx_main_materials_code ON main_materials(code);

CREATE INDEX IF NOT EXISTS idx_materials_category_id ON materials(category_id);
CREATE INDEX IF NOT EXISTS idx_materials_main_material_id ON materials(main_material_id);
CREATE INDEX IF NOT EXISTS idx_materials_is_active ON materials(is_active);

-- GIN index for tag searching (if tags will be used for search)
CREATE INDEX IF NOT EXISTS idx_materials_tags_gin ON materials USING GIN (to_tsvector('english', tags))
WHERE tags IS NOT NULL;

-- ======================================
-- UPDATE FOREIGN KEY REFERENCES
-- ======================================

-- Update any foreign key references from material_main to main_materials
DO $$
DECLARE
    fk_record RECORD;
BEGIN
    -- Find all foreign key constraints referencing material_main
    FOR fk_record IN
        SELECT
            tc.table_name,
            tc.constraint_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND ccu.table_name = 'material_main'
    LOOP
        -- Drop old constraint
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                      fk_record.table_name, fk_record.constraint_name);

        -- Recreate constraint pointing to main_materials
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES main_materials(id)',
                      fk_record.table_name, fk_record.constraint_name, fk_record.column_name);

        RAISE NOTICE 'Updated foreign key constraint % on table %', fk_record.constraint_name, fk_record.table_name;
    END LOOP;
END $$;

-- ======================================
-- CREATE UPDATED_DATE TRIGGERS
-- ======================================

-- Function to update updated_date
CREATE OR REPLACE FUNCTION update_updated_date_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_date
CREATE TRIGGER update_material_categories_updated_date
    BEFORE UPDATE ON material_categories
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_main_materials_updated_date
    BEFORE UPDATE ON main_materials
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_materials_updated_date
    BEFORE UPDATE ON materials
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- ======================================
-- RECREATE FOREIGN KEY CONSTRAINTS
-- ======================================

-- Recreate foreign key constraints that were dropped earlier
-- Note: These will need to be updated manually based on the new materials table structure

DO $$
BEGIN
    -- Add back foreign key constraints for tables that reference materials
    -- This assumes the referencing tables still exist and need to reference materials.id

    -- Check if transactions table exists and add constraint
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transactions') THEN
        -- Check if transactions has a material_id column
        IF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'transactions' AND column_name = 'material_id') THEN
            EXECUTE 'ALTER TABLE transactions ADD CONSTRAINT transactions_material_id_fkey
                    FOREIGN KEY (material_id) REFERENCES materials(id)';
            RAISE NOTICE 'Added foreign key constraint: transactions.material_id → materials.id';
        END IF;
    END IF;

    -- Check if transaction_items table exists and add constraint
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transaction_items') THEN
        -- Check if transaction_items has a material_id column
        IF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'transaction_items' AND column_name = 'material_id') THEN
            EXECUTE 'ALTER TABLE transaction_items ADD CONSTRAINT transaction_items_material_id_fkey
                    FOREIGN KEY (material_id) REFERENCES materials(id)';
            RAISE NOTICE 'Added foreign key constraint: transaction_items.material_id → materials.id';
        END IF;
    END IF;

    -- Check if transaction_records table exists and add constraint
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'transaction_records') THEN
        -- Check if transaction_records has a material_id column
        IF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'transaction_records' AND column_name = 'material_id') THEN
            EXECUTE 'ALTER TABLE transaction_records ADD CONSTRAINT transaction_records_material_id_fkey
                    FOREIGN KEY (material_id) REFERENCES materials(id)';
            RAISE NOTICE 'Added foreign key constraint: transaction_records.material_id → materials.id';
        END IF;
    END IF;

    RAISE NOTICE 'Foreign key constraints recreation completed';
END $$;

-- ======================================
-- MIGRATION COMPLETION
-- ======================================

-- Print summary
DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'MATERIALS TABLE RESTRUCTURING COMPLETED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Created: material_categories table';
    RAISE NOTICE 'Renamed: material_main → main_materials';
    RAISE NOTICE 'Restructured: materials table with enhanced schema';
    RAISE NOTICE 'Added: Performance indexes and constraints';
    RAISE NOTICE 'Ready for: Data migration from CSV';
    RAISE NOTICE '============================================';
END $$;