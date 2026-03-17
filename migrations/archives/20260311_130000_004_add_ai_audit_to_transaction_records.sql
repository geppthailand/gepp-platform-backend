-- Migration: Add AI audit columns to transaction_records
-- Date: 2026-03-11
-- Description: Add ai_audit_status and ai_audit_note columns to transaction_records table

ALTER TABLE transaction_records
    ADD COLUMN IF NOT EXISTS ai_audit_status VARCHAR(50) NOT NULL DEFAULT 'null',
    ADD COLUMN IF NOT EXISTS ai_audit_note JSONB DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_transaction_records_ai_audit_status ON transaction_records(ai_audit_status);

COMMENT ON COLUMN transaction_records.ai_audit_status IS 'AI audit status per record: null (not audited), queued, approved, rejected';
COMMENT ON COLUMN transaction_records.ai_audit_note IS 'JSONB containing AI audit notes and matching results for this record';
