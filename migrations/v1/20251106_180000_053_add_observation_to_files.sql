-- Migration: Add observation and source columns to files table
-- Description: Add JSONB column for AI-extracted observations and ENUM for file source
-- Version: 053
-- Date: 2025-11-06 18:00:00

-- Create file_source ENUM type
DO $$ BEGIN
    CREATE TYPE file_source AS ENUM ('s3', 'ext');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add observation column to files table
ALTER TABLE files
ADD COLUMN IF NOT EXISTS observation JSONB DEFAULT NULL;

-- Add source column to files table
ALTER TABLE files
ADD COLUMN IF NOT EXISTS source file_source DEFAULT 's3';

-- Add comments to explain the columns
COMMENT ON COLUMN files.observation IS 'AI-extracted observations and descriptions from image analysis. Stores structured data about what was identified in the image for audit purposes.';
COMMENT ON COLUMN files.source IS 'File source type: "s3" for S3-stored files requiring presigned URLs, "ext" for external URLs that can be used directly.';

-- Create index for observation queries (useful for searching observations)
CREATE INDEX IF NOT EXISTS idx_files_observation
ON files USING gin(observation)
WHERE observation IS NOT NULL;

-- Create index for source queries
CREATE INDEX IF NOT EXISTS idx_files_source
ON files(source);

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 053: Added observation and source columns to files table';
END $$;
