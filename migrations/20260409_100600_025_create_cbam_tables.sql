-- EU CBAM (Carbon Border Adjustment Mechanism) Module
-- Product-level embedded emissions tracking and quarterly declaration management

CREATE TABLE IF NOT EXISTS esg_cbam_products (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    cn_code VARCHAR(20) NOT NULL,
    product_name VARCHAR(300) NOT NULL,
    product_name_th VARCHAR(300),
    production_volume NUMERIC(18, 4),
    production_unit VARCHAR(50) DEFAULT 'tonne',
    direct_emissions_tco2e NUMERIC(18, 6) DEFAULT 0,
    indirect_emissions_tco2e NUMERIC(18, 6) DEFAULT 0,
    precursor_emissions_tco2e NUMERIC(18, 6) DEFAULT 0,
    total_embedded_emissions NUMERIC(18, 6) DEFAULT 0,
    specific_embedded_emissions NUMERIC(18, 8) DEFAULT 0,
    default_value_tco2e NUMERIC(18, 6),
    reporting_period_start DATE,
    reporting_period_end DATE,
    installation_id VARCHAR(100),
    verification_status VARCHAR(20) DEFAULT 'unverified',
    metadata JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_cbam_verification CHECK (verification_status IN ('unverified', 'self_declared', 'third_party_verified'))
);

CREATE INDEX IF NOT EXISTS idx_esg_cbam_products_org
    ON esg_cbam_products (organization_id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_cbam_products_cn
    ON esg_cbam_products (cn_code)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_cbam_products IS 'EU CBAM product registry with embedded emissions calculations for border adjustment compliance';


CREATE TABLE IF NOT EXISTS esg_cbam_reports (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    reporting_quarter INT NOT NULL,
    reporting_year INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    report_data JSONB NOT NULL DEFAULT '{}',
    submitted_at TIMESTAMP WITH TIME ZONE,
    export_url VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_cbam_quarter CHECK (reporting_quarter BETWEEN 1 AND 4),
    CONSTRAINT chk_cbam_report_status CHECK (status IN ('draft', 'generated', 'submitted', 'accepted', 'rejected'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_esg_cbam_reports_org_period
    ON esg_cbam_reports (organization_id, reporting_year, reporting_quarter)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_cbam_reports IS 'EU CBAM quarterly declaration reports with status tracking';
