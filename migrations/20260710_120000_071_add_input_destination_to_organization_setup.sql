-- ============================================================================
-- Migration: Add input_destination flag to organization_setup
-- Date: 2026-07-10
-- Description: Boolean "กรอกปลายทาง" toggle (General Settings). When true, the
--              create-transaction modal requires a destination per record and the
--              traceability first hop is auto-created on transaction create.
-- ============================================================================

ALTER TABLE organization_setup
    ADD COLUMN IF NOT EXISTS input_destination BOOLEAN NOT NULL DEFAULT FALSE;
