-- Migration: Change transactions.destination_id to destination_ids array
-- Date: 2025-12-10
-- Description: Change destination_id from single BIGINT to ARRAY of BIGINTs to support multiple destinations per transaction

-- Step 1: Add new destination_ids array column
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS destination_ids BIGINT[] DEFAULT '{}';

-- Step 2: Migrate existing destination_id values to the array
UPDATE transactions
SET destination_ids = ARRAY[destination_id]
WHERE destination_id IS NOT NULL AND (destination_ids IS NULL OR destination_ids = '{}');

-- Step 3: Drop the foreign key constraint on destination_id
ALTER TABLE transactions
DROP CONSTRAINT IF EXISTS transactions_destination_id_fkey;

-- Step 4: Drop the old destination_id column
ALTER TABLE transactions
DROP COLUMN IF EXISTS destination_id;

-- Step 5: Add comment to the new column
COMMENT ON COLUMN transactions.destination_ids IS 'Array of destination user_location IDs, ordered to match transaction_records array positions';

-- Step 6: Create index for faster destination-based queries
CREATE INDEX IF NOT EXISTS idx_transactions_destination_ids ON transactions USING GIN(destination_ids);
