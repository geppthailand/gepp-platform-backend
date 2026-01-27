-- Migration: Change ai_audit_note column from TEXT to JSONB (FIXED v2)
-- Date: 2025-11-10
-- Description: Change ai_audit_note column type from TEXT to JSONB to properly store structured audit data
-- This version checks if already JSONB and handles invalid data gracefully

DO $$
DECLARE
    column_type TEXT;
BEGIN
    -- Check current column type
    SELECT data_type INTO column_type
    FROM information_schema.columns
    WHERE table_name = 'transactions'
    AND column_name = 'ai_audit_note';

    -- If already JSONB, skip
    IF column_type = 'jsonb' THEN
        RAISE NOTICE 'Column ai_audit_note is already JSONB type, skipping migration';
        RETURN;
    END IF;

    RAISE NOTICE 'Converting ai_audit_note from % to JSONB...', column_type;

    -- Step 1: Clean up any empty strings or invalid JSON (only if TEXT type)
    IF column_type IN ('text', 'character varying') THEN
        UPDATE transactions
        SET ai_audit_note = NULL
        WHERE ai_audit_note = ''
           OR ai_audit_note = '""'
           OR TRIM(ai_audit_note) = '';

        RAISE NOTICE 'Cleaned up empty strings';
    END IF;

    -- Step 2: Try to identify and fix any invalid JSON strings
    DECLARE
        rec RECORD;
        is_valid_json BOOLEAN;
    BEGIN
        FOR rec IN
            SELECT id, ai_audit_note
            FROM transactions
            WHERE ai_audit_note IS NOT NULL
        LOOP
            BEGIN
                -- Try to parse as JSON
                PERFORM rec.ai_audit_note::JSONB;
                is_valid_json := TRUE;
            EXCEPTION
                WHEN OTHERS THEN
                    -- If it fails, wrap the text content
                    is_valid_json := FALSE;
                    UPDATE transactions
                    SET ai_audit_note = jsonb_build_object('legacy_text', rec.ai_audit_note)::text
                    WHERE id = rec.id;
                    RAISE NOTICE 'Converted invalid JSON for transaction %', rec.id;
            END;
        END LOOP;
    END;

    -- Step 3: Now change the column type
    ALTER TABLE transactions
    ALTER COLUMN ai_audit_note TYPE JSONB USING
        CASE
            WHEN ai_audit_note IS NULL THEN NULL
            WHEN TRIM(ai_audit_note) = '' THEN NULL
            ELSE ai_audit_note::JSONB
        END;

    -- Step 4: Add a comment to document the change
    COMMENT ON COLUMN transactions.ai_audit_note IS 'Stores AI audit observations and status as JSONB with structure: {status: string, audits: {record_id: {images: [{id, obs}]}}}. Token data moved to audit_tokens column.';

    RAISE NOTICE 'Successfully changed ai_audit_note column to JSONB type';

END $$;
