-- Migration: Add audit trigger columns to transactions table
-- Date: 2025-10-10
-- Description: Add reject_triggers and warning_triggers columns to store triggered rule IDs during AI audit

-- Add reject_triggers column (JSONB array to store rule IDs that triggered rejection)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS reject_triggers JSONB DEFAULT '[]'::jsonb;

-- Add warning_triggers column (JSONB array to store rule IDs that triggered warnings)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS warning_triggers JSONB DEFAULT '[]'::jsonb;

-- Add comments to explain columns
COMMENT ON COLUMN transactions.reject_triggers IS
'JSONB array storing rule_id values of audit rules that triggered rejection for this transaction. Example: ["RR-01", "DC-02"]';

COMMENT ON COLUMN transactions.warning_triggers IS
'JSONB array storing rule_id values of audit rules that triggered warnings for this transaction. Example: ["WF-01", "CI-01"]';

COMMENT ON COLUMN transactions.ai_audit_note IS
'Complete audit response from AI including all rule results, messages, and reasons. Stores full JSONB audit data for transparency and analysis.';

-- Create GIN indexes for efficient JSONB queries
CREATE INDEX IF NOT EXISTS idx_transactions_reject_triggers
ON transactions USING GIN (reject_triggers);

CREATE INDEX IF NOT EXISTS idx_transactions_warning_triggers
ON transactions USING GIN (warning_triggers);

-- Create index for querying transactions with any triggers
CREATE INDEX IF NOT EXISTS idx_transactions_has_triggers
ON transactions ((jsonb_array_length(reject_triggers) + jsonb_array_length(warning_triggers)))
WHERE jsonb_array_length(reject_triggers) > 0 OR jsonb_array_length(warning_triggers) > 0;
