-- ============================================================
-- esg_records — record-centric extraction storage
-- ============================================================
-- One row = one *atomic GHG-calculatable item* (one trip, one
-- stay, one invoice line). Replaces the prior datapoint-row
-- pattern where a single record was scattered across many
-- esg_data_entries rows, which made traceback / record-modal
-- queries awkward and produced misaligned columns.
--
-- Design goals
--   • One read = one record. The full set of datapoints lives
--     in the `datapoints` JSONB array, each with a stable
--     `datapoint_id` ref into esg_datapoint, plus the value /
--     unit / confidence / tags the LLM actually emitted.
--   • Strict GHG sufficiency. `ghg_status` declares whether
--     the record has enough activity data to compute kgCO2e,
--     and `ghg_missing_fields` lists what's still needed.
--     Currency-only data (e.g. "5,470 THB") is NOT enough on
--     its own — those records are stored with status
--     'insufficient' and surfaced in the analysis card.
--   • Evidence-linked. `extraction_id` FK into
--     esg_organization_data_extraction makes each record
--     traceable back to the source document.
-- ============================================================

CREATE TABLE IF NOT EXISTS esg_records (
    id                  BIGSERIAL PRIMARY KEY,
    organization_id     BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    line_user_id        VARCHAR(64),               -- LIFF / LINE owner of this record
    user_id             BIGINT,                    -- legacy compat with esg_data_entries.user_id

    -- Source document
    extraction_id       BIGINT REFERENCES esg_organization_data_extraction(id) ON DELETE SET NULL,
    evidence_image_url  VARCHAR(500),              -- direct S3 link, denormalised for fast reads
    file_key            VARCHAR(500),

    -- Hierarchy
    category_id         BIGINT REFERENCES esg_data_category(id) ON DELETE SET NULL,
    subcategory_id      BIGINT REFERENCES esg_data_subcategory(id) ON DELETE SET NULL,
    scope3_category_id  INTEGER,                   -- 1..15 for fast Scope-3 filters
    pillar              CHAR(1),                   -- 'E' / 'S' / 'G'

    -- Record identity
    record_label        VARCHAR(255) NOT NULL,     -- "Taxi BKK→Suvarnabhumi", "Flight TG403", …
    entry_date          DATE,

    -- Datapoints — JSONB array of:
    --   {
    --     datapoint_id: int | null,        -- FK into esg_datapoint when matched, null otherwise
    --     datapoint_name: text,            -- LLM's reported field label (always set)
    --     canonical_name: text | null,     -- name from esg_datapoint when matched
    --     value: number | string,
    --     unit: text | null,
    --     confidence: number,
    --     tags: text[],
    --     is_canonical: bool               -- true if datapoint_id matched the category's
    --                                      -- canonical hierarchy at write time
    --   }
    datapoints          JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- GHG
    kgco2e              NUMERIC(20,4),                 -- null when status != 'computed'
    ghg_status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                                                       -- 'computed' | 'insufficient' | 'method_unknown' | 'pending'
    ghg_method          VARCHAR(60),                   -- e.g. 'km*EF', 'nights*hotel_EF', 'kwh*grid_EF'
    ghg_missing_fields  JSONB NOT NULL DEFAULT '[]'::jsonb,  -- ["distance_km", "transport_mode"] etc.
    ghg_reason          TEXT,                          -- human-readable Thai/English explanation

    -- Bookkeeping
    currency            VARCHAR(8),
    status              VARCHAR(30) DEFAULT 'PENDING_VERIFY',
    entry_source        VARCHAR(30) DEFAULT 'LINE_CHAT',
    notes               TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Hot-path indexes for the data-warehouse modal + dashboards
CREATE INDEX IF NOT EXISTS idx_esg_records_org              ON esg_records(organization_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_records_org_scope3       ON esg_records(organization_id, scope3_category_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_records_org_category     ON esg_records(organization_id, category_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_records_org_user         ON esg_records(organization_id, line_user_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_records_extraction       ON esg_records(extraction_id);
CREATE INDEX IF NOT EXISTS idx_esg_records_entry_date       ON esg_records(entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_esg_records_ghg_status       ON esg_records(ghg_status) WHERE ghg_status != 'computed';
