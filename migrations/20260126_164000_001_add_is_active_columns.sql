-- Migration: Add is_active columns to custom API tables
-- Date: 2026-01-26 16:40
-- Description: Adds missing is_active column to custom_apis and organization_custom_apis tables (BaseModel requirement)

-- Add is_active column to custom_apis table if it doesn't exist
ALTER TABLE custom_apis
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Add is_active column to organization_custom_apis table if it doesn't exist
ALTER TABLE organization_custom_apis
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Add comments
COMMENT ON COLUMN custom_apis.is_active IS 'Whether this custom API is active and available';
COMMENT ON COLUMN organization_custom_apis.is_active IS 'Whether this organization API access is active';

-- Verify the columns were added
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'custom_apis' AND column_name = 'is_active'
    ) THEN
        RAISE NOTICE '✓ custom_apis.is_active column added successfully';
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'organization_custom_apis' AND column_name = 'is_active'
    ) THEN
        RAISE NOTICE '✓ organization_custom_apis.is_active column added successfully';
    END IF;
END $$;
