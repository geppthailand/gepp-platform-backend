-- Migration: Add SystemRole table and system_role_id to organizations
-- Version: 20250917_153000_015
-- Description: Create SystemRole table and add system_role_id foreign key to organizations table

-- Create system_roles table
CREATE TABLE IF NOT EXISTS system_roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    permissions TEXT, -- JSON column for storing system permissions
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_system_roles_name ON system_roles(name);

-- Add system_role_id column to organizations table
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS system_role_id BIGINT REFERENCES system_roles(id);

-- Add index for the foreign key
CREATE INDEX IF NOT EXISTS idx_organizations_system_role_id ON organizations(system_role_id);

-- Insert default system roles for organizations
INSERT INTO system_roles (name, description, permissions) VALUES
('basic', 'Basic system access - Standard business features', '{"transactions": true, "basic_reports": true, "user_management": false, "advanced_analytics": false, "api_access": false}'),
('premium', 'Premium system access - Enhanced business features', '{"transactions": true, "basic_reports": true, "advanced_reports": true, "user_management": true, "basic_analytics": true, "api_access": false}'),
('enterprise', 'Enterprise system access - Full platform capabilities', '{"transactions": true, "basic_reports": true, "advanced_reports": true, "user_management": true, "advanced_analytics": true, "api_access": true, "custom_integrations": true, "bulk_operations": true}'),
('admin', 'System administrator - Full platform control', '{"*": true}');

-- Update organizations to have default basic system role if no role is set
-- This can be run after the column is added
-- UPDATE organizations SET system_role_id = (SELECT id FROM system_roles WHERE name = 'basic' LIMIT 1) WHERE system_role_id IS NULL;

-- Create trigger to auto-update updated_date
CREATE OR REPLACE FUNCTION update_system_roles_updated_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_update_system_roles_updated_date
    BEFORE UPDATE ON system_roles
    FOR EACH ROW
    EXECUTE FUNCTION update_system_roles_updated_date();