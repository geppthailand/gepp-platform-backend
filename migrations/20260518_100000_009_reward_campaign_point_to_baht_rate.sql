-- ============================================================
-- B2B2C Rewards System — Per-Campaign point_to_baht_rate
-- Date: 2026-05-18
-- Purpose:
--   Move the org-wide point_to_baht_rate to per-campaign so each campaign can
--   carry its own conversion rate (used by Cost Report ROI/profit). The org-level
--   rate on reward_setup stays as a fallback for campaigns that don't set their own.
-- ============================================================

BEGIN;

ALTER TABLE reward_campaigns
    ADD COLUMN IF NOT EXISTS point_to_baht_rate DECIMAL(10, 4);

COMMENT ON COLUMN reward_campaigns.point_to_baht_rate IS
    'Per-campaign conversion rate (1 pt = X baht). NULL means fall back to reward_setup.point_to_baht_rate.';

COMMIT;
