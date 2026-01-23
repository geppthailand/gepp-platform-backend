-- Migration: Add transaction_date column to transaction_records table
-- Date: 2025-10-22
-- Description: Add transaction_date column to allow individual transaction dates per record

-- Add transaction_date column to transaction_records
ALTER TABLE transaction_records
ADD COLUMN transaction_date TIMESTAMP WITH TIME ZONE;

-- Add comment to the column
COMMENT ON COLUMN transaction_records.transaction_date IS 'Date of the transaction record (can be different from transaction created_date)';

-- Create index for faster date-based queries
CREATE INDEX idx_transaction_records_transaction_date ON transaction_records(transaction_date);

-- Set default value for existing records (use created_date as fallback)
UPDATE transaction_records
SET transaction_date = created_date
WHERE transaction_date IS NULL;
