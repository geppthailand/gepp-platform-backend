-- Migration: GRI, Rewards, and Knowledge Management
-- Date: 2025-01-09 12:30:00
-- Description: Creates GRI reporting, rewards system, and knowledge management tables

-- GRI Standards
CREATE TABLE IF NOT EXISTS gri_standards (
    id BIGSERIAL PRIMARY KEY,
    
    standard_code VARCHAR(20) UNIQUE NOT NULL, -- e.g., 'GRI-301', 'GRI-302'
    standard_name VARCHAR(255),
    category VARCHAR(100), -- 'environmental', 'social', 'economic'
    
    description TEXT,
    requirements TEXT,
    guidance TEXT,
    
    version VARCHAR(20),
    effective_date DATE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- GRI Indicators
CREATE TABLE IF NOT EXISTS gri_indicators (
    id BIGSERIAL PRIMARY KEY,
    
    standard_id BIGINT NOT NULL REFERENCES gri_standards(id),
    indicator_code VARCHAR(20) NOT NULL, -- e.g., '301-1', '302-1'
    indicator_name VARCHAR(255),
    
    description TEXT,
    measurement_unit VARCHAR(50),
    calculation_method TEXT,
    
    is_mandatory BOOLEAN DEFAULT FALSE,
    reporting_frequency VARCHAR(50), -- 'monthly', 'quarterly', 'annually'
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    UNIQUE(standard_id, indicator_code)
);

-- GRI Reports
CREATE TABLE IF NOT EXISTS gri_reports (
    id BIGSERIAL PRIMARY KEY,
    
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    report_title VARCHAR(255),
    reporting_period VARCHAR(50),
    reporting_year INTEGER,
    
    report_type VARCHAR(50), -- 'sustainability', 'integrated', 'annual'
    gri_version VARCHAR(20), -- e.g., 'GRI Standards 2021'
    
    -- Report status
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'in_review', 'published', 'archived'
    
    -- Key metrics summary
    total_energy_consumption DECIMAL(15, 3), -- GJ
    total_water_consumption DECIMAL(15, 3), -- cubic meters
    total_waste_generated DECIMAL(15, 3), -- tonnes
    total_emissions DECIMAL(15, 3), -- tonnes CO2 equivalent
    
    -- Report content
    executive_summary TEXT,
    methodology TEXT,
    data_collection_approach TEXT,
    
    -- Assurance
    external_assurance BOOLEAN DEFAULT FALSE,
    assurance_provider VARCHAR(255),
    assurance_level VARCHAR(50), -- 'limited', 'reasonable'
    
    -- Publication
    published_date DATE,
    report_url TEXT,
    
    prepared_by_id BIGINT REFERENCES user_locations(id),
    approved_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- GRI Report Data
CREATE TABLE IF NOT EXISTS gri_report_data (
    id BIGSERIAL PRIMARY KEY,
    
    report_id BIGINT NOT NULL REFERENCES gri_reports(id) ON DELETE CASCADE,
    indicator_id BIGINT NOT NULL REFERENCES gri_indicators(id),
    
    -- Data values
    quantitative_value DECIMAL(15, 6),
    qualitative_value TEXT,
    unit VARCHAR(50),
    
    -- Data context
    scope VARCHAR(100), -- 'company-wide', 'facility-specific', 'product-specific'
    boundary TEXT,
    methodology TEXT,
    assumptions TEXT,
    
    -- Data quality
    data_source VARCHAR(255),
    collection_method VARCHAR(100),
    verification_status VARCHAR(50), -- 'unverified', 'internally_verified', 'externally_verified'
    
    -- Time period
    measurement_date DATE,
    period_start DATE,
    period_end DATE,
    
    -- Supporting information
    notes TEXT,
    supporting_documents JSONB,
    
    entered_by_id BIGINT REFERENCES user_locations(id),
    verified_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Rewards Catalog
CREATE TABLE IF NOT EXISTS rewards_catalog (
    id BIGSERIAL PRIMARY KEY,
    
    reward_name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100), -- 'discount', 'product', 'service', 'experience'
    
    -- Point requirements
    points_required INTEGER NOT NULL,
    points_type VARCHAR(50) DEFAULT 'general', -- 'general', 'environmental', 'social'
    
    -- Reward details
    reward_value DECIMAL(10, 2),
    currency_id BIGINT REFERENCES currencies(id) DEFAULT 12,
    
    -- Availability
    quantity_available INTEGER,
    quantity_redeemed INTEGER DEFAULT 0,
    is_limited_quantity BOOLEAN DEFAULT FALSE,
    
    -- Validity
    valid_from DATE,
    valid_until DATE,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Terms and conditions
    terms_and_conditions TEXT,
    redemption_instructions TEXT,
    
    -- Media
    image_url TEXT,
    additional_images JSONB,
    
    -- Provider information
    provider_organization_id BIGINT REFERENCES organizations(id),
    provider_contact_info JSONB,
    
    created_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User Point Balances
CREATE TABLE IF NOT EXISTS user_point_balances (
    id BIGSERIAL PRIMARY KEY,
    
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    
    points_type VARCHAR(50) DEFAULT 'general',
    current_balance INTEGER DEFAULT 0,
    lifetime_earned INTEGER DEFAULT 0,
    lifetime_redeemed INTEGER DEFAULT 0,
    
    -- Balance details
    pending_points INTEGER DEFAULT 0,
    expired_points INTEGER DEFAULT 0,
    
    last_activity_date TIMESTAMP WITH TIME ZONE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    UNIQUE(user_id, points_type)
);

-- Point Transactions
CREATE TABLE IF NOT EXISTS point_transactions (
    id BIGSERIAL PRIMARY KEY,
    
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    
    transaction_type VARCHAR(50), -- 'earned', 'redeemed', 'expired', 'adjusted'
    points_type VARCHAR(50) DEFAULT 'general',
    
    points_amount INTEGER, -- positive for earned, negative for redeemed
    balance_before INTEGER,
    balance_after INTEGER,
    
    -- Transaction details
    source_type VARCHAR(50), -- 'waste_collection', 'recycling', 'survey', 'referral', 'manual'
    source_reference_id BIGINT, -- ID of the source transaction/activity
    
    description TEXT,
    notes TEXT,
    
    -- Expiration (for earned points)
    expires_at TIMESTAMP WITH TIME ZONE,
    
    -- Processing
    processed_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Reward Redemptions
CREATE TABLE IF NOT EXISTS reward_redemptions (
    id BIGSERIAL PRIMARY KEY,
    
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    reward_id BIGINT NOT NULL REFERENCES rewards_catalog(id),
    
    points_redeemed INTEGER,
    redemption_code VARCHAR(100) UNIQUE,
    
    -- Redemption status
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'confirmed', 'fulfilled', 'cancelled', 'expired'
    
    -- Fulfillment details
    delivery_method VARCHAR(50), -- 'digital', 'pickup', 'shipping'
    delivery_address TEXT,
    delivery_instructions TEXT,
    
    fulfillment_date DATE,
    tracking_number VARCHAR(100),
    
    -- Dates
    redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    
    notes TEXT,
    
    processed_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Knowledge Management Files
CREATE TABLE IF NOT EXISTS km_files (
    id BIGSERIAL PRIMARY KEY,
    
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255),
    file_path TEXT,
    file_size INTEGER, -- bytes
    file_type VARCHAR(100), -- MIME type
    
    -- Content classification
    category VARCHAR(100), -- 'regulation', 'procedure', 'guideline', 'research', 'template'
    tags JSONB, -- Array of tags
    language VARCHAR(10) DEFAULT 'en',
    
    -- Content metadata
    title VARCHAR(500),
    description TEXT,
    summary TEXT,
    
    -- Access control
    access_level VARCHAR(50) DEFAULT 'public', -- 'public', 'internal', 'restricted'
    organization_id BIGINT REFERENCES organizations(id), -- NULL for public files
    
    -- Version control
    version VARCHAR(20) DEFAULT '1.0',
    parent_file_id BIGINT REFERENCES km_files(id),
    is_latest_version BOOLEAN DEFAULT TRUE,
    
    -- Processing status
    processing_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'processed', 'failed'
    extraction_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'completed', 'failed'
    
    -- Content extraction
    extracted_text TEXT,
    content_hash VARCHAR(64),
    
    uploaded_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Knowledge Chunks (for vector search)
CREATE TABLE IF NOT EXISTS km_chunks (
    id BIGSERIAL PRIMARY KEY,
    
    file_id BIGINT NOT NULL REFERENCES km_files(id) ON DELETE CASCADE,
    
    chunk_index INTEGER,
    chunk_text TEXT NOT NULL,
    chunk_size INTEGER, -- character count
    
    -- Vector embedding (when vector extension is available)
    -- embedding VECTOR(1536), -- OpenAI ada-002 dimensions
    
    -- Alternative: store as JSON array for compatibility
    embedding_json JSONB,
    
    -- Chunk metadata
    page_number INTEGER,
    section_title VARCHAR(500),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Experts
CREATE TABLE IF NOT EXISTS experts (
    id BIGSERIAL PRIMARY KEY,
    
    name VARCHAR(255) NOT NULL,
    title VARCHAR(255),
    organization VARCHAR(255),
    
    -- Contact information
    email VARCHAR(255),
    phone VARCHAR(50),
    website TEXT,
    
    -- Expertise
    expertise_areas JSONB, -- Array of expertise areas
    specializations JSONB, -- Array of specializations
    languages JSONB, -- Array of languages spoken
    
    -- Professional info
    years_experience INTEGER,
    education TEXT,
    certifications JSONB,
    publications JSONB,
    
    -- Profile
    bio TEXT,
    profile_image_url TEXT,
    
    -- Availability
    availability_status VARCHAR(50) DEFAULT 'available', -- 'available', 'busy', 'unavailable'
    hourly_rate DECIMAL(10, 2),
    currency_id BIGINT REFERENCES currencies(id) DEFAULT 12,
    
    -- Rating and reviews
    average_rating DECIMAL(3, 2), -- 0-5.00
    total_reviews INTEGER DEFAULT 0,
    
    created_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_gri_indicators_standard ON gri_indicators(standard_id);
CREATE INDEX IF NOT EXISTS idx_gri_reports_organization ON gri_reports(organization_id);
CREATE INDEX IF NOT EXISTS idx_gri_reports_year ON gri_reports(reporting_year);
CREATE INDEX IF NOT EXISTS idx_gri_report_data_report ON gri_report_data(report_id);
CREATE INDEX IF NOT EXISTS idx_gri_report_data_indicator ON gri_report_data(indicator_id);

CREATE INDEX IF NOT EXISTS idx_rewards_catalog_category ON rewards_catalog(category);
CREATE INDEX IF NOT EXISTS idx_rewards_catalog_points ON rewards_catalog(points_required);
CREATE INDEX IF NOT EXISTS idx_rewards_catalog_active ON rewards_catalog(is_active);

CREATE INDEX IF NOT EXISTS idx_user_point_balances_user ON user_point_balances(user_id);
CREATE INDEX IF NOT EXISTS idx_point_transactions_user ON point_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_point_transactions_type ON point_transactions(transaction_type);

CREATE INDEX IF NOT EXISTS idx_reward_redemptions_user ON reward_redemptions(user_id);
CREATE INDEX IF NOT EXISTS idx_reward_redemptions_reward ON reward_redemptions(reward_id);
CREATE INDEX IF NOT EXISTS idx_reward_redemptions_status ON reward_redemptions(status);

CREATE INDEX IF NOT EXISTS idx_km_files_category ON km_files(category);
CREATE INDEX IF NOT EXISTS idx_km_files_access_level ON km_files(access_level);
CREATE INDEX IF NOT EXISTS idx_km_files_organization ON km_files(organization_id);
CREATE INDEX IF NOT EXISTS idx_km_files_latest ON km_files(is_latest_version);

CREATE INDEX IF NOT EXISTS idx_km_chunks_file ON km_chunks(file_id);

CREATE INDEX IF NOT EXISTS idx_experts_expertise ON experts USING GIN(expertise_areas);
CREATE INDEX IF NOT EXISTS idx_experts_status ON experts(availability_status);

-- Create triggers for updated_date columns
CREATE TRIGGER update_gri_standards_updated_date BEFORE UPDATE ON gri_standards
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_gri_indicators_updated_date BEFORE UPDATE ON gri_indicators
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_gri_reports_updated_date BEFORE UPDATE ON gri_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_gri_report_data_updated_date BEFORE UPDATE ON gri_report_data
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_rewards_catalog_updated_date BEFORE UPDATE ON rewards_catalog
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_user_point_balances_updated_date BEFORE UPDATE ON user_point_balances
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_reward_redemptions_updated_date BEFORE UPDATE ON reward_redemptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_km_files_updated_date BEFORE UPDATE ON km_files
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_experts_updated_date BEFORE UPDATE ON experts
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();