-- Migration: Organization and Subscription System
-- Date: 2025-01-09 12:10:00
-- Description: Creates organization, subscription, and permission management tables

-- Organization Info
CREATE TABLE IF NOT EXISTS organization_info (
    id BIGSERIAL PRIMARY KEY,
    company_name VARCHAR(255),
    company_name_th VARCHAR(255),
    company_name_en VARCHAR(255),
    display_name VARCHAR(255),
    
    -- Business details
    business_type TEXT,
    business_industry TEXT,
    business_sub_industry TEXT,
    account_type TEXT,
    
    -- Legal and registration
    tax_id VARCHAR(50),
    national_id VARCHAR(50),
    business_registration_certificate TEXT,
    
    -- Contact information
    phone_number VARCHAR(50),
    company_phone VARCHAR(50),
    company_email VARCHAR(255),
    
    -- Address information
    address TEXT,
    country_id BIGINT REFERENCES location_countries(id),
    province_id BIGINT REFERENCES location_provinces(id),
    district_id BIGINT REFERENCES location_districts(id),
    subdistrict_id BIGINT REFERENCES location_subdistricts(id),
    
    -- Images and documents
    profile_image_url TEXT,
    company_logo_url TEXT,
    
    -- Financial information
    footprint DECIMAL(10, 2),
    
    -- Project and operational details
    project_id VARCHAR(100),
    use_purpose TEXT,
    
    -- Additional metadata
    application_date TEXT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Organizations
CREATE TABLE IF NOT EXISTS organizations (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    organization_info_id BIGINT REFERENCES organization_info(id),
    owner_id BIGINT, -- Will reference user_locations(id) after it's created
    subscription_id BIGINT, -- Will reference subscriptions(id) after it's created
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Subscription Plans
CREATE TABLE IF NOT EXISTS subscription_plans (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    price_monthly INTEGER DEFAULT 0, -- Price in cents
    price_yearly INTEGER DEFAULT 0,
    
    -- Limits
    max_users INTEGER DEFAULT 1,
    max_transactions_monthly INTEGER DEFAULT 100,
    max_storage_gb INTEGER DEFAULT 1,
    max_api_calls_daily INTEGER DEFAULT 1000,
    
    -- Features as JSON
    features JSONB,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    plan_id BIGINT NOT NULL REFERENCES subscription_plans(id),
    
    status VARCHAR(50) DEFAULT 'active', -- active, suspended, cancelled, expired
    trial_ends_at TIMESTAMP WITH TIME ZONE,
    current_period_starts_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    current_period_ends_at TIMESTAMP WITH TIME ZONE,
    
    -- Usage tracking
    users_count INTEGER DEFAULT 1,
    transactions_count_this_month INTEGER DEFAULT 0,
    storage_used_gb INTEGER DEFAULT 0,
    api_calls_today INTEGER DEFAULT 0,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- System Permissions (subscription-level)
CREATE TABLE IF NOT EXISTS system_permissions (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    category VARCHAR(100),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Organization Permissions (internal role-based)
CREATE TABLE IF NOT EXISTS organization_permissions (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    category VARCHAR(100),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Organization Roles
CREATE TABLE IF NOT EXISTS organization_roles (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE, -- True for default roles that can't be deleted
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(organization_id, name)
);

-- Junction Tables
CREATE TABLE IF NOT EXISTS subscription_permissions (
    subscription_id BIGINT REFERENCES subscriptions(id) ON DELETE CASCADE,
    permission_id BIGINT REFERENCES system_permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (subscription_id, permission_id)
);

CREATE TABLE IF NOT EXISTS organization_role_permissions (
    role_id BIGINT REFERENCES organization_roles(id) ON DELETE CASCADE,
    permission_id BIGINT REFERENCES organization_permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_organization_roles (
    user_location_id BIGINT, -- Will add FK constraint later
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    role_id BIGINT REFERENCES organization_roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_location_id, organization_id, role_id)
);

-- User Organization Role Mapping (primary role per organization)
CREATE TABLE IF NOT EXISTS user_organization_role_mapping (
    user_location_id BIGINT NOT NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES organization_roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_location_id, organization_id)
);

-- Add foreign key constraints after user_locations table exists
-- These will be added in a later migration

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_organizations_owner ON organizations(owner_id);
CREATE INDEX IF NOT EXISTS idx_organizations_subscription ON organizations(subscription_id);
CREATE INDEX IF NOT EXISTS idx_organizations_info ON organizations(organization_info_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_organization ON subscriptions(organization_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan ON subscriptions(plan_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

CREATE INDEX IF NOT EXISTS idx_organization_roles_organization ON organization_roles(organization_id);
CREATE INDEX IF NOT EXISTS idx_organization_roles_name ON organization_roles(organization_id, name);

CREATE INDEX IF NOT EXISTS idx_system_permissions_code ON system_permissions(code);
CREATE INDEX IF NOT EXISTS idx_system_permissions_category ON system_permissions(category);

CREATE INDEX IF NOT EXISTS idx_organization_permissions_code ON organization_permissions(code);
CREATE INDEX IF NOT EXISTS idx_organization_permissions_category ON organization_permissions(category);

-- Create triggers
CREATE TRIGGER update_organization_info_updated_date BEFORE UPDATE ON organization_info
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_organizations_updated_date BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_subscription_plans_updated_date BEFORE UPDATE ON subscription_plans
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_subscriptions_updated_date BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_system_permissions_updated_date BEFORE UPDATE ON system_permissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_organization_permissions_updated_date BEFORE UPDATE ON organization_permissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_organization_roles_updated_date BEFORE UPDATE ON organization_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Insert default subscription plan
INSERT INTO subscription_plans (
    name, display_name, description,
    price_monthly, price_yearly,
    max_users, max_transactions_monthly, max_storage_gb, max_api_calls_daily,
    features
) VALUES (
    'free', 'Free Plan', 'Basic features for getting started',
    0, 0,
    5, 100, 1, 1000,
    '["Basic waste tracking", "Up to 5 users", "100 transactions/month", "1GB storage", "Basic reporting"]'::jsonb
) ON CONFLICT (name) DO NOTHING;

-- Insert default system permissions
INSERT INTO system_permissions (code, name, description, category) VALUES
    ('waste_transaction.create', 'Create Waste Transaction', 'Create new waste transactions', 'waste_transaction'),
    ('waste_transaction.view', 'View Waste Transaction', 'View waste transactions', 'waste_transaction'),
    ('waste_transaction.edit', 'Edit Waste Transaction', 'Edit existing waste transactions', 'waste_transaction'),
    ('waste_transaction.delete', 'Delete Waste Transaction', 'Delete waste transactions', 'waste_transaction'),
    ('reporting.basic', 'Basic Reporting', 'Access basic reports', 'reporting'),
    ('reporting.advanced', 'Advanced Reporting', 'Access advanced reports and analytics', 'reporting'),
    ('analytics.dashboard', 'Analytics Dashboard', 'Access analytics dashboard', 'analytics'),
    ('user_management.basic', 'Basic User Management', 'Manage users within limit', 'user_management'),
    ('api.basic', 'Basic API Access', 'Basic API access with rate limits', 'api'),
    ('api.advanced', 'Advanced API Access', 'Advanced API access with higher limits', 'api')
ON CONFLICT (code) DO NOTHING;

-- Insert default organization permissions
INSERT INTO organization_permissions (code, name, description, category) VALUES
    ('transaction.create', 'Create Transaction', 'Create waste transactions', 'transaction'),
    ('transaction.view', 'View Transaction', 'View waste transactions', 'transaction'),
    ('transaction.edit', 'Edit Transaction', 'Edit waste transactions', 'transaction'),
    ('transaction.delete', 'Delete Transaction', 'Delete waste transactions', 'transaction'),
    ('transaction.audit', 'Audit Transaction', 'Audit waste transactions', 'transaction'),
    ('user.create', 'Create User', 'Create new users', 'user_management'),
    ('user.view', 'View User', 'View users', 'user_management'),
    ('user.edit', 'Edit User', 'Edit users', 'user_management'),
    ('user.delete', 'Delete User', 'Delete users', 'user_management'),
    ('permission.grant', 'Grant Permission', 'Grant permissions to users', 'user_management'),
    ('report.view', 'View Report', 'View reports', 'reporting'),
    ('report.create', 'Create Report', 'Create reports', 'reporting'),
    ('log.view', 'View Log', 'View system logs', 'system')
ON CONFLICT (code) DO NOTHING;