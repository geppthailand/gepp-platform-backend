-- Migration: Rename transaction_group_id to transaction_carried_over in traceability_transaction_group
-- Date: 2025-03-02
-- Description: Rename column keeping same data type (BIGINT[])

-- Rename the column (data type is unchanged)
ALTER TABLE traceability_transaction_group
RENAME COLUMN transaction_group_id TO transaction_carried_over;

-- Drop the old index (it was named after the column)
DROP INDEX IF EXISTS idx_traceability_transaction_group_transaction_group_id;

-- Create index for the renamed column
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_transaction_carried_over ON traceability_transaction_group USING GIN(transaction_carried_over);

-- Update comment
COMMENT ON COLUMN traceability_transaction_group.transaction_carried_over IS 'List of traceability_transaction_group ids (nested groups / carried over)';
