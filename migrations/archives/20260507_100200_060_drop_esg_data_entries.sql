-- ============================================================
-- Drop esg_data_entries — replaced by esg_records
-- ============================================================
-- The legacy datapoint-row storage is retired. All ESG read/write
-- paths now go through `esg_records` (one row per atomic record,
-- datapoints stored as JSONB). Two empty tables had nullable FKs
-- back to esg_data_entries; we repoint them to esg_records.id.
-- ============================================================

-- 1. Two dependent tables — empty in dev/prod — have nullable FKs
--    pointing at esg_data_entries.id. Drop those constraints and
--    repoint to esg_records (rename column for clarity, idempotent).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'esg_scope3_entries'
    ) THEN
        ALTER TABLE esg_scope3_entries
            DROP CONSTRAINT IF EXISTS esg_scope3_entries_data_entry_id_fkey;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'esg_scope3_entries' AND column_name = 'data_entry_id'
        ) AND NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'esg_scope3_entries' AND column_name = 'record_id'
        ) THEN
            ALTER TABLE esg_scope3_entries RENAME COLUMN data_entry_id TO record_id;
        END IF;
        ALTER TABLE esg_scope3_entries
            ADD CONSTRAINT esg_scope3_entries_record_id_fkey
            FOREIGN KEY (record_id) REFERENCES esg_records(id) ON DELETE SET NULL;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'esg_xbrl_report_values'
    ) THEN
        ALTER TABLE esg_xbrl_report_values
            DROP CONSTRAINT IF EXISTS esg_xbrl_report_values_data_entry_id_fkey;
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'esg_xbrl_report_values' AND column_name = 'data_entry_id'
        ) AND NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'esg_xbrl_report_values' AND column_name = 'record_id'
        ) THEN
            ALTER TABLE esg_xbrl_report_values RENAME COLUMN data_entry_id TO record_id;
        END IF;
        ALTER TABLE esg_xbrl_report_values
            ADD CONSTRAINT esg_xbrl_report_values_record_id_fkey
            FOREIGN KEY (record_id) REFERENCES esg_records(id) ON DELETE SET NULL;
    END IF;
END $$;

-- 2. Drop the table.
DROP TABLE IF EXISTS esg_data_entries CASCADE;
