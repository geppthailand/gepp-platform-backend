-- Migration: 20250923_140300_027_restructure_transactions_system.sql
-- Description: Create transaction_records table and restructure transactions table
-- Date: 2025-09-23
-- Author: Claude Code Assistant

-- ======================================
-- BACKUP EXISTING TRANSACTIONS TABLE
-- ======================================
CREATE TABLE transactions_backup_20250923 AS
SELECT * FROM transactions;

-- ======================================
-- CREATE TRANSACTION_RECORDS TABLE
-- ======================================
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

-- Add comments for documentation
COMMENT ON TABLE transaction_records IS 'Individual material transaction records with detailed tracking and traceability';
COMMENT ON COLUMN transaction_records.created_transaction_id IS 'Reference to the transaction that created this record';
COMMENT ON COLUMN transaction_records.traceability IS 'Sorted array of transaction IDs showing the material journey';
COMMENT ON COLUMN transaction_records.transaction_type IS 'Type of transaction: manual_input, rewards, or iot';
COMMENT ON COLUMN transaction_records.tags IS 'Material condition tags: [(tag_group_id, tag_id), ...]';
COMMENT ON COLUMN transaction_records.origin_coordinates IS 'GPS coordinates where material originated: {lat, lng}';
COMMENT ON COLUMN transaction_records.destination_coordinates IS 'GPS coordinates of material destination: {lat, lng}';
COMMENT ON COLUMN transaction_records.hazardous_level IS 'Hazardous material level (0-5, where 0 is non-hazardous)';

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
CREATE INDEX idx_transaction_records_completed_date ON transaction_records(completed_date);

-- GIN indexes for array and JSONB columns
CREATE INDEX idx_transaction_records_traceability ON transaction_records USING GIN(traceability);
CREATE INDEX idx_transaction_records_tags ON transaction_records USING GIN(tags jsonb_ops);
CREATE INDEX idx_transaction_records_images ON transaction_records USING GIN(images jsonb_ops);
CREATE INDEX idx_transaction_records_origin_coords ON transaction_records USING GIN(origin_coordinates jsonb_ops);
CREATE INDEX idx_transaction_records_dest_coords ON transaction_records USING GIN(destination_coordinates jsonb_ops);

-- ======================================
-- RESTRUCTURE TRANSACTIONS TABLE
-- ======================================

-- First, let's handle the restructuring step by step
DO $$
BEGIN
    RAISE NOTICE 'Starting transactions table restructure...';

    -- Add new columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_records') THEN
        ALTER TABLE transactions ADD COLUMN transaction_records BIGINT[] NOT NULL DEFAULT '{}';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_method') THEN
        ALTER TABLE transactions ADD COLUMN transaction_method VARCHAR(50) NOT NULL DEFAULT 'origin' CHECK (transaction_method IN ('origin', 'transport', 'transform'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'organization_id') THEN
        ALTER TABLE transactions ADD COLUMN organization_id BIGINT REFERENCES organizations(id) ON DELETE SET NULL;
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

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'transaction_date') THEN
        ALTER TABLE transactions ADD COLUMN transaction_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'arrival_date') THEN
        ALTER TABLE transactions ADD COLUMN arrival_date TIMESTAMP WITH TIME ZONE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'origin_coordinates') THEN
        ALTER TABLE transactions ADD COLUMN origin_coordinates JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'destination_coordinates') THEN
        ALTER TABLE transactions ADD COLUMN destination_coordinates JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'notes') THEN
        ALTER TABLE transactions ADD COLUMN notes TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'images') THEN
        ALTER TABLE transactions ADD COLUMN images JSONB NOT NULL DEFAULT '[]';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'vehicle_info') THEN
        ALTER TABLE transactions ADD COLUMN vehicle_info JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'driver_info') THEN
        ALTER TABLE transactions ADD COLUMN driver_info JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'hazardous_level') THEN
        ALTER TABLE transactions ADD COLUMN hazardous_level INTEGER NOT NULL DEFAULT 0 CHECK (hazardous_level BETWEEN 0 AND 5);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'treatment_method') THEN
        ALTER TABLE transactions ADD COLUMN treatment_method VARCHAR(255);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'disposal_method') THEN
        ALTER TABLE transactions ADD COLUMN disposal_method VARCHAR(255);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'created_by_id') THEN
        ALTER TABLE transactions ADD COLUMN created_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'updated_by_id') THEN
        ALTER TABLE transactions ADD COLUMN updated_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'approved_by_id') THEN
        ALTER TABLE transactions ADD COLUMN approved_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL;
    END IF;

    RAISE NOTICE 'New columns added to transactions table';
END $$;

-- Add comments for new transactions table structure
COMMENT ON TABLE transactions IS 'Transaction batches that group multiple transaction records';
COMMENT ON COLUMN transactions.transaction_records IS 'Array of transaction_record IDs belonging to this transaction batch';
COMMENT ON COLUMN transactions.transaction_method IS 'Transaction method: origin, transport, or transform';
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

-- Create new indexes for transactions table
CREATE INDEX IF NOT EXISTS idx_transactions_organization ON transactions(organization_id);
CREATE INDEX IF NOT EXISTS idx_transactions_origin ON transactions(origin_id);
CREATE INDEX IF NOT EXISTS idx_transactions_destination ON transactions(destination_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_by ON transactions(created_by_id);
CREATE INDEX IF NOT EXISTS idx_transactions_updated_by ON transactions(updated_by_id);
CREATE INDEX IF NOT EXISTS idx_transactions_approved_by ON transactions(approved_by_id);
CREATE INDEX IF NOT EXISTS idx_transactions_transaction_method ON transactions(transaction_method);
CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_arrival_date ON transactions(arrival_date);
CREATE INDEX IF NOT EXISTS idx_transactions_weight ON transactions(weight_kg);
CREATE INDEX IF NOT EXISTS idx_transactions_amount ON transactions(total_amount);

-- GIN indexes for new JSONB columns
CREATE INDEX IF NOT EXISTS idx_transactions_records ON transactions USING GIN(transaction_records);
CREATE INDEX IF NOT EXISTS idx_transactions_images ON transactions USING GIN(images jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_vehicle_info ON transactions USING GIN(vehicle_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_driver_info ON transactions USING GIN(driver_info jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_origin_coords ON transactions USING GIN(origin_coordinates jsonb_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_dest_coords ON transactions USING GIN(destination_coordinates jsonb_ops);

-- ======================================
-- CREATE TRIGGERS
-- ======================================

-- Add updated_date triggers for new table
CREATE TRIGGER update_transaction_records_updated_date
    BEFORE UPDATE ON transaction_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- ======================================
-- VERIFICATION AND COMPLETION
-- ======================================

DO $$
DECLARE
    transaction_records_count INTEGER;
    transactions_backup_count INTEGER;
    transactions_new_columns_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO transaction_records_count FROM transaction_records;
    SELECT COUNT(*) INTO transactions_backup_count FROM transactions_backup_20250923;

    -- Count new columns in transactions table
    SELECT COUNT(*) INTO transactions_new_columns_count
    FROM information_schema.columns
    WHERE table_name = 'transactions'
    AND column_name IN ('transaction_records', 'transaction_method', 'organization_id',
                       'origin_id', 'destination_id', 'weight_kg', 'total_amount',
                       'transaction_date', 'arrival_date', 'vehicle_info', 'driver_info');

    RAISE NOTICE '============================================';
    RAISE NOTICE 'TRANSACTIONS SYSTEM RESTRUCTURE FINISHED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Transaction records table created: % records', transaction_records_count;
    RAISE NOTICE 'Transactions backup created: % records', transactions_backup_count;
    RAISE NOTICE 'New columns added to transactions: % columns', transactions_new_columns_count;
    RAISE NOTICE 'Transaction records table: Ready for individual material tracking';
    RAISE NOTICE 'Transactions table: Restructured for batch management';
    RAISE NOTICE '✅ MIGRATION COMPLETE - New transaction system ready!';
    RAISE NOTICE 'Next step: Migrate existing transaction data to new structure';
    RAISE NOTICE '============================================';
END $$;