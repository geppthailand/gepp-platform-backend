-- Migration: Add audit history tracking columns
-- Purpose: Enable audit history to survive undo/reset operations
-- 1. Add audit_records (array of transaction_audit IDs) to transaction_audit_history
-- 2. Add audit_status and ai_audit_status snapshot columns to transaction_audits

-- Step 1: Add audit_records column to transaction_audit_history
ALTER TABLE transaction_audit_history
ADD COLUMN IF NOT EXISTS audit_records INTEGER[] DEFAULT '{}';

COMMENT ON COLUMN transaction_audit_history.audit_records IS 'Array of transaction_audits.id created during this batch';

-- Step 2: Add audit_status and ai_audit_status to transaction_audits
ALTER TABLE transaction_audits
ADD COLUMN IF NOT EXISTS audit_status VARCHAR(50),
ADD COLUMN IF NOT EXISTS ai_audit_status VARCHAR(50);

COMMENT ON COLUMN transaction_audits.audit_status IS 'Snapshot of transaction.status at audit time';
COMMENT ON COLUMN transaction_audits.ai_audit_status IS 'Snapshot of transaction.ai_audit_status at audit time (survives undo)';

-- Step 3: Backfill ai_audit_status from existing audit_notes for historical records
-- Disable the updated_date trigger to avoid timestamp overflow error
ALTER TABLE transaction_audits DISABLE TRIGGER ALL;

UPDATE transaction_audits
SET ai_audit_status = audit_notes->>'status'
WHERE ai_audit_status IS NULL
  AND audit_notes IS NOT NULL
  AND audit_notes->>'status' IS NOT NULL;

ALTER TABLE transaction_audits ENABLE TRIGGER ALL;
