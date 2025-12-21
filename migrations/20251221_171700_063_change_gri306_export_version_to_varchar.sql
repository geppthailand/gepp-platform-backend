-- Migration: Change gri306_export.version from integer to varchar(255)
-- Description: Changes the version column in gri306_export table from integer to varchar(255) to support version names like "Test 1"
-- Date: 2025-12-21 17:17:00

-- Change version column type from integer to varchar(255)
ALTER TABLE public.gri306_export
ALTER COLUMN version TYPE varchar(255) USING version::text;

-- Update comment for the version column
COMMENT ON COLUMN public.gri306_export.version IS 'Version name or identifier of the export (e.g., "Test 1", "v1.0", etc.)';

