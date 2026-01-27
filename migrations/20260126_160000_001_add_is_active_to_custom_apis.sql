-- Migration: Add is_active column to custom_apis and organization_custom_apis tables
-- Date: 2026-01-26
-- Description: Adds missing is_active column that BaseModel expects

-- Add is_active column to custom_apis table
ALTER TABLE custom_apis
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Add is_active column to organization_custom_apis table
ALTER TABLE organization_custom_apis
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Update comments
COMMENT ON COLUMN custom_apis.is_active IS 'Whether this custom API is active and available';
COMMENT ON COLUMN organization_custom_apis.is_active IS 'Whether this organization API access is active';
