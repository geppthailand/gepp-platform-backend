-- Migration: Add qr_input and scale_input to transaction_method check constraint
-- Date: 2026-01-12
-- Description: Extend the transaction_method constraint to allow qr_input and scale_input values

-- Drop existing constraints (there may be two with different names)
ALTER TABLE transactions
DROP CONSTRAINT IF EXISTS chk_transaction_method;

ALTER TABLE transactions
DROP CONSTRAINT IF EXISTS transactions_transaction_method_check;

-- Add the updated constraint with new values
ALTER TABLE transactions
ADD CONSTRAINT chk_transaction_method
CHECK (transaction_method IN ('origin', 'transport', 'transform', 'qr_input', 'scale_input'));
