-- Migration: Create transaction_audits table
-- Description: Create table to store transaction audit history (AI and manual audits)
-- Version: 054
-- Date: 2025-11-06 19:00:00

-- Create transaction_audits table
CREATE TABLE IF NOT EXISTS transaction_audits (
    id BIGSERIAL PRIMARY KEY,

    -- Core fields
    transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    audit_notes JSONB NOT NULL DEFAULT '{}'::jsonb,
    by_human BOOLEAN NOT NULL DEFAULT FALSE,

    -- Audit metadata
    auditor_id BIGINT REFERENCES user_locations(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    audit_type VARCHAR(50),  -- 'ai_sync', 'ai_async', 'manual', etc.

    -- AI processing details
    processing_time_ms INTEGER,
    token_usage JSONB,
    model_version VARCHAR(100),

    -- Standard audit fields
    is_active BOOLEAN DEFAULT TRUE,
    created_date BIGINT,
    updated_date BIGINT,
    deleted_date BIGINT,
    created_by_id BIGINT REFERENCES user_locations(id),
    updated_by_id BIGINT REFERENCES user_locations(id),
    deleted_by_id BIGINT REFERENCES user_locations(id)
);

-- Add comments
COMMENT ON TABLE transaction_audits IS 'Stores audit history for transactions including AI and manual audits';
COMMENT ON COLUMN transaction_audits.transaction_id IS 'Reference to the audited transaction';
COMMENT ON COLUMN transaction_audits.audit_notes IS 'Audit results in JSON format: {"s": "status", "v": [violations]}';
COMMENT ON COLUMN transaction_audits.by_human IS 'TRUE if manual audit, FALSE if AI audit';
COMMENT ON COLUMN transaction_audits.audit_type IS 'Type of audit performed (ai_sync, ai_async, manual, etc.)';
COMMENT ON COLUMN transaction_audits.processing_time_ms IS 'Time taken to process audit in milliseconds';
COMMENT ON COLUMN transaction_audits.token_usage IS 'AI token usage details';
COMMENT ON COLUMN transaction_audits.model_version IS 'AI model version used for audit';

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_transaction_audits_transaction_id
ON transaction_audits(transaction_id);

CREATE INDEX IF NOT EXISTS idx_transaction_audits_by_human
ON transaction_audits(by_human);

CREATE INDEX IF NOT EXISTS idx_transaction_audits_organization_id
ON transaction_audits(organization_id);

CREATE INDEX IF NOT EXISTS idx_transaction_audits_created_date
ON transaction_audits(created_date);

CREATE INDEX IF NOT EXISTS idx_transaction_audits_audit_type
ON transaction_audits(audit_type);

-- Create GIN index for audit_notes JSONB queries
CREATE INDEX IF NOT EXISTS idx_transaction_audits_audit_notes
ON transaction_audits USING gin(audit_notes);

-- Create trigger for updated_date
CREATE OR REPLACE FUNCTION update_transaction_audits_updated_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = EXTRACT(EPOCH FROM NOW()) * 1000;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_transaction_audits_updated_date
    BEFORE UPDATE ON transaction_audits
    FOR EACH ROW
    EXECUTE FUNCTION update_transaction_audits_updated_date();

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 054: Created transaction_audits table';
END $$;
