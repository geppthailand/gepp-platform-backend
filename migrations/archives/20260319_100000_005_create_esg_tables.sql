-- Migration: 005 - Create ESG Tables
-- Date: 2026-03-19
-- Description: Creates tables for ESG (Environment, Social, Governance) platform
--   - esg_organization_settings: ESG config per organization
--   - esg_emission_factors: Reference emission factors (TGO, IPCC, EPA)
--   - esg_documents: Generic ESG document store (all categories)
--   - esg_waste_records: Classified waste data with CO2e calculations
--   - esg_scope3_summaries: Pre-calculated monthly/yearly summaries
--   - esg_line_messages: LINE message tracking

-- ============================================================
-- 1. ESG Organization Settings
-- ============================================================
CREATE TABLE IF NOT EXISTS esg_organization_settings (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- ESG Configuration
    reporting_year INT NOT NULL DEFAULT 2026,
    methodology VARCHAR(50) NOT NULL DEFAULT 'ghg_protocol',  -- ghg_protocol, tgo_cfo, iso_14064
    organizational_boundary VARCHAR(50) NOT NULL DEFAULT 'operational_control',  -- operational_control, financial_control, equity_share
    base_year INT,
    reduction_target_percent DECIMAL(5,2),
    reduction_target_year INT,

    -- LINE Integration
    line_channel_id VARCHAR(255),
    line_channel_secret VARCHAR(255),
    line_channel_token TEXT,
    line_webhook_url VARCHAR(500),
    line_rich_menu_id VARCHAR(255),

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_esg_settings_org UNIQUE (organization_id)
);

CREATE INDEX IF NOT EXISTS idx_esg_settings_org ON esg_organization_settings(organization_id);

-- ============================================================
-- 2. ESG Emission Factors
-- ============================================================
CREATE TABLE IF NOT EXISTS esg_emission_factors (
    id BIGSERIAL PRIMARY KEY,

    -- Classification
    waste_type VARCHAR(100) NOT NULL,          -- e.g. general, organic, plastic, paper, glass, metal, electronic, hazardous
    waste_category VARCHAR(100),               -- e.g. municipal_solid, industrial, construction
    treatment_method VARCHAR(100) NOT NULL,    -- e.g. landfill, incineration, recycling, composting, anaerobic_digestion

    -- Emission Factor
    factor_value DECIMAL(10,6) NOT NULL,       -- kgCO2e per kg of waste
    factor_unit VARCHAR(50) NOT NULL DEFAULT 'kgCO2e/kg',

    -- Source & Validity
    source VARCHAR(100) NOT NULL DEFAULT 'TGO',  -- TGO, IPCC, EPA, DEFRA
    source_version VARCHAR(50),                   -- e.g. AR6, 2024
    country_code VARCHAR(5) DEFAULT 'TH',
    valid_from DATE,
    valid_to DATE,

    -- Metadata
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_emission_factor UNIQUE (waste_type, treatment_method, source, country_code)
);

CREATE INDEX IF NOT EXISTS idx_emission_factors_type ON esg_emission_factors(waste_type, treatment_method);
CREATE INDEX IF NOT EXISTS idx_emission_factors_source ON esg_emission_factors(source);

-- ============================================================
-- 3. ESG Documents (Generic - supports all ESG categories)
-- ============================================================
CREATE TABLE IF NOT EXISTS esg_documents (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Document Info
    file_name VARCHAR(500) NOT NULL,
    file_url TEXT NOT NULL,
    file_type VARCHAR(50),                     -- image/jpeg, application/pdf, etc.
    file_size_bytes BIGINT,

    -- ESG Classification
    esg_category VARCHAR(20),                  -- environment, social, governance
    esg_subcategory VARCHAR(100),              -- scope3_waste, energy, water, labor_practices, anti_corruption, board_diversity, etc.
    document_type VARCHAR(100),                -- waste_manifest, weighbridge_ticket, invoice, certificate, policy, report, audit_report, other
    document_date DATE,
    reporting_year INT,

    -- Source
    source VARCHAR(20) NOT NULL DEFAULT 'upload',  -- upload, line, api
    uploaded_by_id BIGINT,
    line_message_id VARCHAR(255),
    line_user_id VARCHAR(255),

    -- AI Classification
    ai_classification_status VARCHAR(30) DEFAULT 'pending',  -- pending, processing, completed, failed
    ai_classification_result JSONB,            -- Full AI response
    ai_confidence DECIMAL(5,4),                -- 0.0000 to 1.0000
    ai_classified_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    vendor_name VARCHAR(255),
    summary TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    notes TEXT,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_esg_docs_org ON esg_documents(organization_id);
CREATE INDEX IF NOT EXISTS idx_esg_docs_category ON esg_documents(esg_category);
CREATE INDEX IF NOT EXISTS idx_esg_docs_subcategory ON esg_documents(esg_subcategory);
CREATE INDEX IF NOT EXISTS idx_esg_docs_status ON esg_documents(ai_classification_status);
CREATE INDEX IF NOT EXISTS idx_esg_docs_source ON esg_documents(source);
CREATE INDEX IF NOT EXISTS idx_esg_docs_date ON esg_documents(document_date);
CREATE INDEX IF NOT EXISTS idx_esg_docs_reporting_year ON esg_documents(reporting_year);

-- ============================================================
-- 4. ESG Waste Records
-- ============================================================
CREATE TABLE IF NOT EXISTS esg_waste_records (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_id BIGINT REFERENCES esg_documents(id) ON DELETE SET NULL,

    -- Waste Data
    record_date DATE NOT NULL,
    waste_type VARCHAR(100) NOT NULL,          -- general, organic, plastic, paper, glass, metal, electronic, hazardous
    waste_category VARCHAR(100),               -- municipal_solid, industrial, construction
    treatment_method VARCHAR(100) NOT NULL,    -- landfill, incineration, recycling, composting
    weight_kg DECIMAL(12,4) NOT NULL,

    -- GHG Calculation
    emission_factor_id BIGINT REFERENCES esg_emission_factors(id) ON DELETE SET NULL,
    emission_factor_value DECIMAL(10,6),       -- Snapshot of factor at time of calculation
    co2e_kg DECIMAL(12,4),                     -- weight_kg * emission_factor_value

    -- Quality & Verification
    data_quality VARCHAR(20) NOT NULL DEFAULT 'estimated',  -- measured, estimated, calculated
    verification_status VARCHAR(20) NOT NULL DEFAULT 'unverified',  -- unverified, verified, rejected
    verified_by_id BIGINT,
    verified_at TIMESTAMP WITH TIME ZONE,

    -- Source & Location
    source VARCHAR(20) NOT NULL DEFAULT 'manual',  -- manual, ai, line, import
    origin_location_id BIGINT,                -- FK to user_locations
    vendor_name VARCHAR(255),

    -- Additional
    cost DECIMAL(12,2),
    currency VARCHAR(10) DEFAULT 'THB',
    notes TEXT,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id BIGINT,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_waste_records_org ON esg_waste_records(organization_id);
CREATE INDEX IF NOT EXISTS idx_waste_records_date ON esg_waste_records(record_date);
CREATE INDEX IF NOT EXISTS idx_waste_records_type ON esg_waste_records(waste_type);
CREATE INDEX IF NOT EXISTS idx_waste_records_treatment ON esg_waste_records(treatment_method);
CREATE INDEX IF NOT EXISTS idx_waste_records_doc ON esg_waste_records(document_id);
CREATE INDEX IF NOT EXISTS idx_waste_records_verification ON esg_waste_records(verification_status);

-- ============================================================
-- 5. ESG Scope 3 Summaries (Pre-calculated)
-- ============================================================
CREATE TABLE IF NOT EXISTS esg_scope3_summaries (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Period
    period_type VARCHAR(10) NOT NULL,          -- monthly, yearly
    period_year INT NOT NULL,
    period_month INT,                          -- NULL for yearly summaries

    -- Aggregated Data
    total_waste_kg DECIMAL(14,4) NOT NULL DEFAULT 0,
    total_co2e_kg DECIMAL(14,4) NOT NULL DEFAULT 0,
    total_records INT NOT NULL DEFAULT 0,

    -- Breakdown (JSONB for flexibility)
    by_waste_type JSONB DEFAULT '{}'::jsonb,       -- {general: {kg: 100, co2e: 58}, ...}
    by_treatment JSONB DEFAULT '{}'::jsonb,         -- {landfill: {kg: 80, co2e: 46.4}, ...}
    by_location JSONB DEFAULT '{}'::jsonb,          -- {location_id: {kg: 50, co2e: 29}, ...}

    -- Quality Metrics
    verified_percent DECIMAL(5,2) DEFAULT 0,
    measured_percent DECIMAL(5,2) DEFAULT 0,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_scope3_summary UNIQUE (organization_id, period_type, period_year, period_month)
);

CREATE INDEX IF NOT EXISTS idx_scope3_summary_org ON esg_scope3_summaries(organization_id);
CREATE INDEX IF NOT EXISTS idx_scope3_summary_period ON esg_scope3_summaries(period_year, period_month);

-- ============================================================
-- 6. ESG LINE Messages
-- ============================================================
CREATE TABLE IF NOT EXISTS esg_line_messages (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- LINE Message Info
    line_message_id VARCHAR(255) NOT NULL,
    line_user_id VARCHAR(255) NOT NULL,
    line_reply_token VARCHAR(255),
    message_type VARCHAR(50) NOT NULL,         -- image, text, file

    -- Processing
    processing_status VARCHAR(30) NOT NULL DEFAULT 'received',  -- received, downloading, processing, completed, failed
    document_id BIGINT REFERENCES esg_documents(id) ON DELETE SET NULL,
    error_message TEXT,

    -- Reply
    reply_sent BOOLEAN DEFAULT FALSE,
    reply_message TEXT,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_line_messages_org ON esg_line_messages(organization_id);
CREATE INDEX IF NOT EXISTS idx_line_messages_line_id ON esg_line_messages(line_message_id);
CREATE INDEX IF NOT EXISTS idx_line_messages_user ON esg_line_messages(line_user_id);
CREATE INDEX IF NOT EXISTS idx_line_messages_status ON esg_line_messages(processing_status);
