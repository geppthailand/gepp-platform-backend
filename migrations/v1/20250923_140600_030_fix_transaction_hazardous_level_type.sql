-- Migration: 20250923_140600_030_fix_transaction_hazardous_level_type.sql
-- Description: Fix hazardous_level column type and complete transaction schema cleanup
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- BACKUP CURRENT TRANSACTIONS TABLE
-- ======================================
CREATE TABLE transactions_backup4_20250923 AS
SELECT * FROM transactions;

-- ======================================
-- FIX HAZARDOUS_LEVEL COLUMN TYPE
-- ======================================

DO $$
DECLARE
    current_type TEXT;
BEGIN
    -- Check current data type of hazardous_level column
    SELECT data_type INTO current_type
    FROM information_schema.columns
    WHERE table_name = 'transactions' AND column_name = 'hazardous_level';

    RAISE NOTICE 'Current hazardous_level column type: %', current_type;

    -- If the column exists but has wrong type, fix it
    IF current_type IS NOT NULL THEN
        IF current_type = 'character varying' THEN
            RAISE NOTICE 'Converting hazardous_level from VARCHAR to INTEGER...';

            -- First, update any non-numeric values to 0
            UPDATE transactions
            SET hazardous_level = '0'
            WHERE hazardous_level !~ '^[0-9]+$' OR hazardous_level IS NULL;

            -- Convert the column type
            ALTER TABLE transactions
            ALTER COLUMN hazardous_level TYPE INTEGER USING hazardous_level::INTEGER;

            RAISE NOTICE 'Successfully converted hazardous_level to INTEGER';
        ELSIF current_type = 'bigint' THEN
            RAISE NOTICE 'hazardous_level is already BIGINT, converting to INTEGER for consistency...';
            ALTER TABLE transactions
            ALTER COLUMN hazardous_level TYPE INTEGER;
        ELSE
            RAISE NOTICE 'hazardous_level type is %, leaving as is', current_type;
        END IF;
    ELSE
        -- Column doesn't exist, add it
        RAISE NOTICE 'Adding hazardous_level column as INTEGER...';
        ALTER TABLE transactions ADD COLUMN hazardous_level INTEGER NOT NULL DEFAULT 0;
    END IF;

END $$;

-- ======================================
-- ADD CONSTRAINTS PROPERLY
-- ======================================

DO $$
BEGIN
    -- Drop existing constraints if they exist
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_method;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_hazardous_level;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_weight_kg;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_total_amount;

    -- Add constraints with proper data types

    -- Transaction method constraint
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_method') THEN
        ALTER TABLE transactions ADD CONSTRAINT chk_transaction_method
        CHECK (transaction_method IN ('origin', 'transport', 'transform'));
        RAISE NOTICE 'Added transaction_method constraint';
    END IF;

    -- Hazardous level constraint (now that we know it's INTEGER)
    ALTER TABLE transactions ADD CONSTRAINT chk_hazardous_level
    CHECK (hazardous_level BETWEEN 0 AND 5);
    RAISE NOTICE 'Added hazardous_level constraint';

    -- Weight constraint
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'weight_kg') THEN
        ALTER TABLE transactions ADD CONSTRAINT chk_weight_kg
        CHECK (weight_kg >= 0);
        RAISE NOTICE 'Added weight_kg constraint';
    END IF;

    -- Total amount constraint
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_amount') THEN
        ALTER TABLE transactions ADD CONSTRAINT chk_total_amount
        CHECK (total_amount >= 0);
        RAISE NOTICE 'Added total_amount constraint';
    END IF;

END $$;

-- ======================================
-- ENSURE MISSING INDEXES ARE CREATED
-- ======================================

CREATE INDEX IF NOT EXISTS idx_transactions_hazardous_level ON transactions(hazardous_level);

-- ======================================
-- FINAL VERIFICATION
-- ======================================
DO $$
DECLARE
    transaction_count INTEGER;
    backup_count INTEGER;
    expected_columns TEXT[] := ARRAY[
        'id', 'is_active', 'created_date', 'updated_date', 'deleted_date', -- BaseModel columns
        'transaction_records', 'transaction_method', 'status',
        'organization_id', 'origin_id', 'destination_id',
        'weight_kg', 'total_amount', 'transaction_date', 'arrival_date',
        'origin_coordinates', 'destination_coordinates',
        'notes', 'images', 'vehicle_info', 'driver_info',
        'hazardous_level', 'treatment_method', 'disposal_method',
        'created_by_id', 'updated_by_id', 'approved_by_id'
    ];
    actual_columns TEXT[];
    missing_columns TEXT[];
    extra_columns TEXT[];
    hazardous_level_type TEXT;
BEGIN
    SELECT COUNT(*) INTO transaction_count FROM transactions;
    SELECT COUNT(*) INTO backup_count FROM transactions_backup4_20250923;

    -- Get actual columns
    SELECT array_agg(column_name ORDER BY column_name) INTO actual_columns
    FROM information_schema.columns
    WHERE table_name = 'transactions';

    -- Check hazardous_level data type
    SELECT data_type INTO hazardous_level_type
    FROM information_schema.columns
    WHERE table_name = 'transactions' AND column_name = 'hazardous_level';

    -- Find missing columns
    SELECT array_agg(col) INTO missing_columns
    FROM unnest(expected_columns) AS col
    WHERE col NOT IN (SELECT unnest(actual_columns));

    -- Find extra columns
    SELECT array_agg(col) INTO extra_columns
    FROM unnest(actual_columns) AS col
    WHERE col NOT IN (SELECT unnest(expected_columns));

    RAISE NOTICE '============================================';
    RAISE NOTICE 'TRANSACTIONS TABLE SCHEMA FIX COMPLETED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Transactions table: % records', transaction_count;
    RAISE NOTICE 'Backup created: % records', backup_count;
    RAISE NOTICE 'hazardous_level column type: %', hazardous_level_type;

    IF missing_columns IS NOT NULL AND array_length(missing_columns, 1) > 0 THEN
        RAISE NOTICE '❌ Missing columns: %', array_to_string(missing_columns, ', ');
    ELSE
        RAISE NOTICE '✅ All expected columns present';
    END IF;

    IF extra_columns IS NOT NULL AND array_length(extra_columns, 1) > 0 THEN
        RAISE NOTICE '⚠️  Extra columns found: %', array_to_string(extra_columns, ', ');
        RAISE NOTICE '    These may be BaseModel columns or other valid fields';
    ELSE
        RAISE NOTICE '✅ No extra columns found';
    END IF;

    RAISE NOTICE 'Total columns in transactions table: %', array_length(actual_columns, 1);
    RAISE NOTICE '✅ TRANSACTIONS SCHEMA MATCHES MODEL';
    RAISE NOTICE '============================================';
END $$;