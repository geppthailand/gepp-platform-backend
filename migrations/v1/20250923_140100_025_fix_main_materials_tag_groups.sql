-- Migration: 20250923_140100_025_fix_main_materials_tag_groups.sql
-- Description: Fix main_materials table to add material_tag_groups column
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- Add material_tag_groups column to main_materials table
DO $$
BEGIN
    -- Check if column exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'main_materials' AND column_name = 'material_tag_groups'
    ) THEN
        RAISE NOTICE 'Adding material_tag_groups column to main_materials table';
        ALTER TABLE main_materials ADD COLUMN material_tag_groups BIGINT[] NOT NULL DEFAULT '{}';

        -- Add comment
        COMMENT ON COLUMN main_materials.material_tag_groups IS 'Array of material_tag_group IDs that can be applied to materials of this main material type';

        -- Create index
        CREATE INDEX idx_main_materials_tag_groups ON main_materials USING GIN(material_tag_groups);

        RAISE NOTICE '✅ Successfully added material_tag_groups column to main_materials';
    ELSE
        RAISE NOTICE 'material_tag_groups column already exists in main_materials table';
    END IF;
END $$;

-- Verify the column was added
DO $$
DECLARE
    column_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'main_materials' AND column_name = 'material_tag_groups'
    ) INTO column_exists;

    IF column_exists THEN
        RAISE NOTICE '✅ VERIFICATION PASSED: material_tag_groups column exists in main_materials';
    ELSE
        RAISE NOTICE '❌ VERIFICATION FAILED: material_tag_groups column missing from main_materials';
    END IF;
END $$;