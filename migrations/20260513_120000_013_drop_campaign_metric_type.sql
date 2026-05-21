-- ============================================================
-- Rewards v3 — Phase 4A: Drop Campaign Metric Type discriminator
-- Date: 2026-05-13
-- Purpose: Campaigns can now contain BOTH material and activity targets
--          simultaneously. The metric_type column (and the per-campaign
--          activity_type join table) are no longer needed — claims on
--          reward_activity_materials cover both kinds.
-- Reverses: 20260505_100000_009_add_campaign_metric_type.sql
--           20260505_100100_010_add_activity_types.sql (only the join table;
--           the reward_activity_types master table remains in use)
-- ============================================================

-- Drop the CHECK constraint first
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'reward_campaigns_metric_type_check'
  ) THEN
    ALTER TABLE reward_campaigns DROP CONSTRAINT reward_campaigns_metric_type_check;
  END IF;
END $$;

-- Drop the metric_type column
ALTER TABLE reward_campaigns
    DROP COLUMN IF EXISTS metric_type;

-- Drop the campaign↔activity_type join table (replaced by reward_campaign_claims)
DROP TABLE IF EXISTS reward_campaign_activity_types;
