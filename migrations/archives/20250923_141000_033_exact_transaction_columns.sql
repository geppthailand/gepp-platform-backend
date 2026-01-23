-- Migration: 20250923_141000_033_exact_transaction_columns.sql
-- Description: Ensure transactions table has exactly the specified columns
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- BACKUP CURRENT TRANSACTIONS TABLE
-- ======================================
CREATE TABLE transactions_backup5_20250923 AS
SELECT * FROM transactions;

-- ======================================
-- GET CURRENT COLUMNS AND CLEAN UP
-- ======================================

DO $$
DECLARE
    col_name TEXT;
    expected_columns TEXT[] := ARRAY[
        'id', 'is_active', 'transaction_records', 'transaction_method', 'status',
        'organization_id', 'origin_id', 'destination_id', 'weight_kg', 'total_amount',
        'transaction_date', 'arrival_date', 'origin_coordinates', 'destination_coordinates',
        'notes', 'images', 'vehicle_info', 'driver_info', 'hazardous_level',
        'treatment_method', 'disposal_method', 'created_by_id', 'updated_by_id', 'approved_by_id',
        'created_date', 'updated_date', 'deleted_date'
    ];
    actual_columns TEXT[];
    extra_columns TEXT[];
BEGIN
    RAISE NOTICE 'Starting exact column specification for transactions table...';

    -- Get all current columns
    SELECT array_agg(column_name) INTO actual_columns
    FROM information_schema.columns
    WHERE table_name = 'transactions';

    -- Find extra columns to remove
    SELECT array_agg(col) INTO extra_columns
    FROM unnest(actual_columns) AS col
    WHERE col NOT IN (SELECT unnest(expected_columns));

    -- Remove extra columns
    IF extra_columns IS NOT NULL AND array_length(extra_columns, 1) > 0 THEN
        FOREACH col_name IN ARRAY extra_columns
        LOOP
            EXECUTE format('ALTER TABLE transactions DROP COLUMN IF EXISTS %I', col_name);
            RAISE NOTICE 'Dropped extra column: %', col_name;
        END LOOP;
    END IF;

    RAISE NOTICE 'Completed removal of extra columns';
END $$;

-- ======================================
-- ENSURE ALL REQUIRED COLUMNS EXIST
-- ======================================

DO $$
BEGIN
    RAISE NOTICE 'Ensuring all required columns exist with correct types...';

    -- BaseModel columns (should already exist)
    -- id, is_active, created_date, updated_date, deleted_date

    -- Core transaction management
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_records') THEN
        ALTER TABLE transactions ADD COLUMN transaction_records BIGINT[] NOT NULL DEFAULT '{}';
        RAISE NOTICE 'Added transaction_records column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_method') THEN
        ALTER TABLE transactions ADD COLUMN transaction_method VARCHAR(50) NOT NULL DEFAULT 'origin';
        RAISE NOTICE 'Added transaction_method column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'status') THEN
        ALTER TABLE transactions ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'draft';
        RAISE NOTICE 'Added status column';
    END IF;

    -- Organization and locations
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'organization_id') THEN
        ALTER TABLE transactions ADD COLUMN organization_id BIGINT REFERENCES organizations(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added organization_id column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'origin_id') THEN
        ALTER TABLE transactions ADD COLUMN origin_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added origin_id column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'destination_id') THEN
        ALTER TABLE transactions ADD COLUMN destination_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added destination_id column';
    END IF;

    -- Aggregated data
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'weight_kg') THEN
        ALTER TABLE transactions ADD COLUMN weight_kg DECIMAL(15,4) NOT NULL DEFAULT 0;
        RAISE NOTICE 'Added weight_kg column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_amount') THEN
        ALTER TABLE transactions ADD COLUMN total_amount DECIMAL(15,4) NOT NULL DEFAULT 0;
        RAISE NOTICE 'Added total_amount column';
    END IF;

    -- Date tracking
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_date') THEN
        ALTER TABLE transactions ADD COLUMN transaction_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
        RAISE NOTICE 'Added transaction_date column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'arrival_date') THEN
        ALTER TABLE transactions ADD COLUMN arrival_date TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added arrival_date column';
    END IF;

    -- Location coordinates
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'origin_coordinates') THEN
        ALTER TABLE transactions ADD COLUMN origin_coordinates JSONB;
        RAISE NOTICE 'Added origin_coordinates column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'destination_coordinates') THEN
        ALTER TABLE transactions ADD COLUMN destination_coordinates JSONB;
        RAISE NOTICE 'Added destination_coordinates column';
    END IF;

    -- Documentation and notes
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'notes') THEN
        ALTER TABLE transactions ADD COLUMN notes TEXT;
        RAISE NOTICE 'Added notes column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'images') THEN
        ALTER TABLE transactions ADD COLUMN images JSONB NOT NULL DEFAULT '[]';
        RAISE NOTICE 'Added images column';
    END IF;

    -- Vehicle and driver information
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'vehicle_info') THEN
        ALTER TABLE transactions ADD COLUMN vehicle_info JSONB;
        RAISE NOTICE 'Added vehicle_info column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'driver_info') THEN
        ALTER TABLE transactions ADD COLUMN driver_info JSONB;
        RAISE NOTICE 'Added driver_info column';
    END IF;

    -- Hazardous and treatment information
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'hazardous_level') THEN
        ALTER TABLE transactions ADD COLUMN hazardous_level INTEGER NOT NULL DEFAULT 0;
        RAISE NOTICE 'Added hazardous_level column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'treatment_method') THEN
        ALTER TABLE transactions ADD COLUMN treatment_method VARCHAR(255);
        RAISE NOTICE 'Added treatment_method column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'disposal_method') THEN
        ALTER TABLE transactions ADD COLUMN disposal_method VARCHAR(255);
        RAISE NOTICE 'Added disposal_method column';
    END IF;

    -- People involved
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'created_by_id') THEN
        ALTER TABLE transactions ADD COLUMN created_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added created_by_id column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'updated_by_id') THEN
        ALTER TABLE transactions ADD COLUMN updated_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added updated_by_id column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'approved_by_id') THEN
        ALTER TABLE transactions ADD COLUMN approved_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added approved_by_id column';
    END IF;

    RAISE NOTICE 'Completed ensuring required columns exist';
END $$;

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

    IF current_type = 'character varying' THEN
        RAISE NOTICE 'Converting hazardous_level from VARCHAR to INTEGER...';

        -- First, update any non-numeric values to 0
        UPDATE transactions
        SET hazardous_level = '0'
        WHERE hazardous_level !~ '^[0-9]+$' OR hazardous_level IS NULL;

        -- Convert the column type
        ALTER TABLE transactions
        ALTER COLUMN hazardous_level TYPE INTEGER USING hazardous_level::INTEGER;

        -- Set NOT NULL and default
        ALTER TABLE transactions
        ALTER COLUMN hazardous_level SET NOT NULL;

        ALTER TABLE transactions
        ALTER COLUMN hazardous_level SET DEFAULT 0;

        RAISE NOTICE 'Successfully converted hazardous_level to INTEGER';
    ELSE
        RAISE NOTICE 'hazardous_level type is already %, no conversion needed', current_type;
    END IF;
END $$;

-- ======================================
-- ADD CONSTRAINTS
-- ======================================

DO $$
BEGIN
    -- Drop existing constraints if they exist
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_method;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_hazardous_level;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_weight_kg;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_total_amount;

    -- Add constraints
    ALTER TABLE transactions ADD CONSTRAINT chk_transaction_method
    CHECK (transaction_method IN ('origin', 'transport', 'transform'));

    ALTER TABLE transactions ADD CONSTRAINT chk_hazardous_level
    CHECK (hazardous_level BETWEEN 0 AND 5);

    ALTER TABLE transactions ADD CONSTRAINT chk_weight_kg
    CHECK (weight_kg >= 0);

    ALTER TABLE transactions ADD CONSTRAINT chk_total_amount
    CHECK (total_amount >= 0);

    RAISE NOTICE 'Added all constraints successfully';
END $$;

-- ======================================
-- CREATE INDEXES
-- ======================================

-- Drop any old indexes that might conflict
DROP INDEX IF EXISTS idx_transactions_transaction_type;
DROP INDEX IF EXISTS idx_transactions_from_organization;
DROP INDEX IF EXISTS idx_transactions_to_organization;
DROP INDEX IF EXISTS idx_transactions_from_location;
DROP INDEX IF EXISTS idx_transactions_to_location;
DROP INDEX IF EXISTS idx_transactions_material;
DROP INDEX IF EXISTS idx_transactions_currency;
DROP INDEX IF EXISTS idx_transactions_tracking_number;

-- Create proper indexes for the exact schema
CREATE INDEX IF NOT EXISTS idx_transactions_records ON transactions USING GIN(transaction_records);
CREATE INDEX IF NOT EXISTS idx_transactions_method ON transactions(transaction_method);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_organization ON transactions(organization_id);
CREATE INDEX IF NOT EXISTS idx_transactions_origin ON transactions(origin_id);
CREATE INDEX IF NOT EXISTS idx_transactions_destination ON transactions(destination_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_by ON transactions(created_by_id);
CREATE INDEX IF NOT EXISTS idx_transactions_updated_by ON transactions(updated_by_id);
CREATE INDEX IF NOT EXISTS idx_transactions_approved_by ON transactions(approved_by_id);
CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_arrival_date ON transactions(arrival_date);
CREATE INDEX IF NOT EXISTS idx_transactions_weight ON transactions(weight_kg);
CREATE INDEX IF NOT EXISTS idx_transactions_amount ON transactions(total_amount);
CREATE INDEX IF NOT EXISTS idx_transactions_hazardous_level ON transactions(hazardous_level);
CREATE INDEX IF NOT EXISTS idx_transactions_is_active ON transactions(is_active);

-- GIN indexes for JSONB columns
CREATE INDEX IF NOT EXISTS idx_transactions_images ON transactions USING GIN(images jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_vehicle_info ON transactions USING GIN(vehicle_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_driver_info ON transactions USING GIN(driver_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_origin_coords ON transactions USING GIN(origin_coordinates jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_dest_coords ON transactions USING GIN(destination_coordinates jsonb_ops);

-- ======================================
-- FINAL VERIFICATION
-- ======================================
DO $$
DECLARE
    transaction_count INTEGER;
    backup_count INTEGER;
    expected_columns TEXT[] := ARRAY[
        'id', 'is_active', 'transaction_records', 'transaction_method', 'status',
        'organization_id', 'origin_id', 'destination_id', 'weight_kg', 'total_amount',
        'transaction_date', 'arrival_date', 'origin_coordinates', 'destination_coordinates',
        'notes', 'images', 'vehicle_info', 'driver_info', 'hazardous_level',
        'treatment_method', 'disposal_method', 'created_by_id', 'updated_by_id', 'approved_by_id',
        'created_date', 'updated_date', 'deleted_date'
    ];
    actual_columns TEXT[];
    missing_columns TEXT[];
    extra_columns TEXT[];
BEGIN
    SELECT COUNT(*) INTO transaction_count FROM transactions;
    SELECT COUNT(*) INTO backup_count FROM transactions_backup5_20250923;

    -- Get actual columns
    SELECT array_agg(column_name ORDER BY column_name) INTO actual_columns
    FROM information_schema.columns
    WHERE table_name = 'transactions';

    -- Find missing columns
    SELECT array_agg(col) INTO missing_columns
    FROM unnest(expected_columns) AS col
    WHERE col NOT IN (SELECT unnest(actual_columns));

    -- Find extra columns
    SELECT array_agg(col) INTO extra_columns
    FROM unnest(actual_columns) AS col
    WHERE col NOT IN (SELECT unnest(expected_columns));

    RAISE NOTICE '============================================';
    RAISE NOTICE 'TRANSACTIONS TABLE EXACT SPECIFICATION COMPLETE';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Transactions table: % records', transaction_count;
    RAISE NOTICE 'Backup created: % records', backup_count;

    IF missing_columns IS NOT NULL AND array_length(missing_columns, 1) > 0 THEN
        RAISE NOTICE '❌ Missing columns: %', array_to_string(missing_columns, ', ');
    ELSE
        RAISE NOTICE '✅ All expected columns present';
    END IF;

    IF extra_columns IS NOT NULL AND array_length(extra_columns, 1) > 0 THEN
        RAISE NOTICE '❌ Extra columns found: %', array_to_string(extra_columns, ', ');
    ELSE
        RAISE NOTICE '✅ No extra columns found';
    END IF;

    RAISE NOTICE 'Total columns in transactions table: %', array_length(actual_columns, 1);
    RAISE NOTICE 'Expected columns: %', array_length(expected_columns, 1);

    IF array_length(actual_columns, 1) = array_length(expected_columns, 1)
       AND (missing_columns IS NULL OR array_length(missing_columns, 1) = 0)
       AND (extra_columns IS NULL OR array_length(extra_columns, 1) = 0) THEN
        RAISE NOTICE '✅ TRANSACTIONS TABLE MATCHES EXACT SPECIFICATION';
    ELSE
        RAISE NOTICE '❌ TRANSACTIONS TABLE DOES NOT MATCH SPECIFICATION';
    END IF;

    RAISE NOTICE '============================================';
END $$;