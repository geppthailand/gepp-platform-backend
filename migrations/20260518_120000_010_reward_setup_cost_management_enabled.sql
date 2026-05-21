-- ============================================================
-- B2B2C Rewards System — Cost Management feature toggle
-- Date: 2026-05-18
-- Purpose:
--   Add org-level boolean to gate the "บัญชี & ต้นทุน" feature. When OFF, all cost-related
--   UI (deposit unit_price, receipt upload, KPI baht subtexts, campaign budget + rate
--   inputs, the new top-level "บัญชี & ต้นทุน" tab) is hidden. Data is not deleted —
--   flipping back ON restores the full UI with all historical data intact.
-- ============================================================

BEGIN;

ALTER TABLE reward_setup
    ADD COLUMN IF NOT EXISTS cost_management_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN reward_setup.cost_management_enabled IS
    'Master toggle for the cost-management feature surface. OFF (default) hides all cost UI.';

COMMIT;
