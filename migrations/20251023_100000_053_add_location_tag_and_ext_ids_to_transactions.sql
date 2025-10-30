-- Migration: 20251023_100000_053_add_location_tag_and_ext_ids_to_transactions.sql
-- Description: Add location_tag_id, ext_id_1, and ext_id_2 columns to transactions table
-- Date: 2025-10-23
-- Author: Claude Code Assistant

-- ======================================
-- ADD NEW COLUMNS TO TRANSACTIONS TABLE
-- ======================================

DO $$
BEGIN
    RAISE NOTICE 'Adding location_tag_id, ext_id_1, and ext_id_2 columns to transactions table...';

    -- Add location_tag_id column
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'location_tag_id'
    ) THEN
        ALTER TABLE transactions
        ADD COLUMN location_tag_id BIGINT;
        RAISE NOTICE 'Added location_tag_id column';
    ELSE
        RAISE NOTICE 'Column location_tag_id already exists';
    END IF;

    -- Add ext_id_1 column
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'ext_id_1'
    ) THEN
        ALTER TABLE transactions
        ADD COLUMN ext_id_1 VARCHAR(50);
        RAISE NOTICE 'Added ext_id_1 column';
    ELSE
        RAISE NOTICE 'Column ext_id_1 already exists';
    END IF;

    -- Add ext_id_2 column
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'ext_id_2'
    ) THEN
        ALTER TABLE transactions
        ADD COLUMN ext_id_2 VARCHAR(50);
        RAISE NOTICE 'Added ext_id_2 column';
    ELSE
        RAISE NOTICE 'Column ext_id_2 already exists';
    END IF;

    RAISE NOTICE 'Completed adding new columns to transactions table';
END $$;

-- ======================================
-- CREATE INDEXES FOR NEW COLUMNS
-- ======================================

DO $$
BEGIN
    RAISE NOTICE 'Creating indexes for new columns...';

    -- Index for location_tag_id (for faster lookups)
    CREATE INDEX IF NOT EXISTS idx_transactions_location_tag_id
    ON transactions(location_tag_id);
    RAISE NOTICE 'Created index on location_tag_id';

    -- Index for ext_id_1 (for faster lookups)
    CREATE INDEX IF NOT EXISTS idx_transactions_ext_id_1
    ON transactions(ext_id_1);
    RAISE NOTICE 'Created index on ext_id_1';

    -- Index for ext_id_2 (for faster lookups)
    CREATE INDEX IF NOT EXISTS idx_transactions_ext_id_2
    ON transactions(ext_id_2);
    RAISE NOTICE 'Created index on ext_id_2';

    RAISE NOTICE 'Completed creating indexes';
END $$;

-- ======================================
-- VERIFICATION
-- ======================================

DO $$
DECLARE
    location_tag_id_exists BOOLEAN;
    ext_id_1_exists BOOLEAN;
    ext_id_2_exists BOOLEAN;
    location_tag_id_type TEXT;
    ext_id_1_type TEXT;
    ext_id_2_type TEXT;
BEGIN
    -- Check if columns exist
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'location_tag_id'
    ) INTO location_tag_id_exists;

    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'ext_id_1'
    ) INTO ext_id_1_exists;

    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'ext_id_2'
    ) INTO ext_id_2_exists;

    -- Get column types
    IF location_tag_id_exists THEN
        SELECT data_type INTO location_tag_id_type
        FROM information_schema.columns
        WHERE table_name = 'transactions' AND column_name = 'location_tag_id';
    END IF;

    IF ext_id_1_exists THEN
        SELECT data_type INTO ext_id_1_type
        FROM information_schema.columns
        WHERE table_name = 'transactions' AND column_name = 'ext_id_1';
    END IF;

    IF ext_id_2_exists THEN
        SELECT data_type INTO ext_id_2_type
        FROM information_schema.columns
        WHERE table_name = 'transactions' AND column_name = 'ext_id_2';
    END IF;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'MIGRATION VERIFICATION';
    RAISE NOTICE '============================================';

    IF location_tag_id_exists THEN
        RAISE NOTICE '✅ Column location_tag_id exists (type: %)', location_tag_id_type;
    ELSE
        RAISE NOTICE '❌ Column location_tag_id missing';
    END IF;

    IF ext_id_1_exists THEN
        RAISE NOTICE '✅ Column ext_id_1 exists (type: %)', ext_id_1_type;
    ELSE
        RAISE NOTICE '❌ Column ext_id_1 missing';
    END IF;

    IF ext_id_2_exists THEN
        RAISE NOTICE '✅ Column ext_id_2 exists (type: %)', ext_id_2_type;
    ELSE
        RAISE NOTICE '❌ Column ext_id_2 missing';
    END IF;

    IF location_tag_id_exists AND ext_id_1_exists AND ext_id_2_exists THEN
        RAISE NOTICE '✅ MIGRATION COMPLETED SUCCESSFULLY';
    ELSE
        RAISE NOTICE '❌ MIGRATION INCOMPLETE';
    END IF;

    RAISE NOTICE '============================================';
END $$;
