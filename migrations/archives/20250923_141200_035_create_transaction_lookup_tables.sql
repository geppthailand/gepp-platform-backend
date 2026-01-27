--
-- Migration: Create transaction lookup tables
-- Description: Create transaction_types and transaction_methods lookup tables
-- Date: September 23, 2025
-- Version: 035
--

BEGIN;

-- =============================================================================
-- TRANSACTION TYPES TABLE
-- =============================================================================
-- Purpose: Lookup table for TransactionRecord.transaction_type values
-- Current values: manual_input, rewards, iot

CREATE TABLE IF NOT EXISTS transaction_types (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE NULL,

    -- Transaction type details
    code VARCHAR(50) UNIQUE NOT NULL,
    name_en VARCHAR(255) NOT NULL,
    name_th VARCHAR(255) NOT NULL,
    description_en TEXT,
    description_th TEXT,
    color VARCHAR(7) NOT NULL DEFAULT '#808080',

    -- Ordering and display
    display_order INTEGER NOT NULL DEFAULT 0,
    is_system_default BOOLEAN NOT NULL DEFAULT false
);

-- Insert default transaction types
INSERT INTO transaction_types (code, name_en, name_th, description_en, description_th, color, display_order, is_system_default) VALUES
('manual_input', 'Manual Input', 'กรอกข้อมูลด้วยตนเอง', 'Manually entered transaction record', 'บันทึกธุรกรรมที่กรอกข้อมูลด้วยตนเอง', '#3B82F6', 1, true),
('rewards', 'Rewards', 'รางวัล', 'Transaction record from rewards system', 'บันทึกธุรกรรมจากระบบรางวัล', '#10B981', 2, true),
('iot', 'IoT Device', 'อุปกรณ์ IoT', 'Automatically detected by IoT devices', 'ตรวจจับโดยอุปกรณ์ IoT โดยอัตโนมัติ', '#F59E0B', 3, true);

-- =============================================================================
-- TRANSACTION METHODS TABLE
-- =============================================================================
-- Purpose: Lookup table for Transaction.transaction_method values
-- Current values: origin, transport, transform

CREATE TABLE IF NOT EXISTS transaction_methods (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE NULL,

    -- Transaction method details
    code VARCHAR(50) UNIQUE NOT NULL,
    name_en VARCHAR(255) NOT NULL,
    name_th VARCHAR(255) NOT NULL,
    description_en TEXT,
    description_th TEXT,
    color VARCHAR(7) NOT NULL DEFAULT '#808080',

    -- Ordering and display
    display_order INTEGER NOT NULL DEFAULT 0,
    is_system_default BOOLEAN NOT NULL DEFAULT false
);

-- Insert default transaction methods
INSERT INTO transaction_methods (code, name_en, name_th, description_en, description_th, color, display_order, is_system_default) VALUES
('origin', 'Origin', 'ต้นทาง', 'Transaction at the point of origin', 'ธุรกรรมที่จุดเริ่มต้น', '#8B5CF6', 1, true),
('transport', 'Transport', 'การขนส่ง', 'Transaction during transportation', 'ธุรกรรมในระหว่างการขนส่ง', '#06B6D4', 2, true),
('transform', 'Transform', 'การแปลงสภาพ', 'Transaction involving material transformation', 'ธุรกรรมที่เกี่ยวข้องกับการแปลงสภาพวัสดุ', '#EF4444', 3, true);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

-- Transaction Types indexes
CREATE INDEX IF NOT EXISTS idx_transaction_types_code ON transaction_types(code);
CREATE INDEX IF NOT EXISTS idx_transaction_types_is_active ON transaction_types(is_active);
CREATE INDEX IF NOT EXISTS idx_transaction_types_is_system_default ON transaction_types(is_system_default);
CREATE INDEX IF NOT EXISTS idx_transaction_types_display_order ON transaction_types(display_order);
CREATE INDEX IF NOT EXISTS idx_transaction_types_deleted_date ON transaction_types(deleted_date);

-- Transaction Methods indexes
CREATE INDEX IF NOT EXISTS idx_transaction_methods_code ON transaction_methods(code);
CREATE INDEX IF NOT EXISTS idx_transaction_methods_is_active ON transaction_methods(is_active);
CREATE INDEX IF NOT EXISTS idx_transaction_methods_is_system_default ON transaction_methods(is_system_default);
CREATE INDEX IF NOT EXISTS idx_transaction_methods_display_order ON transaction_methods(display_order);
CREATE INDEX IF NOT EXISTS idx_transaction_methods_deleted_date ON transaction_methods(deleted_date);

-- =============================================================================
-- ALTER EXISTING TABLES TO ADD FOREIGN KEY REFERENCES
-- =============================================================================

-- Add new columns to transaction_records table
ALTER TABLE transaction_records
ADD COLUMN IF NOT EXISTS transaction_type_id BIGINT REFERENCES transaction_types(id) ON DELETE SET NULL;

-- Add new column to transactions table
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS transaction_method_id BIGINT REFERENCES transaction_methods(id) ON DELETE SET NULL;

-- =============================================================================
-- DATA MIGRATION - UPDATE EXISTING RECORDS
-- =============================================================================

-- Update transaction_records to reference transaction_types
UPDATE transaction_records
SET transaction_type_id = tt.id
FROM transaction_types tt
WHERE transaction_records.transaction_type = tt.code
AND transaction_records.transaction_type_id IS NULL;

-- Update transactions to reference transaction_methods
UPDATE transactions
SET transaction_method_id = tm.id
FROM transaction_methods tm
WHERE transactions.transaction_method = tm.code
AND transactions.transaction_method_id IS NULL;

-- =============================================================================
-- ADD INDEXES FOR NEW FOREIGN KEY COLUMNS
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_transaction_records_transaction_type_id ON transaction_records(transaction_type_id);
CREATE INDEX IF NOT EXISTS idx_transactions_transaction_method_id ON transactions(transaction_method_id);

-- =============================================================================
-- CONSTRAINTS AND VALIDATION
-- =============================================================================

-- Add constraints to ensure data integrity
-- Note: We keep the original string columns for backward compatibility during migration
-- The application can choose to use either the string column or the reference

-- =============================================================================
-- COMMENTS FOR DOCUMENTATION
-- =============================================================================

COMMENT ON TABLE transaction_types IS 'Lookup table for transaction record types (manual_input, rewards, iot)';
COMMENT ON COLUMN transaction_types.code IS 'Unique code used in application logic';
COMMENT ON COLUMN transaction_types.name_en IS 'Display name in English';
COMMENT ON COLUMN transaction_types.name_th IS 'Display name in Thai';
COMMENT ON COLUMN transaction_types.is_system_default IS 'Whether this is a system-defined type';

COMMENT ON TABLE transaction_methods IS 'Lookup table for transaction methods (origin, transport, transform)';
COMMENT ON COLUMN transaction_methods.code IS 'Unique code used in application logic';
COMMENT ON COLUMN transaction_methods.name_en IS 'Display name in English';
COMMENT ON COLUMN transaction_methods.name_th IS 'Display name in Thai';
COMMENT ON COLUMN transaction_methods.is_system_default IS 'Whether this is a system-defined method';

COMMENT ON COLUMN transaction_records.transaction_type_id IS 'Foreign key reference to transaction_types table';
COMMENT ON COLUMN transactions.transaction_method_id IS 'Foreign key reference to transaction_methods table';

-- =============================================================================
-- BACKUP AND SAFETY NOTES
-- =============================================================================

-- This migration adds new lookup tables and foreign key references
-- Original string columns are preserved for backward compatibility
-- No existing data is lost or modified destructively

-- =============================================================================
-- ROLLBACK INSTRUCTIONS
-- =============================================================================

-- To rollback this migration:
-- 1. ALTER TABLE transaction_records DROP COLUMN IF EXISTS transaction_type_id;
-- 2. ALTER TABLE transactions DROP COLUMN IF EXISTS transaction_method_id;
-- 3. DROP TABLE IF EXISTS transaction_methods;
-- 4. DROP TABLE IF EXISTS transaction_types;

COMMIT;

-- =============================================================================
-- MIGRATION COMPLETED
-- =============================================================================
-- Tables created: transaction_types, transaction_methods
-- Columns added: transaction_records.transaction_type_id, transactions.transaction_method_id
-- Data migrated: Existing string values mapped to new reference IDs
-- Indexes created: Performance indexes for all new tables and columns
-- Status: READY FOR TESTING
-- =============================================================================