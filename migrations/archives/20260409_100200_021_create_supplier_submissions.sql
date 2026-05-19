-- Supplier Data Submissions
-- Tracks data submitted by suppliers through the portal (Tier 1 forms, Tier 2 CSV uploads)

CREATE TABLE IF NOT EXISTS esg_supplier_submissions (
    id BIGSERIAL PRIMARY KEY,
    supplier_id BIGINT NOT NULL REFERENCES esg_suppliers(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    reporting_year INT NOT NULL,
    reporting_period VARCHAR(20) NOT NULL DEFAULT 'annual',
    scope3_category INT,
    submission_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    submitted_at TIMESTAMP WITH TIME ZONE,
    verified_at TIMESTAMP WITH TIME ZONE,
    verified_by_id BIGINT REFERENCES user_locations(id),
    data_tier VARCHAR(10) NOT NULL DEFAULT '1',
    raw_data JSONB NOT NULL DEFAULT '{}',
    calculated_tco2e NUMERIC(18, 6),
    anomaly_flags JSONB NOT NULL DEFAULT '[]',
    file_key VARCHAR(500),
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_submission_status CHECK (submission_status IN ('pending', 'submitted', 'verified', 'rejected', 'overdue')),
    CONSTRAINT chk_submission_tier CHECK (data_tier IN ('1', '2', '3')),
    CONSTRAINT chk_submission_period CHECK (reporting_period IN ('annual', 'Q1', 'Q2', 'Q3', 'Q4', 'monthly'))
);

CREATE INDEX IF NOT EXISTS idx_esg_submissions_supplier
    ON esg_supplier_submissions (supplier_id, reporting_year)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_submissions_org_status
    ON esg_supplier_submissions (organization_id, submission_status)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_submissions_org_year
    ON esg_supplier_submissions (organization_id, reporting_year)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_supplier_submissions IS 'Supplier-submitted emission data with anomaly detection flags and review workflow';
