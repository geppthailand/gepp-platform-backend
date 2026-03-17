-- Add absolute_percentage column to traceability_transport_transactions
-- This stores the percentage of each node's weight relative to its siblings' total weight at the same tree level.
-- Recalculated on every create/update/revert operation via _recalculate_absolute_percentage().
-- Used by reports for fast percentage lookups without needing to traverse the tree.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'traceability_transport_transactions'
          AND column_name = 'absolute_percentage'
    ) THEN
        ALTER TABLE traceability_transport_transactions
        ADD COLUMN absolute_percentage DECIMAL DEFAULT NULL;
    END IF;
END $$;
