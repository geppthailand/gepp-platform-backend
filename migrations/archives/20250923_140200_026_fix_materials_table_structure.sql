-- Migration: 20250923_140200_026_fix_materials_table_structure.sql
-- Description: Fix materials table structure - remove legacy_tags and base_material_id, add fixed_tags
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- Fix materials table structure
DO $$
BEGIN
    -- Remove legacy_tags column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'legacy_tags'
    ) THEN
        RAISE NOTICE 'Removing legacy_tags column from materials table';
        ALTER TABLE materials DROP COLUMN legacy_tags;
    ELSE
        RAISE NOTICE 'legacy_tags column does not exist in materials table';
    END IF;

    -- Remove base_material_id column if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'base_material_id'
    ) THEN
        RAISE NOTICE 'Removing base_material_id column from materials table';
        -- Drop index first
        DROP INDEX IF EXISTS idx_materials_base_material;
        -- Drop column
        ALTER TABLE materials DROP COLUMN base_material_id;
    ELSE
        RAISE NOTICE 'base_material_id column does not exist in materials table';
    END IF;

    -- Add fixed_tags column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'fixed_tags'
    ) THEN
        RAISE NOTICE 'Adding fixed_tags column to materials table';
        ALTER TABLE materials ADD COLUMN fixed_tags JSONB NOT NULL DEFAULT '[]';

        -- Add comment
        COMMENT ON COLUMN materials.fixed_tags IS 'JSON array for material condition descriptions, same data type as tags';

        -- Create index
        CREATE INDEX idx_materials_fixed_tags ON materials USING GIN(fixed_tags jsonb_ops);
    ELSE
        RAISE NOTICE 'fixed_tags column already exists in materials table';
    END IF;
END $$;

-- Verify the final structure
DO $$
DECLARE
    legacy_tags_exists BOOLEAN;
    base_material_id_exists BOOLEAN;
    fixed_tags_exists BOOLEAN;
    tags_exists BOOLEAN;
BEGIN
    -- Check for unwanted columns
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'legacy_tags'
    ) INTO legacy_tags_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'base_material_id'
    ) INTO base_material_id_exists;

    -- Check for required columns
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'fixed_tags'
    ) INTO fixed_tags_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'materials' AND column_name = 'tags'
    ) INTO tags_exists;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'MATERIALS TABLE STRUCTURE VERIFICATION';
    RAISE NOTICE '============================================';

    IF NOT legacy_tags_exists THEN
        RAISE NOTICE '✅ legacy_tags column successfully removed';
    ELSE
        RAISE NOTICE '❌ legacy_tags column still exists';
    END IF;

    IF NOT base_material_id_exists THEN
        RAISE NOTICE '✅ base_material_id column successfully removed';
    ELSE
        RAISE NOTICE '❌ base_material_id column still exists';
    END IF;

    IF fixed_tags_exists THEN
        RAISE NOTICE '✅ fixed_tags column exists';
    ELSE
        RAISE NOTICE '❌ fixed_tags column missing';
    END IF;

    IF tags_exists THEN
        RAISE NOTICE '✅ tags column exists';
    ELSE
        RAISE NOTICE '❌ tags column missing';
    END IF;

    RAISE NOTICE '============================================';
    RAISE NOTICE '✅ MATERIALS TABLE STRUCTURE FIX COMPLETE';
    RAISE NOTICE '============================================';
END $$;