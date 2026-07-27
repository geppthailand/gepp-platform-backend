-- ============================================================================
-- Migration: Create import_files + transactions.import_file_id
-- Date: 2026-07-15
-- Description: Bulk data-import batches. Each row is one upload (e.g. an .xlsx of
--              waste transactions). type='transaction' for the waste-import flow.
--              preview_payload holds the extracted + fuzzy-matched, ready-to-insert
--              transactions for review; on confirm the created transactions are
--              tagged with transactions.import_file_id so an entire upload can be
--              reverted (soft-deleted) as one unit.
--              All idempotent (IF NOT EXISTS).
-- ============================================================================

-- ─── import_files ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS import_files (
    id                  BIGSERIAL     PRIMARY KEY,
    organization_id     BIGINT        NOT NULL REFERENCES organizations(id),
    -- User (users.id) who uploaded — plain id, mirrors transactions.created_by_id (no FK).
    uploaded_by_id      BIGINT        NOT NULL,
    -- What kind of import this is (e.g. 'transaction'); used to route backend processing.
    type                VARCHAR(50)   NOT NULL DEFAULT 'transaction',
    -- Uploaded file metadata + S3 location of the raw file.
    original_filename   VARCHAR(512),
    s3_key              TEXT,
    s3_bucket           VARCHAR(255),
    file_size           BIGINT,
    mime_type           VARCHAR(255),
    -- Lifecycle: uploaded → extracting → extracted → confirming → confirmed → reverted; or failed.
    status              VARCHAR(30)   NOT NULL DEFAULT 'uploaded',
    -- Extracted + matched, ready-to-insert transactions (grouped) for the review step.
    preview_payload     JSONB,
    -- Roll-up counts (rows, transactions, records, excluded) for the history list.
    summary             JSONB,
    error               TEXT,
    confirmed_date      TIMESTAMPTZ,
    reverted_date       TIMESTAMPTZ,
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    created_date        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_date        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    deleted_date        TIMESTAMPTZ
);

-- History list per org + type, newest first.
CREATE INDEX IF NOT EXISTS idx_import_files_org_type
    ON import_files (organization_id, type)
    WHERE deleted_date IS NULL;

-- ─── transactions.import_file_id ─────────────────────────────────────────────
-- Links every transaction created by an import to its batch, so a whole upload
-- can be reverted (soft-deleted) at once.
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS import_file_id BIGINT REFERENCES import_files(id);

CREATE INDEX IF NOT EXISTS idx_transactions_import_file
    ON transactions (import_file_id)
    WHERE import_file_id IS NOT NULL AND deleted_date IS NULL;
