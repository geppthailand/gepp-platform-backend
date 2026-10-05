-- ============================================================================
-- Migration: Rewards Admin tools — require a photo on member self-submitted claims
-- Date: 2026-10-04
-- Description:
--   reward_setup.self_claim_photo_required (default FALSE = photo step stays optional).
--   Only meaningful while admin_tools_enabled is on (self-claims exist only then).
-- Idempotent.
-- ============================================================================

BEGIN;

ALTER TABLE reward_setup
    ADD COLUMN IF NOT EXISTS self_claim_photo_required BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;
