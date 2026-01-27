-- Migration: Fix transaction_method check constraint to allow qr_input and scale_input
-- Date: 2026-01-12
-- Description: Drop all existing transaction_method constraints and recreate with new values

-- Drop all possible constraint names
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_method;
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_transaction_method_check;
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_chk_transaction_method;

-- Add the updated constraint with new values
ALTER TABLE transactions
ADD CONSTRAINT chk_transaction_method
CHECK (transaction_method IN ('origin', 'transport', 'transform', 'qr_input', 'scale_input'));
