-- Migration: Update ai_audit_status with new default and constraints (Part 2)
-- Date: 2025-10-09 16:01:00
-- Description: Updates existing data and sets default to 'null' for ai_audit_status

-- Update existing NULL values to 'null' string value
UPDATE transactions
SET ai_audit_status = 'null'
WHERE ai_audit_status IS NULL;

-- Set default value for ai_audit_status column
ALTER TABLE transactions
ALTER COLUMN ai_audit_status SET DEFAULT 'null';

-- Make the column NOT NULL (since we now have a default)
ALTER TABLE transactions
ALTER COLUMN ai_audit_status SET NOT NULL;

-- Update comments
COMMENT ON COLUMN transactions.ai_audit_status IS 'AI audit result status - Values: null (not queued), queued (waiting for audit), approved, rejected, no_action';

-- Create index for queued transactions for efficient queue processing
CREATE INDEX IF NOT EXISTS idx_transactions_ai_audit_queued
ON transactions(ai_audit_status)
WHERE ai_audit_status = 'queued';
