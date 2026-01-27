-- Migration: Add organization_id column to user_roles table
-- Date: 2025-09-16 16:00:00
-- Description: Add organization_id column to user_roles table to support organization-scoped platform roles

-- Add organization_id column to user_roles table
ALTER TABLE user_roles
ADD COLUMN IF NOT EXISTS organization_id BIGINT;

-- Add foreign key constraint to organizations table
ALTER TABLE user_roles
ADD CONSTRAINT user_roles_organization_id_fkey
FOREIGN KEY (organization_id) REFERENCES organizations(id);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_user_roles_organization_id
ON user_roles(organization_id);

-- Update existing user_roles to have null organization_id (these are platform-wide roles)
-- New organization-specific roles will be created with organization_id set

-- Add helpful comment
DO $$
BEGIN
    RAISE NOTICE 'user_roles table updated successfully';
    RAISE NOTICE 'Added organization_id column and foreign key constraint';
    RAISE NOTICE 'Existing roles are platform-wide (organization_id = NULL)';
    RAISE NOTICE 'New organization-specific roles can now be created';
END $$;