-- Migration: Add is_user_audit column to transactions table
-- Date: 2025-10-20
-- Description: Add is_user_audit boolean column to track if transaction was manually audited by a user

-- Add is_user_audit column (boolean to indicate manual user audit)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS is_user_audit BOOLEAN NOT NULL DEFAULT FALSE;

-- Add comment to explain column
COMMENT ON COLUMN transactions.is_user_audit IS
'Boolean flag indicating whether this transaction was manually audited by a user (true) or automatically audited by AI (false). Set to true when user approves or rejects transaction through manual audit interface.';

-- Create index for efficient queries on user-audited transactions
CREATE INDEX IF NOT EXISTS idx_transactions_is_user_audit
ON transactions (is_user_audit)
WHERE is_user_audit = TRUE;

-- Create composite index for querying user-audited transactions by status
CREATE INDEX IF NOT EXISTS idx_transactions_user_audit_status
ON transactions (is_user_audit, status)
WHERE is_user_audit = TRUE;
