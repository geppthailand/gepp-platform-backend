-- Migration: User Management System
-- Date: 2025-01-09 12:05:00
-- Description: Creates user management tables including roles, locations, and authentication

-- User Roles
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    permissions JSONB,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- User Business Roles
CREATE TABLE IF NOT EXISTS user_business_roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    permissions JSONB,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- User Locations (Main user entity)
CREATE TABLE IF NOT EXISTS user_locations (
    id BIGSERIAL PRIMARY KEY,
    
    -- User flags
    is_user BOOLEAN NOT NULL DEFAULT FALSE,
    is_location BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Basic Info
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    display_name VARCHAR(255),
    
    -- Authentication
    email VARCHAR(255),
    is_email_active BOOLEAN NOT NULL DEFAULT FALSE,
    email_notification VARCHAR(255),
    phone VARCHAR(255),
    username VARCHAR(255),
    password VARCHAR(255),
    facebook_id VARCHAR(255),
    apple_id VARCHAR(255),
    google_id_gmail VARCHAR(255),
    
    -- Platform and roles
    platform platform_enum NOT NULL DEFAULT 'NA',
    role_id BIGINT REFERENCES user_roles(id),
    business_role_id BIGINT REFERENCES user_business_roles(id),
    
    -- Location data (PostGIS would be better but not available)
    coordinate TEXT, -- Store as "lat,lng" string
    address TEXT,
    postal_code VARCHAR(10),
    country_id BIGINT NOT NULL DEFAULT 212 REFERENCES location_countries(id),
    province_id BIGINT REFERENCES location_provinces(id),
    district_id BIGINT REFERENCES location_districts(id),
    subdistrict_id BIGINT REFERENCES location_subdistricts(id),
    
    -- Business information
    business_type TEXT,
    business_industry TEXT,
    business_sub_industry TEXT,
    company_name TEXT,
    company_phone TEXT,
    company_email VARCHAR(255),
    tax_id TEXT,
    
    -- Waste management fields
    functions TEXT,
    type TEXT,
    population TEXT,
    material TEXT,
    
    -- Profile and documents
    profile_image_url TEXT,
    national_id TEXT,
    national_card_image TEXT,
    business_registration_certificate TEXT,
    
    -- Relationships
    organization_id BIGINT,
    parent_location_id BIGINT REFERENCES user_locations(id),
    created_by_id BIGINT REFERENCES user_locations(id),
    auditor_id BIGINT REFERENCES user_locations(id),
    
    -- Organizational hierarchy
    parent_user_id BIGINT REFERENCES user_locations(id),
    organization_level INTEGER DEFAULT 0,
    organization_path TEXT,
    sub_users JSONB,
    
    -- Localization
    locale VARCHAR(15) DEFAULT 'TH',
    nationality_id BIGINT REFERENCES nationalities(id),
    currency_id BIGINT NOT NULL DEFAULT 12 REFERENCES currencies(id),
    phone_code_id BIGINT REFERENCES phone_number_country_codes(id),
    
    -- Additional fields
    note TEXT,
    expired_date TIMESTAMP WITH TIME ZONE,
    footprint DECIMAL(10, 2),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- User Sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    session_token VARCHAR(255) NOT NULL,
    device_info TEXT,
    ip_address INET,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- User Input Channels (for tracking user interaction channels)
CREATE TABLE IF NOT EXISTS user_input_channels (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    channel VARCHAR(50), -- 'web', 'mobile', 'api', etc.
    device_id VARCHAR(255),
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- User Analytics
CREATE TABLE IF NOT EXISTS user_analytics (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    event_type VARCHAR(100),
    event_data JSONB,
    session_id BIGINT REFERENCES user_sessions(id),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- User subusers association table (many-to-many)
CREATE TABLE IF NOT EXISTS user_subusers (
    parent_user_id BIGINT REFERENCES user_locations(id) ON DELETE CASCADE,
    subuser_id BIGINT REFERENCES user_locations(id) ON DELETE CASCADE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (parent_user_id, subuser_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_locations_email ON user_locations(email);
CREATE INDEX IF NOT EXISTS idx_user_locations_username ON user_locations(username);
CREATE INDEX IF NOT EXISTS idx_user_locations_organization ON user_locations(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_parent_user ON user_locations(parent_user_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_role ON user_locations(role_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_business_role ON user_locations(business_role_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_country ON user_locations(country_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_province ON user_locations(province_id);
CREATE INDEX IF NOT EXISTS idx_user_locations_active_users ON user_locations(is_user, is_active);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_user_analytics_user ON user_analytics(user_id);
CREATE INDEX IF NOT EXISTS idx_user_analytics_event_type ON user_analytics(event_type);
CREATE INDEX IF NOT EXISTS idx_user_analytics_created ON user_analytics(created_date);

-- Create triggers for updated_date columns
CREATE TRIGGER update_user_roles_updated_date BEFORE UPDATE ON user_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_user_business_roles_updated_date BEFORE UPDATE ON user_business_roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_user_locations_updated_date BEFORE UPDATE ON user_locations
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_user_sessions_updated_date BEFORE UPDATE ON user_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_user_input_channels_updated_date BEFORE UPDATE ON user_input_channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Insert default user roles
INSERT INTO user_roles (name, description) VALUES
    ('admin', 'System Administrator'),
    ('user', 'Regular User'),
    ('operator', 'System Operator'),
    ('viewer', 'Read-only User')
ON CONFLICT DO NOTHING;

INSERT INTO user_business_roles (name, description) VALUES
    ('owner', 'Business Owner'),
    ('manager', 'Business Manager'),
    ('employee', 'Business Employee'),
    ('contractor', 'External Contractor')
ON CONFLICT DO NOTHING;