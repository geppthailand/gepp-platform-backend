-- Migration: Refactor business roles to organization roles
-- Date: 2025-09-16 13:00:00
-- Description:
--   1. Rename business_role_id to organization_role_id in user_locations table
--   2. Update foreign key constraint to reference organization_roles instead of user_business_roles
--   3. Drop UserOrganizationRole mapping table (user_organization_role_mapping)
--   4. Update user_invitations table to use intended_organization_role

-- Begin transaction
BEGIN;

-- Step 1: Remove existing foreign key constraint for business_role_id
ALTER TABLE user_locations DROP CONSTRAINT IF EXISTS user_locations_business_role_id_fkey;

-- Step 2: Rename business_role_id column to organization_role_id
ALTER TABLE user_locations RENAME COLUMN business_role_id TO organization_role_id;

-- Step 3: Add new foreign key constraint to organization_roles table
ALTER TABLE user_locations
ADD CONSTRAINT user_locations_organization_role_id_fkey
FOREIGN KEY (organization_role_id) REFERENCES organization_roles(id);

-- Step 4: Update index name
DROP INDEX IF EXISTS idx_user_locations_business_role;
CREATE INDEX IF NOT EXISTS idx_user_locations_organization_role ON user_locations(organization_role_id);

-- Step 5: Drop the user_organization_role_mapping table if it exists
DROP TABLE IF EXISTS user_organization_role_mapping CASCADE;

-- Step 6: Update user_invitations table - rename intended_business_role to intended_organization_role
-- First check if the column exists and rename it
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_invitations'
        AND column_name = 'intended_business_role'
    ) THEN
        ALTER TABLE user_invitations RENAME COLUMN intended_business_role TO intended_organization_role_id;

        -- Update the column type to be a foreign key to organization_roles
        ALTER TABLE user_invitations ALTER COLUMN intended_organization_role_id TYPE BIGINT;

        -- Add foreign key constraint
        ALTER TABLE user_invitations
        ADD CONSTRAINT user_invitations_intended_organization_role_id_fkey
        FOREIGN KEY (intended_organization_role_id) REFERENCES organization_roles(id);
    END IF;
END $$;

-- Step 7: Create organization_roles table if it doesn't exist (should already exist from subscription_models)
CREATE TABLE IF NOT EXISTS organization_roles (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Step 8: Create organization_permissions table if it doesn't exist
CREATE TABLE IF NOT EXISTS organization_permissions (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    category VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Step 9: Create organization_role_permissions junction table if it doesn't exist
CREATE TABLE IF NOT EXISTS organization_role_permissions (
    role_id BIGINT NOT NULL REFERENCES organization_roles(id),
    permission_id BIGINT NOT NULL REFERENCES organization_permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

-- Step 10: Insert default organization permissions
INSERT INTO organization_permissions (code, name, description, category) VALUES
('transaction.create', 'Create Transactions', 'Create new waste transactions', 'transaction'),
('transaction.edit', 'Edit Transactions', 'Edit existing waste transactions', 'transaction'),
('transaction.view', 'View Transactions', 'View waste transactions', 'transaction'),
('transaction.delete', 'Delete Transactions', 'Delete waste transactions', 'transaction'),
('user_management.invite', 'Invite Users', 'Invite new users to organization', 'user_management'),
('user_management.suspend', 'Suspend Users', 'Suspend user accounts', 'user_management'),
('user_management.view', 'View Users', 'View organization users', 'user_management'),
('role.assign', 'Assign Roles', 'Assign roles to users', 'user_management'),
('organization.manage', 'Manage Organization', 'Manage organization settings', 'organization'),
('reporting.generate', 'Generate Reports', 'Generate various reports', 'reporting'),
('reporting.view', 'View Reports', 'View generated reports', 'reporting'),
('audit.perform', 'Perform Audits', 'Perform audit operations', 'audit'),
('location.create', 'Create Locations', 'Create new locations', 'location'),
('location.view', 'View Locations', 'View location information', 'location'),
('settings.manage', 'Manage Settings', 'Manage system settings', 'settings')
ON CONFLICT (code) DO NOTHING;

-- Step 11: Create default organization roles for each organization
INSERT INTO organization_roles (organization_id, name, description, is_system)
SELECT
    o.id,
    'Administrator',
    'Full access to all organization features',
    true
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM organization_roles
    WHERE organization_id = o.id AND name = 'Administrator'
);

INSERT INTO organization_roles (organization_id, name, description, is_system)
SELECT
    o.id,
    'Manager',
    'Management access with user and transaction oversight',
    true
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM organization_roles
    WHERE organization_id = o.id AND name = 'Manager'
);

INSERT INTO organization_roles (organization_id, name, description, is_system)
SELECT
    o.id,
    'Operator',
    'Standard user with transaction access',
    true
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM organization_roles
    WHERE organization_id = o.id AND name = 'Operator'
);

INSERT INTO organization_roles (organization_id, name, description, is_system)
SELECT
    o.id,
    'Viewer',
    'Read-only access to organization data',
    true
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM organization_roles
    WHERE organization_id = o.id AND name = 'Viewer'
);

-- Step 12: Assign permissions to default roles
-- Administrator gets all permissions
INSERT INTO organization_role_permissions (role_id, permission_id)
SELECT
    or_table.id,
    op.id
FROM organization_roles or_table
CROSS JOIN organization_permissions op
WHERE or_table.name = 'Administrator'
ON CONFLICT DO NOTHING;

-- Manager gets most permissions except organization management
INSERT INTO organization_role_permissions (role_id, permission_id)
SELECT
    or_table.id,
    op.id
FROM organization_roles or_table
CROSS JOIN organization_permissions op
WHERE or_table.name = 'Manager'
AND op.code NOT IN ('organization.manage', 'settings.manage')
ON CONFLICT DO NOTHING;

-- Operator gets transaction and basic permissions
INSERT INTO organization_role_permissions (role_id, permission_id)
SELECT
    or_table.id,
    op.id
FROM organization_roles or_table
CROSS JOIN organization_permissions op
WHERE or_table.name = 'Operator'
AND op.code IN (
    'transaction.create', 'transaction.edit', 'transaction.view',
    'location.view', 'reporting.view'
)
ON CONFLICT DO NOTHING;

-- Viewer gets only view permissions
INSERT INTO organization_role_permissions (role_id, permission_id)
SELECT
    or_table.id,
    op.id
FROM organization_roles or_table
CROSS JOIN organization_permissions op
WHERE or_table.name = 'Viewer'
AND op.code IN (
    'transaction.view', 'location.view', 'reporting.view', 'user_management.view'
)
ON CONFLICT DO NOTHING;

-- Step 13: Create triggers for updated_date on new tables
CREATE OR REPLACE FUNCTION update_updated_date_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_organization_roles_updated_date
    BEFORE UPDATE ON organization_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_organization_permissions_updated_date
    BEFORE UPDATE ON organization_permissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Commit transaction
COMMIT;