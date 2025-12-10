-- Migration: Add destination_id column to transaction_records table
-- Date: 2025-12-10
-- Description: Add destination_id column to store the destination location for each transaction record

-- Add destination_id column to transaction_records
ALTER TABLE transaction_records
ADD COLUMN IF NOT EXISTS destination_id BIGINT REFERENCES user_locations(id);

-- Add comment to the column
COMMENT ON COLUMN transaction_records.destination_id IS 'Reference to the destination user_location for this transaction record';

-- Create index for faster destination-based queries
CREATE INDEX IF NOT EXISTS idx_transaction_records_destination_id ON transaction_records(destination_id);
