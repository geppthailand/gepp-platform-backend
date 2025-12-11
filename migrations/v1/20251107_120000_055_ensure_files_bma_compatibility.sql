-- Migration: Ensure files table has BMA integration compatibility
-- Description: Idempotent migration to ensure observation and source columns exist
-- Version: 055
-- Date: 2025-11-07 12:00:00

-- Create file_source ENUM type if not exists
DO $$ BEGIN
    CREATE TYPE file_source AS ENUM ('s3', 'ext');
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'Type file_source already exists, skipping creation';
END $$;

-- Add observation column to files table if not exists
DO $$ BEGIN
    ALTER TABLE files ADD COLUMN observation JSONB DEFAULT NULL;
    RAISE NOTICE 'Added observation column to files table';
EXCEPTION
    WHEN duplicate_column THEN
        RAISE NOTICE 'Column files.observation already exists, skipping';
END $$;

-- Add source column to files table if not exists
DO $$ BEGIN
    ALTER TABLE files ADD COLUMN source file_source DEFAULT 's3';
    RAISE NOTICE 'Added source column to files table';
EXCEPTION
    WHEN duplicate_column THEN
        RAISE NOTICE 'Column files.source already exists, skipping';
END $$;

-- Add comments to explain the columns (idempotent)
COMMENT ON COLUMN files.observation IS 'AI-extracted observations and descriptions from image analysis. Stores structured data about what was identified in the image for audit purposes.';
COMMENT ON COLUMN files.source IS 'File source type: "s3" for S3-stored files requiring presigned URLs, "ext" for external URLs that can be used directly.';

-- Create index for observation queries (useful for searching observations)
CREATE INDEX IF NOT EXISTS idx_files_observation
ON files USING gin(observation)
WHERE observation IS NOT NULL;

-- Create index for source queries
CREATE INDEX IF NOT EXISTS idx_files_source
ON files(source);

-- Verify columns exist
DO $$
DECLARE
    has_observation BOOLEAN;
    has_source BOOLEAN;
BEGIN
    -- Check if observation column exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'files' AND column_name = 'observation'
    ) INTO has_observation;

    -- Check if source column exists
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'files' AND column_name = 'source'
    ) INTO has_source;

    -- Report status
    IF has_observation AND has_source THEN
        RAISE NOTICE '✓ Migration 055: SUCCESS - Both observation and source columns verified in files table';
    ELSIF has_observation AND NOT has_source THEN
        RAISE WARNING '✗ Migration 055: FAILED - observation column exists but source column missing';
    ELSIF NOT has_observation AND has_source THEN
        RAISE WARNING '✗ Migration 055: FAILED - source column exists but observation column missing';
    ELSE
        RAISE WARNING '✗ Migration 055: FAILED - Both columns missing from files table';
    END IF;
END $$;
