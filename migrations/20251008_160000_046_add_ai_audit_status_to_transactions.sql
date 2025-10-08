-- Migration: Add AI audit status and note columns to transactions
-- Date: 2025-10-08 16:00:00
-- Description: Adds ai_audit_status and ai_audit_note columns to track AI audit results separately from actual transaction status

-- Create ENUM type for AI audit status
DO $$ BEGIN
    CREATE TYPE ai_audit_status_enum AS ENUM ('approved', 'rejected', 'no_action');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add ai_audit_status column to transactions table
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS ai_audit_status ai_audit_status_enum DEFAULT NULL;

-- Add ai_audit_note column to transactions table
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS ai_audit_note TEXT DEFAULT NULL;

-- Add comments to explain the columns
COMMENT ON COLUMN transactions.ai_audit_status IS 'AI audit result status - shows what AI determined without affecting actual transaction status if organization.allow_ai_audit is false. Values: approved, rejected, no_action (future use)';

COMMENT ON COLUMN transactions.ai_audit_note IS 'AI audit notes and reasoning - stores detailed information about why AI made its decision';

-- Create index for faster queries on ai_audit_status
CREATE INDEX IF NOT EXISTS idx_transactions_ai_audit_status
ON transactions(ai_audit_status)
WHERE ai_audit_status IS NOT NULL;

-- Create composite index for filtering by both status and ai_audit_status
CREATE INDEX IF NOT EXISTS idx_transactions_status_ai_audit
ON transactions(status, ai_audit_status)
WHERE ai_audit_status IS NOT NULL;
