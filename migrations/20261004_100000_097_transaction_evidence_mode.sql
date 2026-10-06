-- ============================================================================
-- Migration: Org-wide "require evidence" for manually created waste transactions
-- Date: 2026-10-04
-- Description:
--   organizations.transaction_evidence_mode
--     'none'        attachments optional (default — behaviour unchanged)
--     'transaction' at least one attachment on the transaction itself or on any record
--     'record'      every record needs its own attachment (or the transaction one covers it)
--   Enforced only on the web create path (POST /api/transactions). Scale/IoT readings,
--   GEPP Rewards claims and Excel imports are exempt. Owner-only setting.
-- Idempotent.
-- ============================================================================

BEGIN;

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS transaction_evidence_mode VARCHAR(16) NOT NULL DEFAULT 'none';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'organizations_transaction_evidence_mode_check'
    ) THEN
        ALTER TABLE organizations
            ADD CONSTRAINT organizations_transaction_evidence_mode_check
            CHECK (transaction_evidence_mode IN ('none', 'transaction', 'record'));
    END IF;
END $$;

COMMIT;
