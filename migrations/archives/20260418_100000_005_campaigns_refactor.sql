-- ============================================================
-- B2B2C Rewards System — Campaigns Tab Refactor
-- Date: 2026-04-18
-- Purpose:
--   1. Add target_participants + budget_baht to reward_campaigns
--   2. Migrate existing 'inactive' status → 'archived' (lifecycle expansion)
--   3. Create reward_campaign_targets table (per-material weight goals)
-- ============================================================

-- 1. New columns on reward_campaigns
ALTER TABLE reward_campaigns
    ADD COLUMN IF NOT EXISTS target_participants INTEGER,
    ADD COLUMN IF NOT EXISTS budget_baht DECIMAL(12,2);

-- 2. Lifecycle: existing 'inactive' → 'archived' (preserve data, hidden by default)
--    New valid states: draft / active / paused / ended (computed) / archived
UPDATE reward_campaigns
   SET status = 'archived'
 WHERE status = 'inactive';

-- 3. New table: reward_campaign_targets
CREATE TABLE IF NOT EXISTS reward_campaign_targets (
    id BIGSERIAL PRIMARY KEY,
    reward_campaign_id BIGINT NOT NULL REFERENCES reward_campaigns(id),
    target_level VARCHAR(10) NOT NULL CHECK (target_level IN ('main', 'sub')),
    main_material_id BIGINT REFERENCES main_materials(id),
    material_id BIGINT REFERENCES materials(id),
    target_weight_kg DECIMAL(12,2) NOT NULL,
    created_date TIMESTAMPTZ DEFAULT NOW(),
    updated_date TIMESTAMPTZ DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    -- main XOR sub: exactly one of the two material FKs must be set
    CHECK (
      (target_level = 'main' AND main_material_id IS NOT NULL AND material_id IS NULL) OR
      (target_level = 'sub'  AND material_id IS NOT NULL AND main_material_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_reward_campaign_targets_campaign
    ON reward_campaign_targets(reward_campaign_id);
