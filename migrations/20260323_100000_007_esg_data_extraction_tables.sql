-- ============================================================
-- ESG Data Extraction Platform Tables
-- Creates tables for multi-channel platform binding, ESG data
-- hierarchy (categories/subcategories/datapoints), and
-- data extraction records from LINE groups and other channels.
-- ============================================================

-- 1. esg_organization_setup - Extended org ESG config
CREATE TABLE IF NOT EXISTS esg_organization_setup (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- ESG Operational Config
    industry_sector VARCHAR(100),
    employee_count INT,
    revenue_currency VARCHAR(10) DEFAULT 'THB',
    annual_revenue DECIMAL(14,2),
    reporting_framework VARCHAR(50) DEFAULT 'gri',
    fiscal_year_start INT DEFAULT 1,

    -- Data Collection Config
    auto_extract_enabled BOOLEAN DEFAULT TRUE,
    notification_enabled BOOLEAN DEFAULT TRUE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_esg_org_setup UNIQUE (organization_id)
);

CREATE INDEX idx_esg_org_setup_org ON esg_organization_setup(organization_id);

-- 2. esg_external_platform_binding - Multi-channel platform bindings
CREATE TABLE IF NOT EXISTS esg_external_platform_binding (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL CHECK (channel IN ('line','whatsapp','telegram','wechat','email')),

    -- Auth & Config (channel-specific credentials stored as JSONB)
    -- LINE example: {"channel_id":"...", "channel_secret":"...", "channel_token":"...", "bot_user_id":"..."}
    auth_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Authorized groups for this binding
    -- [{"group_id":"C...", "group_name":"ESG-Factory-A", "pairing_code":"ABC123", "status":"paired", "paired_at":"2026-03-23T..."}]
    authorized_groups JSONB DEFAULT '[]'::jsonb,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_platform_binding UNIQUE (organization_id, channel)
);

CREATE INDEX idx_platform_binding_org ON esg_external_platform_binding(organization_id);
CREATE INDEX idx_platform_binding_channel ON esg_external_platform_binding(channel);

-- 3. esg_data_category - Top-level ESG data categories
CREATE TABLE IF NOT EXISTS esg_data_category (
    id BIGSERIAL PRIMARY KEY,
    pillar VARCHAR(1) NOT NULL CHECK (pillar IN ('E','S','G')),
    name VARCHAR(200) NOT NULL,
    name_th VARCHAR(200),
    description TEXT,
    sort_order INT DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_esg_data_category_pillar ON esg_data_category(pillar);

-- 4. esg_data_subcategory - Subcategories within each category
CREATE TABLE IF NOT EXISTS esg_data_subcategory (
    id BIGSERIAL PRIMARY KEY,
    pillar VARCHAR(1) NOT NULL CHECK (pillar IN ('E','S','G')),
    esg_data_category_id BIGINT NOT NULL REFERENCES esg_data_category(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    name_th VARCHAR(200),
    description TEXT,
    sort_order INT DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_esg_data_subcategory_cat ON esg_data_subcategory(esg_data_category_id);
CREATE INDEX idx_esg_data_subcategory_pillar ON esg_data_subcategory(pillar);

-- 5. esg_datapoint - Specific extractable data points
CREATE TABLE IF NOT EXISTS esg_datapoint (
    id BIGSERIAL PRIMARY KEY,
    pillar VARCHAR(1) NOT NULL CHECK (pillar IN ('E','S','G')),
    esg_data_subcategory_id BIGINT NOT NULL REFERENCES esg_data_subcategory(id) ON DELETE CASCADE,
    name VARCHAR(300) NOT NULL,
    name_th VARCHAR(300),
    description TEXT,
    unit VARCHAR(50),
    data_type VARCHAR(20) DEFAULT 'numeric',
    sort_order INT DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_esg_datapoint_subcat ON esg_datapoint(esg_data_subcategory_id);
CREATE INDEX idx_esg_datapoint_pillar ON esg_datapoint(pillar);

-- 6. esg_organization_data_extraction - Extracted data records
CREATE TABLE IF NOT EXISTS esg_organization_data_extraction (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Source channel and type
    channel VARCHAR(20) NOT NULL CHECK (channel IN ('line','whatsapp','telegram','wechat','email','upload','manual')),
    type VARCHAR(10) NOT NULL CHECK (type IN ('none','text','image','pdf','xlsx','docx')),
    file_id BIGINT REFERENCES files(id) ON DELETE SET NULL,

    -- Raw content (for text messages)
    raw_content TEXT,

    -- Source tracking
    source_group_id VARCHAR(255),
    source_group_name VARCHAR(255),
    source_user_id VARCHAR(255),
    source_message_id VARCHAR(255),

    -- LLM Extraction Results
    extractions JSONB DEFAULT '{}'::jsonb,

    -- Datapoint Matches
    -- [{"datapoint_id": 42, "value": 1500, "unit": "kg", "confidence": 0.95}]
    datapoint_matches JSONB DEFAULT '[]'::jsonb,

    -- Reference tracking (vendor, date, location, etc.)
    refs JSONB DEFAULT '{}'::jsonb,

    -- Processing status
    processing_status VARCHAR(30) DEFAULT 'pending',
    error_message TEXT,
    processed_at TIMESTAMP WITH TIME ZONE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_extraction_org ON esg_organization_data_extraction(organization_id);
CREATE INDEX idx_extraction_channel ON esg_organization_data_extraction(channel);
CREATE INDEX idx_extraction_status ON esg_organization_data_extraction(processing_status);
CREATE INDEX idx_extraction_group ON esg_organization_data_extraction(source_group_id);
CREATE INDEX idx_extraction_datapoints ON esg_organization_data_extraction USING GIN (datapoint_matches);

-- 7. Migrate existing LINE credentials from esg_organization_settings to esg_external_platform_binding
INSERT INTO esg_external_platform_binding (organization_id, channel, auth_json)
SELECT
    organization_id,
    'line',
    jsonb_build_object(
        'channel_id', line_channel_id,
        'channel_secret', line_channel_secret,
        'channel_token', line_channel_token,
        'webhook_url', line_webhook_url,
        'rich_menu_id', line_rich_menu_id
    )
FROM esg_organization_settings
WHERE line_channel_id IS NOT NULL
  AND line_channel_id != ''
  AND is_active = TRUE
ON CONFLICT (organization_id, channel) DO NOTHING;
