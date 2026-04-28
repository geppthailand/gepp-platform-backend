-- Create esg_data_entries table for LINE Chat + LIFF data submissions
-- Stores both LINE_CHAT (quick capture via OCR/text) and LIFF_MANUAL (web form) entries

CREATE TABLE IF NOT EXISTS esg_data_entries (
    id BIGSERIAL PRIMARY KEY,

    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    user_id BIGINT REFERENCES user_locations(id),
    line_user_id VARCHAR(100),

    -- ESG hierarchy linkage (nullable for LINE_CHAT entries - AI fills later)
    category_id BIGINT REFERENCES esg_data_category(id),
    subcategory_id BIGINT REFERENCES esg_data_subcategory(id),
    datapoint_id BIGINT REFERENCES esg_datapoint(id),
    category VARCHAR(100),

    -- Value
    value NUMERIC(18, 4) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    calculated_tco2e NUMERIC(18, 6),

    -- Dates
    entry_date DATE,
    record_date DATE,

    -- Notes + evidence
    notes TEXT,
    file_key VARCHAR(500),
    file_name VARCHAR(255),
    evidence_image_url VARCHAR(500),

    -- Categorization tag (e.g., 'Scope 1', 'Scope 2', 'Scope 3')
    scope_tag VARCHAR(50),

    -- Source + verification status
    entry_source VARCHAR(20) NOT NULL DEFAULT 'LIFF_MANUAL',
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING_VERIFY',

    -- BaseModel columns
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT esg_data_entries_entry_source_check
        CHECK (entry_source IN ('LINE_CHAT', 'LIFF_MANUAL')),
    CONSTRAINT esg_data_entries_status_check
        CHECK (status IN ('PENDING_VERIFY', 'VERIFIED'))
);

-- Indexes for dashboard + filtering queries
CREATE INDEX IF NOT EXISTS idx_esg_data_entries_organization_id
    ON esg_data_entries (organization_id);

CREATE INDEX IF NOT EXISTS idx_esg_data_entries_user_id
    ON esg_data_entries (user_id)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_esg_data_entries_line_user_id
    ON esg_data_entries (line_user_id)
    WHERE line_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_esg_data_entries_entry_source
    ON esg_data_entries (organization_id, entry_source);

CREATE INDEX IF NOT EXISTS idx_esg_data_entries_status
    ON esg_data_entries (organization_id, status);

CREATE INDEX IF NOT EXISTS idx_esg_data_entries_entry_date
    ON esg_data_entries (organization_id, entry_date DESC);

COMMENT ON TABLE  esg_data_entries IS 'ESG data entries from LINE Chat (OCR/text) or LIFF (manual form)';
COMMENT ON COLUMN esg_data_entries.entry_source IS 'Source of entry: LINE_CHAT or LIFF_MANUAL';
COMMENT ON COLUMN esg_data_entries.calculated_tco2e IS 'Auto-calculated CO2 equivalent in tonnes';
COMMENT ON COLUMN esg_data_entries.status IS 'Verification status: PENDING_VERIFY or VERIFIED';
