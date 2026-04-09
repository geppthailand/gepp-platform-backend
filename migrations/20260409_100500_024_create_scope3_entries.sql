-- Scope 3 Emission Entries
-- Detailed calculation records per GHG Protocol category with multiple methods

CREATE TABLE IF NOT EXISTS esg_scope3_entries (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    category_number INT NOT NULL,
    supplier_id BIGINT REFERENCES esg_suppliers(id),
    data_entry_id BIGINT REFERENCES esg_data_entries(id),
    reporting_year INT NOT NULL,
    reporting_month INT,
    calculation_method VARCHAR(30) NOT NULL,
    activity_data NUMERIC(18, 4),
    activity_unit VARCHAR(50),
    emission_factor_value NUMERIC(18, 8),
    emission_factor_source VARCHAR(200),
    calculated_tco2e NUMERIC(18, 6) NOT NULL,
    spend_amount NUMERIC(18, 2),
    spend_currency VARCHAR(10) DEFAULT 'THB',
    data_quality_indicator VARCHAR(20) NOT NULL DEFAULT 'estimated',
    notes TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_scope3_method CHECK (calculation_method IN ('spend_based', 'supplier_specific', 'average_data', 'hybrid')),
    CONSTRAINT chk_scope3_quality CHECK (data_quality_indicator IN ('primary', 'secondary', 'estimated', 'default')),
    CONSTRAINT chk_scope3_category CHECK (category_number BETWEEN 1 AND 15),
    CONSTRAINT chk_scope3_month CHECK (reporting_month IS NULL OR reporting_month BETWEEN 1 AND 12)
);

CREATE INDEX IF NOT EXISTS idx_esg_scope3_org_year
    ON esg_scope3_entries (organization_id, reporting_year)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_scope3_org_category
    ON esg_scope3_entries (organization_id, category_number)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_scope3_supplier
    ON esg_scope3_entries (supplier_id)
    WHERE is_active = TRUE AND supplier_id IS NOT NULL;

COMMENT ON TABLE esg_scope3_entries IS 'Detailed Scope 3 emission entries per GHG Protocol category with calculation method tracking';
