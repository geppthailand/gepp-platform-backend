-- Migration: Add 'failed' status to ai_audit_status enum
-- Purpose: Allow marking transactions that failed during AI audit process
-- Date: 2025-11-11
-- Version: 057

-- Add 'failed' value to ai_audit_status_enum
DO $$
BEGIN
    -- Check if 'failed' value already exists
    IF NOT EXISTS (
        SELECT 1
        FROM pg_enum
        WHERE enumlabel = 'failed'
        AND enumtypid = (
            SELECT oid
            FROM pg_type
            WHERE typname = 'ai_audit_status_enum'
        )
    ) THEN
        -- Add 'failed' to the enum
        ALTER TYPE ai_audit_status_enum ADD VALUE 'failed';
        RAISE NOTICE 'Added ''failed'' value to ai_audit_status_enum';
    ELSE
        RAISE NOTICE '''failed'' value already exists in ai_audit_status_enum, skipping';
    END IF;
END $$;

-- Add comment to document the new status
COMMENT ON TYPE ai_audit_status_enum IS 'AI audit status for transactions. Values: null (not queued), queued (waiting for audit), approved (passed audit), rejected (failed audit rules), no_action (audit complete but no action needed), failed (audit process error)';
