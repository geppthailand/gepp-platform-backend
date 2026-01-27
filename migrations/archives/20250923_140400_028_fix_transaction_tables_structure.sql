-- Migration: 20250923_140400_028_fix_transaction_tables_structure.sql
-- Description: Fix transaction and transaction_records tables to match new schema
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- BACKUP CURRENT TABLES
-- ======================================
CREATE TABLE transaction_records_backup_20250923 AS
SELECT * FROM transaction_records;

CREATE TABLE transactions_backup2_20250923 AS
SELECT * FROM transactions;

-- ======================================
-- DROP AND RECREATE TRANSACTION_RECORDS
-- ======================================

-- Drop existing transaction_records table completely
DROP TABLE IF EXISTS transaction_records CASCADE;

-- Create new transaction_records table with correct structure
CREATE TABLE transaction_records (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT true,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    traceability BIGINT[] NOT NULL DEFAULT '{}', -- Array of transaction_ids sorted
    transaction_type VARCHAR(50) NOT NULL CHECK (transaction_type IN ('manual_input', 'rewards', 'iot')),
    material_id BIGINT REFERENCES materials(id) ON DELETE SET NULL,
    main_material_id BIGINT NOT NULL REFERENCES main_materials(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES material_categories(id) ON DELETE CASCADE,
    tags JSONB NOT NULL DEFAULT '[]', -- Array of tuples [(material_tag_group_id, material_tag_id), ...]
    unit VARCHAR(100) NOT NULL,
    origin_quantity DECIMAL(15,4) NOT NULL DEFAULT 0,
    origin_weight_kg DECIMAL(15,4) NOT NULL DEFAULT 0,
    origin_price_per_unit DECIMAL(15,4) NOT NULL DEFAULT 0,
    total_amount DECIMAL(15,4) NOT NULL DEFAULT 0,
    currency_id BIGINT REFERENCES currencies(id) ON DELETE SET NULL,
    notes TEXT,
    images JSONB NOT NULL DEFAULT '[]', -- Array of image URLs/paths
    origin_coordinates JSONB, -- {lat: float, lng: float}
    destination_coordinates JSONB, -- {lat: float, lng: float}
    hazardous_level INTEGER NOT NULL DEFAULT 0 CHECK (hazardous_level BETWEEN 0 AND 5),
    treatment_method VARCHAR(255),
    disposal_method VARCHAR(255),
    created_by_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    approved_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    completed_date TIMESTAMP WITH TIME ZONE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    -- Constraints
    CONSTRAINT chk_transaction_records_quantities CHECK (
        origin_quantity >= 0 AND
        origin_weight_kg >= 0 AND
        origin_price_per_unit >= 0 AND
        total_amount >= 0
    )
);

-- Add comments for transaction_records
COMMENT ON TABLE transaction_records IS 'Individual material transaction records with detailed tracking and traceability';
COMMENT ON COLUMN transaction_records.created_transaction_id IS 'Reference to the transaction that created this record';
COMMENT ON COLUMN transaction_records.traceability IS 'Sorted array of transaction IDs showing the material journey';
COMMENT ON COLUMN transaction_records.transaction_type IS 'Type of transaction: manual_input, rewards, or iot';
COMMENT ON COLUMN transaction_records.tags IS 'Material condition tags: [(tag_group_id, tag_id), ...]';

-- Create indexes for transaction_records
CREATE INDEX idx_transaction_records_created_transaction ON transaction_records(created_transaction_id);
CREATE INDEX idx_transaction_records_material ON transaction_records(material_id);
CREATE INDEX idx_transaction_records_main_material ON transaction_records(main_material_id);
CREATE INDEX idx_transaction_records_category ON transaction_records(category_id);
CREATE INDEX idx_transaction_records_currency ON transaction_records(currency_id);
CREATE INDEX idx_transaction_records_created_by ON transaction_records(created_by_id);
CREATE INDEX idx_transaction_records_approved_by ON transaction_records(approved_by_id);
CREATE INDEX idx_transaction_records_status ON transaction_records(status);
CREATE INDEX idx_transaction_records_transaction_type ON transaction_records(transaction_type);
CREATE INDEX idx_transaction_records_is_active ON transaction_records(is_active);
CREATE INDEX idx_transaction_records_created_date ON transaction_records(created_date);

-- GIN indexes for arrays and JSONB
CREATE INDEX idx_transaction_records_traceability ON transaction_records USING GIN(traceability);
CREATE INDEX idx_transaction_records_tags ON transaction_records USING GIN(tags jsonb_ops);
CREATE INDEX idx_transaction_records_images ON transaction_records USING GIN(images jsonb_ops);
CREATE INDEX idx_transaction_records_origin_coords ON transaction_records USING GIN(origin_coordinates jsonb_ops);
CREATE INDEX idx_transaction_records_dest_coords ON transaction_records USING GIN(destination_coordinates jsonb_ops);

-- ======================================
-- RESTRUCTURE TRANSACTIONS TABLE
-- ======================================

-- Remove old columns that don't fit the new structure
DO $$
BEGIN
    -- Remove old columns one by one, checking if they exist first
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_number') THEN
        ALTER TABLE transactions DROP COLUMN transaction_number;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_type_id') THEN
        ALTER TABLE transactions DROP COLUMN transaction_type_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'reference_number') THEN
        ALTER TABLE transactions DROP COLUMN reference_number;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'batch_number') THEN
        ALTER TABLE transactions DROP COLUMN batch_number;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'source_location_id') THEN
        ALTER TABLE transactions DROP COLUMN source_location_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'destination_location_id') THEN
        ALTER TABLE transactions DROP COLUMN destination_location_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'priority') THEN
        ALTER TABLE transactions DROP COLUMN priority;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'scheduled_pickup_date') THEN
        ALTER TABLE transactions DROP COLUMN scheduled_pickup_date;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'actual_pickup_date') THEN
        ALTER TABLE transactions DROP COLUMN actual_pickup_date;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'scheduled_delivery_date') THEN
        ALTER TABLE transactions DROP COLUMN scheduled_delivery_date;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'actual_delivery_date') THEN
        ALTER TABLE transactions DROP COLUMN actual_delivery_date;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'completed_date') THEN
        ALTER TABLE transactions DROP COLUMN completed_date;
    END IF;

    -- Drop other old columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'driver_id') THEN
        ALTER TABLE transactions DROP COLUMN driver_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'collector_id') THEN
        ALTER TABLE transactions DROP COLUMN collector_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'receiver_id') THEN
        ALTER TABLE transactions DROP COLUMN receiver_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'verified_by_id') THEN
        ALTER TABLE transactions DROP COLUMN verified_by_id;
    END IF;

    -- Drop more old columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'vehicle_number') THEN
        ALTER TABLE transactions DROP COLUMN vehicle_number;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'vehicle_type') THEN
        ALTER TABLE transactions DROP COLUMN vehicle_type;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'route_id') THEN
        ALTER TABLE transactions DROP COLUMN route_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'distance_km') THEN
        ALTER TABLE transactions DROP COLUMN distance_km;
    END IF;

    -- Drop aggregation columns that will be replaced
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_weight') THEN
        ALTER TABLE transactions DROP COLUMN total_weight;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_volume') THEN
        ALTER TABLE transactions DROP COLUMN total_volume;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_items') THEN
        ALTER TABLE transactions DROP COLUMN total_items;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_value') THEN
        ALTER TABLE transactions DROP COLUMN total_value;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'currency') THEN
        ALTER TABLE transactions DROP COLUMN currency;
    END IF;

    RAISE NOTICE 'Old columns removed from transactions table';
END $$;

-- Add new columns to transactions table if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_records') THEN
        ALTER TABLE transactions ADD COLUMN transaction_records BIGINT[] NOT NULL DEFAULT '{}';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_method') THEN
        ALTER TABLE transactions ADD COLUMN transaction_method VARCHAR(50) NOT NULL DEFAULT 'origin'
        CHECK (transaction_method IN ('origin', 'transport', 'transform'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'origin_id') THEN
        ALTER TABLE transactions ADD COLUMN origin_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'destination_id') THEN
        ALTER TABLE transactions ADD COLUMN destination_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'weight_kg') THEN
        ALTER TABLE transactions ADD COLUMN weight_kg DECIMAL(15,4) NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'total_amount') THEN
        ALTER TABLE transactions ADD COLUMN total_amount DECIMAL(15,4) NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'arrival_date') THEN
        ALTER TABLE transactions ADD COLUMN arrival_date TIMESTAMP WITH TIME ZONE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'vehicle_info') THEN
        ALTER TABLE transactions ADD COLUMN vehicle_info JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'driver_info') THEN
        ALTER TABLE transactions ADD COLUMN driver_info JSONB;
    END IF;

    RAISE NOTICE 'New columns added to transactions table';
END $$;

-- Add comments for transactions table
COMMENT ON TABLE transactions IS 'Transaction batches that group multiple transaction records';
COMMENT ON COLUMN transactions.transaction_records IS 'Array of transaction_record IDs belonging to this transaction batch';
COMMENT ON COLUMN transactions.transaction_method IS 'Transaction method: origin, transport, or transform';

-- Create new indexes for transactions
CREATE INDEX IF NOT EXISTS idx_transactions_records ON transactions USING GIN(transaction_records);
CREATE INDEX IF NOT EXISTS idx_transactions_method ON transactions(transaction_method);
CREATE INDEX IF NOT EXISTS idx_transactions_origin ON transactions(origin_id);
CREATE INDEX IF NOT EXISTS idx_transactions_destination ON transactions(destination_id);
CREATE INDEX IF NOT EXISTS idx_transactions_vehicle_info ON transactions USING GIN(vehicle_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_driver_info ON transactions USING GIN(driver_info jsonb_ops);

-- Add triggers for transaction_records
CREATE TRIGGER update_transaction_records_updated_date
    BEFORE UPDATE ON transaction_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- ======================================
-- VERIFICATION
-- ======================================
DO $$
DECLARE
    tr_count INTEGER;
    t_count INTEGER;
    tr_backup_count INTEGER;
    t_backup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO tr_count FROM transaction_records;
    SELECT COUNT(*) INTO t_count FROM transactions;
    SELECT COUNT(*) INTO tr_backup_count FROM transaction_records_backup_20250923;
    SELECT COUNT(*) INTO t_backup_count FROM transactions_backup2_20250923;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'TRANSACTION TABLES FIX COMPLETED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'New transaction_records table: % records', tr_count;
    RAISE NOTICE 'Updated transactions table: % records', t_count;
    RAISE NOTICE 'Transaction_records backup: % records', tr_backup_count;
    RAISE NOTICE 'Transactions backup: % records', t_backup_count;
    RAISE NOTICE '✅ TRANSACTION SCHEMA FIX COMPLETE';
    RAISE NOTICE '============================================';
END $$;