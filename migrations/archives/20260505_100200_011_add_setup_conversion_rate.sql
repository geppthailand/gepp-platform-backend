-- ============================================================
-- Rewards v3 — Phase 2: Org-level points → baht conversion rate
-- Date: 2026-05-05
-- Purpose: Powers Cost Report ROI/profit calculations. 1 point = X baht.
--          NOTE: reward_setup already has cost_per_point (DECIMAL(10,4))
--          which conceptually serves the same role. We rename it to
--          point_to_baht_rate for clarity and align with the new UI.
-- ============================================================

-- Add the new column if it doesn't already exist
ALTER TABLE reward_setup
    ADD COLUMN IF NOT EXISTS point_to_baht_rate DECIMAL(10, 4) NULL;

-- Backfill from cost_per_point (only when new column is null and old has a value)
UPDATE reward_setup
SET point_to_baht_rate = cost_per_point
WHERE point_to_baht_rate IS NULL
  AND cost_per_point IS NOT NULL;

-- Default to 0.50 for any rows still null
UPDATE reward_setup
SET point_to_baht_rate = 0.50
WHERE point_to_baht_rate IS NULL;

-- NOTE: cost_per_point is intentionally kept for backward compat with anything
-- that still reads it. The Setup service writes both columns going forward.

COMMENT ON COLUMN reward_setup.point_to_baht_rate IS
    'Org-level conversion rate: 1 point = X baht. Used for Cost Report ROI/profit.';
