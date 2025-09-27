-- Migration: Add key field to organization_roles table
-- Date: 2025-09-16 15:00:00
-- Description: Add key field to organization_roles for role identification and enable organization-specific roles

-- Add key column to organization_roles
ALTER TABLE organization_roles ADD COLUMN IF NOT EXISTS key VARCHAR(50);

-- Update existing roles to have keys (if any exist)
-- Note: This is safe to run even if no data exists
UPDATE organization_roles SET key = LOWER(REPLACE(name, ' ', '_')) WHERE key IS NULL;

-- Add unique constraint for key within organization
CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_roles_org_key
ON organization_roles(organization_id, key);

-- Add index for better performance
CREATE INDEX IF NOT EXISTS idx_organization_roles_organization_id
ON organization_roles(organization_id);

-- Verify the changes
DO $$
BEGIN
    RAISE NOTICE 'organization_roles table updated successfully';
    RAISE NOTICE 'Added key column and unique constraint on (organization_id, key)';
END $$;