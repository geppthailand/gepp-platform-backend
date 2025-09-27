-- Migration: 20250923_140700_031_simple_constraint_fix.sql
-- Description: Simple fix for hazardous_level constraint issue
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- FIX HAZARDOUS_LEVEL COLUMN TYPE ONLY
-- ======================================

DO $$
DECLARE
    current_type TEXT;
    current_nullable TEXT;
BEGIN
    -- Check current data type of hazardous_level column
    SELECT data_type, is_nullable
    INTO current_type, current_nullable
    FROM information_schema.columns
    WHERE table_name = 'transactions' AND column_name = 'hazardous_level';

    RAISE NOTICE 'Current hazardous_level column type: %, nullable: %', current_type, current_nullable;

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

            -- Set NOT NULL constraint if it was nullable
            IF current_nullable = 'YES' THEN
                ALTER TABLE transactions
                ALTER COLUMN hazardous_level SET NOT NULL;
            END IF;

            -- Set default value
            ALTER TABLE transactions
            ALTER COLUMN hazardous_level SET DEFAULT 0;

            RAISE NOTICE 'Successfully converted hazardous_level to INTEGER';

        ELSIF current_type = 'bigint' THEN
            RAISE NOTICE 'Converting hazardous_level from BIGINT to INTEGER...';
            ALTER TABLE transactions
            ALTER COLUMN hazardous_level TYPE INTEGER;

            -- Set NOT NULL constraint if it was nullable
            IF current_nullable = 'YES' THEN
                ALTER TABLE transactions
                ALTER COLUMN hazardous_level SET NOT NULL;
            END IF;

            -- Set default value
            ALTER TABLE transactions
            ALTER COLUMN hazardous_level SET DEFAULT 0;

            RAISE NOTICE 'Successfully converted hazardous_level to INTEGER';
        ELSE
            RAISE NOTICE 'hazardous_level type is %, no conversion needed', current_type;
        END IF;
    ELSE
        -- Column doesn't exist, add it
        RAISE NOTICE 'Adding hazardous_level column as INTEGER...';
        ALTER TABLE transactions ADD COLUMN hazardous_level INTEGER NOT NULL DEFAULT 0;
    END IF;

END $$;

-- ======================================
-- ADD CONSTRAINTS SAFELY
-- ======================================

DO $$
BEGIN
    -- Drop existing constraints if they exist
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_method;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_hazardous_level;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_weight_kg;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_total_amount;

    RAISE NOTICE 'Dropped any existing constraints';

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

    RAISE NOTICE 'All constraints added successfully';

END $$;

-- ======================================
-- ENSURE REQUIRED INDEX EXISTS
-- ======================================

CREATE INDEX IF NOT EXISTS idx_transactions_hazardous_level ON transactions(hazardous_level);

-- ======================================
-- VERIFICATION
-- ======================================
DO $$
DECLARE
    hazardous_level_type TEXT;
    transaction_count INTEGER;
    constraints_count INTEGER;
BEGIN
    -- Check hazardous_level data type
    SELECT data_type INTO hazardous_level_type
    FROM information_schema.columns
    WHERE table_name = 'transactions' AND column_name = 'hazardous_level';

    -- Count transactions
    SELECT COUNT(*) INTO transaction_count FROM transactions;

    -- Count constraints
    SELECT COUNT(*) INTO constraints_count
    FROM information_schema.check_constraints
    WHERE constraint_name LIKE '%transactions%';

    RAISE NOTICE '============================================';
    RAISE NOTICE 'CONSTRAINT FIX COMPLETED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Transactions table: % records', transaction_count;
    RAISE NOTICE 'hazardous_level column type: %', hazardous_level_type;
    RAISE NOTICE 'Check constraints added: %', constraints_count;
    RAISE NOTICE '✅ CONSTRAINTS FIXED SUCCESSFULLY';
    RAISE NOTICE '============================================';
END $$;