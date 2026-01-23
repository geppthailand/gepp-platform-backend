-- Migration: Add Foreign Key Constraints
-- Date: 2025-01-09 12:15:00
-- Description: Adds foreign key constraints between tables created in previous migrations

-- Add organization_id FK to user_locations
ALTER TABLE user_locations 
ADD CONSTRAINT IF NOT EXISTS fk_user_locations_organization 
FOREIGN KEY (organization_id) REFERENCES organizations(id);

-- Add owner_id FK to organizations
ALTER TABLE organizations 
ADD CONSTRAINT IF NOT EXISTS fk_organizations_owner 
FOREIGN KEY (owner_id) REFERENCES user_locations(id);

-- Add subscription_id FK to organizations
ALTER TABLE organizations 
ADD CONSTRAINT IF NOT EXISTS fk_organizations_subscription 
FOREIGN KEY (subscription_id) REFERENCES subscriptions(id);

-- Add user_location_id FK to user_organization_roles
ALTER TABLE user_organization_roles 
ADD CONSTRAINT IF NOT EXISTS fk_user_organization_roles_user 
FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE;

-- Add user_location_id FK to user_organization_role_mapping
ALTER TABLE user_organization_role_mapping 
ADD CONSTRAINT IF NOT EXISTS fk_user_organization_role_mapping_user 
FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE;

-- Create indexes for the new foreign keys
CREATE INDEX IF NOT EXISTS idx_user_organization_roles_user ON user_organization_roles(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_organization_roles_org ON user_organization_roles(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_organization_roles_role ON user_organization_roles(role_id);

CREATE INDEX IF NOT EXISTS idx_user_organization_role_mapping_user ON user_organization_role_mapping(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_organization_role_mapping_org ON user_organization_role_mapping(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_organization_role_mapping_role ON user_organization_role_mapping(role_id);