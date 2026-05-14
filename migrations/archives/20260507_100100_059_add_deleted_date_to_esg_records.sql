-- ============================================================
-- Add `deleted_date` to esg_records
-- ============================================================
-- The base SQLAlchemy model (BaseModel) declares a `deleted_date`
-- column on every model for soft-delete bookkeeping. The table
-- created in migration 058 missed it, so the first INSERT from
-- prod failed with `column "deleted_date" does not exist`.
-- ============================================================

ALTER TABLE esg_records
    ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMPTZ;
