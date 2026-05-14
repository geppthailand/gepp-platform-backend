-- ==========================================
-- Add metadata JSONB and currency columns to esg_data_entries
-- metadata: stores tags, confidence, record context from AI extraction
-- currency: stores currency code (e.g. USD, THB) for financial datapoints
-- ==========================================

ALTER TABLE esg_data_entries ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE esg_data_entries ADD COLUMN IF NOT EXISTS currency VARCHAR(10);

CREATE INDEX IF NOT EXISTS idx_esg_data_entries_metadata ON esg_data_entries USING GIN (metadata);
