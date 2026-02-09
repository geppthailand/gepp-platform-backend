-- Migration: Create user_tenants table (same pattern as user_location_tags)
-- Date: 2026-02-02
-- Description: Creates the user_tenants table for managing tenants.
--              Tenants are organization-level and can be mapped to multiple locations (many-to-many).
--              Also adds tenants JSONB column to user_locations.

-- Create user_tenants table
CREATE TABLE IF NOT EXISTS user_tenants (
    id BIGSERIAL PRIMARY KEY,

    -- Basic info
    name VARCHAR(255) NOT NULL,
    note TEXT,

    -- Relationships
    user_location_id BIGINT REFERENCES user_locations(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    created_by_id BIGINT REFERENCES user_locations(id),

    -- Many-to-many: JSONB array of user_location IDs this tenant is associated with
    user_locations JSONB DEFAULT '[]'::jsonb,

    -- Members (JSONB array of user_location IDs assigned to this tenant)
    members JSONB DEFAULT '[]'::jsonb,

    -- Event date range (optional)
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,

    -- Standard audit fields (from BaseModel)
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_user_tenants_user_location_id ON user_tenants(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_tenants_organization_id ON user_tenants(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_tenants_is_active ON user_tenants(is_active);
CREATE INDEX IF NOT EXISTS idx_user_tenants_deleted_date ON user_tenants(deleted_date);

COMMENT ON TABLE user_tenants IS 'Tenants for categorizing and grouping locations (same pattern as location tags)';
COMMENT ON COLUMN user_tenants.user_locations IS 'JSONB array of user_location IDs this tenant is associated with';
COMMENT ON COLUMN user_tenants.members IS 'JSONB array of user_location IDs assigned as tenant members';

-- Add tenants column to user_locations if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_locations'
        AND column_name = 'tenants'
    ) THEN
        ALTER TABLE user_locations
        ADD COLUMN tenants JSONB DEFAULT '[]'::jsonb;

        RAISE NOTICE 'Added tenants column to user_locations';
    ELSE
        RAISE NOTICE 'tenants column already exists in user_locations';
    END IF;
END $$;

COMMENT ON COLUMN user_locations.tenants IS 'JSONB array of user_tenant IDs associated with this location';
