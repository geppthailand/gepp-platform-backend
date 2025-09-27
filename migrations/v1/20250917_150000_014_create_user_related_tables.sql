-- Migration: Create user-related tables (preferences, invitations, banks, etc.)
-- Date: 2025-09-17
-- Description: Create missing user-related tables that are referenced in models but missing from database

-- Note: Using VARCHAR for enum columns to avoid enum type conflicts
-- SQLAlchemy will handle enum validation at the application level

-- Create user_preferences table
CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_location_id BIGINT NOT NULL,

    -- Notification preferences
    email_notifications BOOLEAN DEFAULT TRUE,
    push_notifications BOOLEAN DEFAULT TRUE,
    sms_notifications BOOLEAN DEFAULT FALSE,

    -- Display preferences
    language VARCHAR(10) DEFAULT 'th',
    timezone VARCHAR(50) DEFAULT 'Asia/Bangkok',
    theme VARCHAR(20) DEFAULT 'light',
    currency VARCHAR(10) DEFAULT 'THB',

    -- Feature preferences
    show_tutorials BOOLEAN DEFAULT TRUE,
    compact_view BOOLEAN DEFAULT FALSE,
    auto_save BOOLEAN DEFAULT TRUE,

    -- Privacy preferences
    profile_visibility VARCHAR(20) DEFAULT 'organization',
    share_analytics BOOLEAN DEFAULT TRUE,

    -- Custom preferences (JSONB for flexible storage)
    custom_settings JSONB,

    -- Base model fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,

    -- Foreign key constraint
    CONSTRAINT user_preferences_user_location_id_fkey
        FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE
);

-- Create user_invitations table
CREATE TABLE IF NOT EXISTS user_invitations (
    id BIGSERIAL PRIMARY KEY,

    -- Invitation details
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    invited_by_id BIGINT NOT NULL,
    organization_id BIGINT NOT NULL,

    -- Intended user setup
    intended_role VARCHAR(50), -- Maps to UserRoleEnum at application level
    intended_organization_role BIGINT,
    intended_platform VARCHAR(50), -- Maps to PlatformEnum at application level

    -- Invitation status
    status VARCHAR(50) DEFAULT 'pending',
    invitation_token VARCHAR(255) UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,

    -- User creation result
    created_user_id BIGINT,

    -- Additional data
    custom_message TEXT,
    invitation_data JSONB,

    -- Base model fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,

    -- Foreign key constraints
    CONSTRAINT user_invitations_invited_by_id_fkey
        FOREIGN KEY (invited_by_id) REFERENCES user_locations(id),
    CONSTRAINT user_invitations_organization_id_fkey
        FOREIGN KEY (organization_id) REFERENCES organizations(id),
    CONSTRAINT user_invitations_created_user_id_fkey
        FOREIGN KEY (created_user_id) REFERENCES user_locations(id),
    CONSTRAINT user_invitations_intended_organization_role_fkey
        FOREIGN KEY (intended_organization_role) REFERENCES organization_roles(id)
);

-- Create user_bank table (singular to match model)
CREATE TABLE IF NOT EXISTS user_bank (
    id BIGSERIAL PRIMARY KEY,
    user_location_id BIGINT NOT NULL,
    organization_id BIGINT NOT NULL,
    bank_id BIGINT,

    -- Enhanced bank details
    account_number VARCHAR(50),
    account_name VARCHAR(255),
    account_type VARCHAR(50), -- savings, checking, etc.

    -- Branch information
    branch_name VARCHAR(255),
    branch_code VARCHAR(20),

    -- Status and verification
    is_verified BOOLEAN DEFAULT FALSE,
    verification_date TIMESTAMP,
    is_primary BOOLEAN DEFAULT FALSE,

    -- Additional info
    note TEXT,

    -- Base model fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,

    -- Foreign key constraints
    CONSTRAINT user_bank_user_location_id_fkey
        FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE,
    CONSTRAINT user_bank_organization_id_fkey
        FOREIGN KEY (organization_id) REFERENCES organizations(id),
    CONSTRAINT user_bank_bank_id_fkey
        FOREIGN KEY (bank_id) REFERENCES banks(id)
);

-- Create user_subscriptions table
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_location_id BIGINT NOT NULL,
    organization_id BIGINT NOT NULL,
    subscription_package_id BIGINT, -- Made nullable since subscription_packages table doesn't exist yet

    -- Subscription details
    start_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR(50) DEFAULT 'active', -- active, suspended, expired, cancelled

    -- Billing
    billing_cycle VARCHAR(20), -- monthly, yearly
    next_billing_date DATE,
    auto_renew BOOLEAN DEFAULT TRUE,

    -- Usage tracking
    usage_data JSONB, -- Track usage against subscription limits

    -- Base model fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,

    -- Foreign key constraints
    CONSTRAINT user_subscriptions_user_location_id_fkey
        FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE,
    CONSTRAINT user_subscriptions_organization_id_fkey
        FOREIGN KEY (organization_id) REFERENCES organizations(id)
    -- Note: subscription_packages foreign key constraint will be added when that table is created
);

-- Create user_activities table
CREATE TABLE IF NOT EXISTS user_activities (
    id BIGSERIAL PRIMARY KEY,
    user_location_id BIGINT NOT NULL,
    actor_id BIGINT,

    -- Activity details
    activity_type VARCHAR(100) NOT NULL, -- login, logout, create_user, etc.
    resource VARCHAR(100), -- What was affected
    action VARCHAR(100), -- What action was taken

    -- Activity data
    details JSONB, -- Additional activity details
    ip_address VARCHAR(45),
    user_agent TEXT,

    -- Context
    organization_id BIGINT,
    session_id VARCHAR(255),

    -- Base model fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,

    -- Foreign key constraints
    CONSTRAINT user_activities_user_location_id_fkey
        FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE,
    CONSTRAINT user_activities_actor_id_fkey
        FOREIGN KEY (actor_id) REFERENCES user_locations(id)
);

-- Create user_devices table
CREATE TABLE IF NOT EXISTS user_devices (
    id BIGSERIAL PRIMARY KEY,
    user_location_id BIGINT NOT NULL,

    -- Device identification
    device_id VARCHAR(255) NOT NULL, -- Unique device identifier
    device_name VARCHAR(255),
    device_type VARCHAR(50), -- mobile, tablet, desktop
    platform VARCHAR(50), -- ios, android, web, windows, mac

    -- Device details
    browser VARCHAR(100),
    browser_version VARCHAR(50),
    os_version VARCHAR(50),
    app_version VARCHAR(50),

    -- Security
    is_trusted BOOLEAN DEFAULT FALSE,
    push_token TEXT, -- For push notifications

    -- Activity
    last_active TIMESTAMP,
    first_seen TIMESTAMP,

    -- Base model fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,

    -- Foreign key constraint
    CONSTRAINT user_devices_user_location_id_fkey
        FOREIGN KEY (user_location_id) REFERENCES user_locations(id) ON DELETE CASCADE,

    -- Unique constraint on user + device
    CONSTRAINT user_devices_user_device_unique
        UNIQUE (user_location_id, device_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_location_id ON user_preferences(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_invitations_email ON user_invitations(email);
CREATE INDEX IF NOT EXISTS idx_user_invitations_token ON user_invitations(invitation_token);
CREATE INDEX IF NOT EXISTS idx_user_invitations_organization_id ON user_invitations(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_bank_user_location_id ON user_bank(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_location_id ON user_subscriptions(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_activities_user_location_id ON user_activities(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_devices_user_location_id ON user_devices(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_devices_device_id ON user_devices(device_id);

-- Comments
COMMENT ON TABLE user_preferences IS 'User preferences and settings for personalization';
COMMENT ON TABLE user_invitations IS 'Track user invitations and their acceptance status';
COMMENT ON TABLE user_bank IS 'User banking information for payments and transfers';
COMMENT ON TABLE user_subscriptions IS 'User subscription information and billing details';
COMMENT ON TABLE user_activities IS 'Track user activity and engagement metrics';
COMMENT ON TABLE user_devices IS 'Track user devices and login sessions';