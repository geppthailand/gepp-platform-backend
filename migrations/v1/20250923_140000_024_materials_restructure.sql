-- Migration: 20250923_140000_024_materials_restructure.sql
-- Description: Restructure materials system with tags and tag groups
-- Creates material_tags, material_tag_groups tables and adds JSONB columns to materials table
-- Materials reference main_materials directly via main_material_id
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- CREATE MATERIAL_TAGS TABLE
-- ======================================
CREATE TABLE material_tags (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT true,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    color VARCHAR(7) NOT NULL DEFAULT '#808080', -- Hex color code
    is_global BOOLEAN NOT NULL DEFAULT false,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE NULL,

    -- Constraints
    CONSTRAINT chk_material_tags_color CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT chk_material_tags_global_org CHECK (
        (is_global = true AND organization_id IS NULL) OR
        (is_global = false AND organization_id IS NOT NULL)
    )
);

-- Add comment for documentation
COMMENT ON TABLE material_tags IS 'Material tags for waste material conditions, can be organization-specific or global';
COMMENT ON COLUMN material_tags.is_global IS 'If true, tag is available to all organizations; if false, only to the specific organization';
COMMENT ON COLUMN material_tags.organization_id IS 'Required when is_global is false, null when is_global is true';

-- Create indexes for material_tags
CREATE INDEX idx_material_tags_organization ON material_tags(organization_id);
CREATE INDEX idx_material_tags_is_global ON material_tags(is_global);
CREATE INDEX idx_material_tags_is_active ON material_tags(is_active);
CREATE INDEX idx_material_tags_name ON material_tags(name);

-- ======================================
-- CREATE MATERIAL_TAG_GROUPS TABLE
-- ======================================
CREATE TABLE material_tag_groups (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT true,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    color VARCHAR(7) NOT NULL DEFAULT '#808080', -- Hex color code
    is_global BOOLEAN NOT NULL DEFAULT false,
    tags BIGINT[] NOT NULL DEFAULT '{}', -- Array of material_tag ids
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE NULL,

    -- Constraints
    CONSTRAINT chk_material_tag_groups_color CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT chk_material_tag_groups_global_org CHECK (
        (is_global = true AND organization_id IS NULL) OR
        (is_global = false AND organization_id IS NOT NULL)
    )
);

-- Add comment for documentation
COMMENT ON TABLE material_tag_groups IS 'Groups of similar category material tags (e.g., colors: red, blue, white; quality: good, bad)';
COMMENT ON COLUMN material_tag_groups.tags IS 'Array of material_tag IDs belonging to this group';

-- Create indexes for material_tag_groups
CREATE INDEX idx_material_tag_groups_organization ON material_tag_groups(organization_id);
CREATE INDEX idx_material_tag_groups_is_global ON material_tag_groups(is_global);
CREATE INDEX idx_material_tag_groups_is_active ON material_tag_groups(is_active);
CREATE INDEX idx_material_tag_groups_name ON material_tag_groups(name);
CREATE INDEX idx_material_tag_groups_tags ON material_tag_groups USING GIN(tags);

-- ======================================
-- UPDATE MAIN_MATERIALS TABLE
-- ======================================
-- Add material_tag_groups column to main_materials for referencing applicable tag groups

DO $$
BEGIN
    -- Add material_tag_groups column to main_materials if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'main_materials' AND column_name = 'material_tag_groups'
    ) THEN
        RAISE NOTICE 'Adding material_tag_groups column to main_materials table';
        ALTER TABLE main_materials ADD COLUMN material_tag_groups BIGINT[] NOT NULL DEFAULT '{}';
    ELSE
        RAISE NOTICE 'material_tag_groups column already exists in main_materials table';
    END IF;
END $$;

-- Add comment and index for main_materials.material_tag_groups
COMMENT ON COLUMN main_materials.material_tag_groups IS 'Array of material_tag_group IDs that can be applied to materials of this main material type';

-- Create index for material_tag_groups array column
DROP INDEX IF EXISTS idx_main_materials_tag_groups;
CREATE INDEX idx_main_materials_tag_groups ON main_materials USING GIN(material_tag_groups);

-- ======================================
-- BACKUP EXISTING MATERIALS TABLE
-- ======================================
CREATE TABLE materials_backup_20250923 AS
SELECT * FROM materials;

-- ======================================
-- MODIFY MATERIALS TABLE STRUCTURE
-- ======================================

-- Keep existing columns and add new ones
-- Note: category_id and main_material_id will be kept for backward compatibility
-- The new base_material_id will be used for mapping during transition

-- Handle existing tags column and add new columns
DO $$
BEGIN
    -- Check if tags column exists and what type it is
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'tags'
    ) THEN
        -- Check if it's already JSONB
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'materials' AND column_name = 'tags' AND data_type = 'jsonb'
        ) THEN
            -- Drop existing text tags column (not preserving legacy data)
            RAISE NOTICE 'Removing existing text tags column and creating new JSONB tags column';
            ALTER TABLE materials DROP COLUMN tags;

            -- Add new JSONB tags column
            ALTER TABLE materials ADD COLUMN tags JSONB NOT NULL DEFAULT '[]';
        ELSE
            RAISE NOTICE 'Tags column is already JSONB type, no conversion needed';
        END IF;
    ELSE
        -- Add new JSONB tags column
        RAISE NOTICE 'Adding new JSONB tags column';
        ALTER TABLE materials ADD COLUMN tags JSONB NOT NULL DEFAULT '[]';
    END IF;

    -- Add fixed_tags column for material condition descriptions
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'fixed_tags'
    ) THEN
        RAISE NOTICE 'Adding fixed_tags JSONB column for material condition descriptions';
        ALTER TABLE materials ADD COLUMN fixed_tags JSONB NOT NULL DEFAULT '[]';
    END IF;
END $$;

-- Add comments for new structure
COMMENT ON COLUMN materials.tags IS 'JSON array of tuples mapping material_tag_groups to material_tags: [(tag_group_id, tag_id)]';
COMMENT ON COLUMN materials.fixed_tags IS 'JSON array for material condition descriptions, same data type as tags';
COMMENT ON COLUMN materials.category_id IS 'Reference to material_categories for material classification';
COMMENT ON COLUMN materials.main_material_id IS 'Reference to main_materials for base material type';

-- Create indexes for new columns
DROP INDEX IF EXISTS idx_materials_tags;
CREATE INDEX idx_materials_tags ON materials USING GIN(tags jsonb_ops);

DROP INDEX IF EXISTS idx_materials_fixed_tags;
CREATE INDEX idx_materials_fixed_tags ON materials USING GIN(fixed_tags jsonb_ops);

-- Update trigger function for updated_date
CREATE OR REPLACE FUNCTION update_updated_date_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add updated_date triggers for new tables
CREATE TRIGGER update_material_tags_updated_date
    BEFORE UPDATE ON material_tags
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_material_tag_groups_updated_date
    BEFORE UPDATE ON material_tag_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- ======================================
-- VERIFICATION AND COMPLETION
-- ======================================

DO $$
DECLARE
    material_tags_count INTEGER;
    material_tag_groups_count INTEGER;
    materials_backup_count INTEGER;
    materials_with_tags_count INTEGER;
    materials_with_fixed_tags_count INTEGER;
    main_materials_with_tag_groups_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO material_tags_count FROM material_tags;
    SELECT COUNT(*) INTO material_tag_groups_count FROM material_tag_groups;
    SELECT COUNT(*) INTO materials_backup_count FROM materials_backup_20250923;

    -- Check materials table columns
    SELECT COUNT(*) INTO materials_with_tags_count FROM materials WHERE tags IS NOT NULL;
    SELECT COUNT(*) INTO materials_with_fixed_tags_count FROM materials WHERE fixed_tags IS NOT NULL;

    -- Check main_materials table
    SELECT COUNT(*) INTO main_materials_with_tag_groups_count FROM main_materials WHERE material_tag_groups IS NOT NULL;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'MATERIALS RESTRUCTURE MIGRATION FINISHED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Material tags table created: % records', material_tags_count;
    RAISE NOTICE 'Material tag groups table created: % records', material_tag_groups_count;
    RAISE NOTICE 'Main materials with tag groups column: % records', main_materials_with_tag_groups_count;
    RAISE NOTICE 'Materials backup created: % records', materials_backup_count;
    RAISE NOTICE 'Materials with tags column: % records', materials_with_tags_count;
    RAISE NOTICE 'Materials with fixed_tags column: % records', materials_with_fixed_tags_count;
    RAISE NOTICE 'Tables restructured with new JSONB and array columns';
    RAISE NOTICE '✅ MIGRATION COMPLETE - New table structure ready!';
    RAISE NOTICE 'Next step: Populate material tags and tag groups in main_materials';
    RAISE NOTICE '============================================';
END $$;

-- ======================================
-- ROLLBACK INSTRUCTIONS
-- ======================================
--
-- To undo this migration, run the following commands:
--
-- -- Step 1: Drop indexes
-- DROP INDEX IF EXISTS idx_materials_tags;
-- DROP INDEX IF EXISTS idx_materials_fixed_tags;
-- DROP INDEX IF EXISTS idx_main_materials_tag_groups;
-- DROP INDEX IF EXISTS idx_material_tag_groups_tags;
-- DROP INDEX IF EXISTS idx_material_tag_groups_name;
-- DROP INDEX IF EXISTS idx_material_tag_groups_is_active;
-- DROP INDEX IF EXISTS idx_material_tag_groups_is_global;
-- DROP INDEX IF EXISTS idx_material_tag_groups_organization;
-- DROP INDEX IF EXISTS idx_material_tags_name;
-- DROP INDEX IF EXISTS idx_material_tags_is_active;
-- DROP INDEX IF EXISTS idx_material_tags_is_global;
-- DROP INDEX IF EXISTS idx_material_tags_organization;
--
-- -- Step 2: Drop triggers
-- DROP TRIGGER IF EXISTS update_material_tag_groups_updated_date ON material_tag_groups;
-- DROP TRIGGER IF EXISTS update_material_tags_updated_date ON material_tags;
--
-- -- Step 3: Remove new columns from tables
-- ALTER TABLE materials DROP COLUMN IF EXISTS tags;
-- ALTER TABLE materials DROP COLUMN IF EXISTS fixed_tags;
-- ALTER TABLE main_materials DROP COLUMN IF EXISTS material_tag_groups;
--
-- -- Step 4: Drop new tables (in correct order due to foreign keys)
-- DROP TABLE IF EXISTS material_tag_groups;
-- DROP TABLE IF EXISTS material_tags;
--
-- -- Step 5: Drop backup table if desired
-- DROP TABLE IF EXISTS materials_backup_20250923;