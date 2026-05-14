-- ============================================================
-- Rewards v3 — Phase 2: Campaign Metric Type discriminator
-- Date: 2026-05-05
-- Purpose: Campaigns can now be either Material-based (kg) or Activity-based (count).
--          Existing campaigns default to 'material' to preserve current behavior.
-- ============================================================

ALTER TABLE reward_campaigns
    ADD COLUMN IF NOT EXISTS metric_type VARCHAR(20) NOT NULL DEFAULT 'material';

-- Backfill all existing rows (in case they bypassed the default at insert time)
UPDATE reward_campaigns SET metric_type = 'material' WHERE metric_type IS NULL;

-- Add CHECK constraint (idempotent — drop+add)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'reward_campaigns_metric_type_check'
  ) THEN
    ALTER TABLE reward_campaigns DROP CONSTRAINT reward_campaigns_metric_type_check;
  END IF;
END $$;

ALTER TABLE reward_campaigns
    ADD CONSTRAINT reward_campaigns_metric_type_check
        CHECK (metric_type IN ('material', 'activity'));

COMMENT ON COLUMN reward_campaigns.metric_type IS
    'Campaign measurement type: material=weight in kg, activity=count of occurrences';
