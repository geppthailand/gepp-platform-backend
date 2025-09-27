-- Migration: 20250923_140500_029_complete_transaction_schema_cleanup.sql
-- Description: Complete cleanup of transactions table to match the new Transaction model exactly
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- BACKUP CURRENT TRANSACTIONS TABLE
-- ======================================
CREATE TABLE transactions_backup3_20250923 AS
SELECT * FROM transactions;

-- ======================================
-- COMPLETE TRANSACTIONS TABLE CLEANUP
-- ======================================

DO $$
BEGIN
    RAISE NOTICE 'Starting complete transactions table cleanup...';

    -- Remove ALL old columns that don't belong in the new schema
    -- Old transaction system columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_type') THEN
        ALTER TABLE transactions DROP COLUMN transaction_type;
        RAISE NOTICE 'Dropped transaction_type column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'from_organization_id') THEN
        ALTER TABLE transactions DROP COLUMN from_organization_id;
        RAISE NOTICE 'Dropped from_organization_id column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'to_organization_id') THEN
        ALTER TABLE transactions DROP COLUMN to_organization_id;
        RAISE NOTICE 'Dropped to_organization_id column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'from_location_id') THEN
        ALTER TABLE transactions DROP COLUMN from_location_id;
        RAISE NOTICE 'Dropped from_location_id column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'to_location_id') THEN
        ALTER TABLE transactions DROP COLUMN to_location_id;
        RAISE NOTICE 'Dropped to_location_id column';
    END IF;

    -- Material specific columns (these belong in transaction_records)
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'waste_type') THEN
        ALTER TABLE transactions DROP COLUMN waste_type;
        RAISE NOTICE 'Dropped waste_type column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'material_id') THEN
        ALTER TABLE transactions DROP COLUMN material_id;
        RAISE NOTICE 'Dropped material_id column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'quantity') THEN
        ALTER TABLE transactions DROP COLUMN quantity;
        RAISE NOTICE 'Dropped quantity column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'unit') THEN
        ALTER TABLE transactions DROP COLUMN unit;
        RAISE NOTICE 'Dropped unit column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'price_per_unit') THEN
        ALTER TABLE transactions DROP COLUMN price_per_unit;
        RAISE NOTICE 'Dropped price_per_unit column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'currency_id') THEN
        ALTER TABLE transactions DROP COLUMN currency_id;
        RAISE NOTICE 'Dropped currency_id column';
    END IF;

    -- Scheduling columns (not in new schema)
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'scheduled_date') THEN
        ALTER TABLE transactions DROP COLUMN scheduled_date;
        RAISE NOTICE 'Dropped scheduled_date column';
    END IF;

    -- Address columns (coordinates are kept)
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'pickup_address') THEN
        ALTER TABLE transactions DROP COLUMN pickup_address;
        RAISE NOTICE 'Dropped pickup_address column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'delivery_address') THEN
        ALTER TABLE transactions DROP COLUMN delivery_address;
        RAISE NOTICE 'Dropped delivery_address column';
    END IF;

    -- Coordinate columns with wrong names
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'pickup_coordinate') THEN
        ALTER TABLE transactions DROP COLUMN pickup_coordinate;
        RAISE NOTICE 'Dropped pickup_coordinate column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'delivery_coordinate') THEN
        ALTER TABLE transactions DROP COLUMN delivery_coordinate;
        RAISE NOTICE 'Dropped delivery_coordinate column';
    END IF;

    -- Instructions and documentation
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'special_instructions') THEN
        ALTER TABLE transactions DROP COLUMN special_instructions;
        RAISE NOTICE 'Dropped special_instructions column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'documents') THEN
        ALTER TABLE transactions DROP COLUMN documents;
        RAISE NOTICE 'Dropped documents column';
    END IF;

    -- Tracking and waste codes
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'tracking_number') THEN
        ALTER TABLE transactions DROP COLUMN tracking_number;
        RAISE NOTICE 'Dropped tracking_number column';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'waste_code') THEN
        ALTER TABLE transactions DROP COLUMN waste_code;
        RAISE NOTICE 'Dropped waste_code column';
    END IF;

    RAISE NOTICE 'Completed removal of old columns';
END $$;

-- ======================================
-- ENSURE ALL REQUIRED COLUMNS EXIST
-- ======================================

DO $$
BEGIN
    RAISE NOTICE 'Ensuring all required columns exist with correct types...';

    -- Core transaction management
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_records') THEN
        ALTER TABLE transactions ADD COLUMN transaction_records BIGINT[] NOT NULL DEFAULT '{}';
        RAISE NOTICE 'Added transaction_records column';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_method') THEN
        ALTER TABLE transactions ADD COLUMN transaction_method VARCHAR(50) NOT NULL DEFAULT 'origin'
        CHECK (transaction_method IN ('origin', 'transport', 'transform'));
        RAISE NOTICE 'Added transaction_method column';
    END IF;

    -- Status (should already exist from BaseModel)
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
        ALTER TABLE transactions ADD COLUMN hazardous_level BIGINT NOT NULL DEFAULT 0
        CHECK (hazardous_level BETWEEN 0 AND 5);
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
-- RECREATE INDEXES
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

-- Create proper indexes for the new schema
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

-- GIN indexes for JSONB columns
CREATE INDEX IF NOT EXISTS idx_transactions_images ON transactions USING GIN(images jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_vehicle_info ON transactions USING GIN(vehicle_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_driver_info ON transactions USING GIN(driver_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_origin_coords ON transactions USING GIN(origin_coordinates jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_dest_coords ON transactions USING GIN(destination_coordinates jsonb_ops);

-- ======================================
-- UPDATE TABLE CONSTRAINTS
-- ======================================

-- Add table constraints for the new schema
DO $$
BEGIN
    -- Drop old constraints that might exist
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_method;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_hazardous_level;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_weight_kg;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_total_amount;

    -- Add new constraints
    ALTER TABLE transactions ADD CONSTRAINT chk_transaction_method
    CHECK (transaction_method IN ('origin', 'transport', 'transform'));

    ALTER TABLE transactions ADD CONSTRAINT chk_hazardous_level
    CHECK (hazardous_level BETWEEN 0 AND 5);

    ALTER TABLE transactions ADD CONSTRAINT chk_weight_kg
    CHECK (weight_kg >= 0);

    ALTER TABLE transactions ADD CONSTRAINT chk_total_amount
    CHECK (total_amount >= 0);

    RAISE NOTICE 'Added table constraints';
END $$;

-- ======================================
-- UPDATE COMMENTS
-- ======================================

COMMENT ON TABLE transactions IS 'Transaction batches that group multiple transaction records for logistics management';
COMMENT ON COLUMN transactions.transaction_records IS 'Array of transaction_record IDs belonging to this transaction batch';
COMMENT ON COLUMN transactions.transaction_method IS 'Transaction method: origin (collection), transport (movement), or transform (processing)';
COMMENT ON COLUMN transactions.organization_id IS 'Organization responsible for this transaction';
COMMENT ON COLUMN transactions.origin_id IS 'Starting location/user for this transaction';
COMMENT ON COLUMN transactions.destination_id IS 'Ending location/user for this transaction';
COMMENT ON COLUMN transactions.weight_kg IS 'Total weight of all materials in this transaction (kg)';
COMMENT ON COLUMN transactions.total_amount IS 'Total monetary value of this transaction';
COMMENT ON COLUMN transactions.transaction_date IS 'When the transaction was initiated';
COMMENT ON COLUMN transactions.arrival_date IS 'When materials arrived at destination';
COMMENT ON COLUMN transactions.vehicle_info IS 'Vehicle information: {license, type, capacity, etc.}';
COMMENT ON COLUMN transactions.driver_info IS 'Driver information: {name, license, contact, etc.}';
COMMENT ON COLUMN transactions.hazardous_level IS 'Overall hazardous level for this transaction (0-5)';

-- ======================================
-- VERIFICATION
-- ======================================
DO $$
DECLARE
    transaction_count INTEGER;
    backup_count INTEGER;
    column_count INTEGER;
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
    col TEXT;
BEGIN
    SELECT COUNT(*) INTO transaction_count FROM transactions;
    SELECT COUNT(*) INTO backup_count FROM transactions_backup3_20250923;

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
    RAISE NOTICE 'TRANSACTIONS TABLE COMPLETE CLEANUP FINISHED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Transactions table: % records', transaction_count;
    RAISE NOTICE 'Backup created: % records', backup_count;

    IF missing_columns IS NOT NULL AND array_length(missing_columns, 1) > 0 THEN
        RAISE NOTICE '❌ Missing columns: %', array_to_string(missing_columns, ', ');
    ELSE
        RAISE NOTICE '✅ All expected columns present';
    END IF;

    IF extra_columns IS NOT NULL AND array_length(extra_columns, 1) > 0 THEN
        RAISE NOTICE '⚠️  Extra columns found: %', array_to_string(extra_columns, ', ');
    ELSE
        RAISE NOTICE '✅ No extra columns found';
    END IF;

    RAISE NOTICE 'Total columns in transactions table: %', array_length(actual_columns, 1);
    RAISE NOTICE '✅ TRANSACTIONS SCHEMA CLEANUP COMPLETE';
    RAISE NOTICE '============================================';
END $$;