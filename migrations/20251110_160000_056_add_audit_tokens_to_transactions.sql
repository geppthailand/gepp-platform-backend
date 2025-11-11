-- Migration: Add audit_tokens column to transactions table
-- Purpose: Store AI audit token usage data separately from ai_audit_note
-- Date: 2025-11-10
-- Version: 056

-- Add audit_tokens column to store token usage data with breakdown
-- Structure: {t: {input, output, thinking}, tr: {input, output, thinking}, durations: {jud: <secs>, obs: {<record_id>: <secs>}}}
-- t = transaction judgment phase tokens
-- tr = transaction record observation phase tokens (sum of all records)
-- durations = time spent in seconds for judgment (jud) and per-record observations (obs)
ALTER TABLE transactions
ADD COLUMN audit_tokens JSONB DEFAULT NULL;

-- Add comment for documentation
COMMENT ON COLUMN transactions.audit_tokens IS 'AI audit token usage and duration data. Structure: {t: {input, output, thinking}, tr: {input, output, thinking}, durations: {jud: <secs>, obs: {<record_id>: <secs>}}}. t=judgment phase, tr=observation phase (sum of all records), durations=time spent in seconds.';

-- Create index for querying by token usage (optional, for analytics)
CREATE INDEX IF NOT EXISTS idx_transactions_audit_tokens ON transactions USING gin (audit_tokens);

-- Verify the column was added
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'audit_tokens'
    ) THEN
        RAISE NOTICE 'Migration successful: audit_tokens column added to transactions table';
    ELSE
        RAISE EXCEPTION 'Migration failed: audit_tokens column was not added';
    END IF;
END $$;
