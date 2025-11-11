-- Verification Script for files table schema
-- Run this to check if the files table has all required columns for BMA integration

-- Check if file_source enum exists
SELECT
    CASE
        WHEN EXISTS (
            SELECT 1 FROM pg_type
            WHERE typname = 'file_source'
        ) THEN '✓ file_source ENUM exists'
        ELSE '✗ file_source ENUM missing'
    END AS enum_check;

-- Check files table columns
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'files'
    AND column_name IN ('observation', 'source', 'url', 's3_key', 's3_bucket')
ORDER BY
    CASE column_name
        WHEN 'url' THEN 1
        WHEN 's3_key' THEN 2
        WHEN 's3_bucket' THEN 3
        WHEN 'source' THEN 4
        WHEN 'observation' THEN 5
    END;

-- Check indexes on files table
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'files'
    AND indexname IN ('idx_files_observation', 'idx_files_source')
ORDER BY indexname;

-- Sample files data to verify source column
SELECT
    id,
    file_type,
    source,
    LEFT(url, 80) AS url_preview,
    LEFT(s3_key, 60) AS s3_key_preview,
    observation IS NOT NULL AS has_observation,
    created_at
FROM files
ORDER BY created_at DESC
LIMIT 5;

-- Count files by source type
SELECT
    source,
    COUNT(*) AS count
FROM files
WHERE is_active = true
GROUP BY source
ORDER BY count DESC;
