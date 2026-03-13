-- Add reverse pointer from transaction_records to traceability_transaction_group
-- This enables efficient lookup of which traceability group a record belongs to,
-- used by the 3-tier recycling rate calculation in reports.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'transaction_records'
          AND column_name = 'traceability_group_id'
    ) THEN
        ALTER TABLE transaction_records
        ADD COLUMN traceability_group_id BIGINT DEFAULT NULL
        REFERENCES traceability_transaction_group(id);
    END IF;
END $$;
