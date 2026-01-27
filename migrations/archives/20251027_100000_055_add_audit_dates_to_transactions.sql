-- Migration: Add audit_date and ai_audit_date columns to transactions
-- Version: 055
-- Date: 2025-10-27
-- Description: Add audit_date and ai_audit_date timestamp columns to track when audits were performed

-- Add ai_audit_date column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'ai_audit_date'
    ) THEN
        ALTER TABLE transactions
        ADD COLUMN ai_audit_date TIMESTAMP WITHOUT TIME ZONE;

        RAISE NOTICE 'Added ai_audit_date column to transactions';
    ELSE
        RAISE NOTICE 'Column ai_audit_date already exists in transactions';
    END IF;
END $$;

-- Add audit_date column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'audit_date'
    ) THEN
        ALTER TABLE transactions
        ADD COLUMN audit_date TIMESTAMP WITHOUT TIME ZONE;

        RAISE NOTICE 'Added audit_date column to transactions';
    ELSE
        RAISE NOTICE 'Column audit_date already exists in transactions';
    END IF;
END $$;

-- Create index for faster queries on audit dates
CREATE INDEX IF NOT EXISTS idx_transactions_ai_audit_date
ON transactions(ai_audit_date)
WHERE ai_audit_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_audit_date
ON transactions(audit_date)
WHERE audit_date IS NOT NULL;

-- Add comment to columns for documentation
COMMENT ON COLUMN transactions.ai_audit_date IS 'Timestamp when AI audit was performed on this transaction';
COMMENT ON COLUMN transactions.audit_date IS 'Timestamp when manual audit was performed on this transaction';

-- Verify the columns were added
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_name = 'transactions'
    AND column_name IN ('ai_audit_date', 'audit_date');

    IF v_count = 2 THEN
        RAISE NOTICE 'Migration completed successfully. Both audit date columns added to transactions table.';
    ELSE
        RAISE WARNING 'Migration incomplete. Expected 2 columns, found %', v_count;
    END IF;
END $$;
