-- ============================================================================
-- Migration: Manual audit — approve / reject in batches
-- Date: 2026-10-06
-- Description:
--   One row per bulk approve / reject ("Approve All" on the Manual Audit modal, either the
--   selected rows or everything matching the list filter). The bell gets ONE notification
--   per batch (resource.audit_batch.id) instead of one per transaction, the emails become
--   one digest per recipient, and opening the notification lists exactly these transactions
--   (GET /api/transactions?audit_batch_id=<id>, still org- and member-scoped).
--   transaction_ids = the transactions this batch actually changed (skipped ones excluded).
-- Idempotent.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS transaction_audit_batches (
    id                BIGSERIAL PRIMARY KEY,
    organization_id   BIGINT       NOT NULL,
    action            VARCHAR(16)  NOT NULL CHECK (action IN ('approved', 'rejected')),
    transaction_ids   BIGINT[]     NOT NULL DEFAULT '{}',
    total             INTEGER      NOT NULL DEFAULT 0,
    -- how the set was chosen: 'selected' (ids sent by the client) or 'filter' (all matching)
    source            VARCHAR(16)  NOT NULL DEFAULT 'selected',
    filters           JSONB,
    notes             TEXT,
    created_by_id     BIGINT,
    created_date      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transaction_audit_batches_org
    ON transaction_audit_batches (organization_id, created_date DESC);

COMMIT;
