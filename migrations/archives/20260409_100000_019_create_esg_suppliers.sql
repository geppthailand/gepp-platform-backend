-- ESG Supplier Registry
-- Stores supplier profiles for Scope 3 supply chain management

CREATE TABLE IF NOT EXISTS esg_suppliers (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    supplier_name VARCHAR(300) NOT NULL,
    supplier_code VARCHAR(100),
    tax_id VARCHAR(50),
    country VARCHAR(3) NOT NULL DEFAULT 'THA',
    industry_sector VARCHAR(100),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    contact_name VARCHAR(255),
    tier VARCHAR(10) NOT NULL DEFAULT 'tier1',
    data_collection_level VARCHAR(10) NOT NULL DEFAULT '1',
    annual_spend NUMERIC(18, 2),
    spend_currency VARCHAR(10) DEFAULT 'THB',
    primary_scope3_category INT,
    emission_data_source VARCHAR(30) NOT NULL DEFAULT 'default',
    total_reported_tco2e NUMERIC(18, 6) DEFAULT 0,
    data_quality_score NUMERIC(5, 2) DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_supplier_tier CHECK (tier IN ('tier1', 'tier2', 'tier3')),
    CONSTRAINT chk_supplier_data_level CHECK (data_collection_level IN ('1', '2', '3')),
    CONSTRAINT chk_supplier_status CHECK (status IN ('active', 'inactive', 'pending')),
    CONSTRAINT chk_supplier_emission_source CHECK (emission_data_source IN ('default', 'supplier_specific', 'hybrid'))
);

CREATE INDEX IF NOT EXISTS idx_esg_suppliers_org
    ON esg_suppliers (organization_id)
    WHERE is_active = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_esg_suppliers_org_code
    ON esg_suppliers (organization_id, supplier_code)
    WHERE is_active = TRUE AND supplier_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_esg_suppliers_org_status
    ON esg_suppliers (organization_id, status)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_suppliers IS 'Supplier registry for Scope 3 supply chain management and data collection';
