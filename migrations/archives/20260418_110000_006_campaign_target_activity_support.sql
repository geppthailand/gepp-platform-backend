-- ============================================================
-- B2B2C Rewards System — Campaign Target: Activity Material support
-- Date: 2026-04-18
-- Purpose: Targets can now point at RewardActivityMaterial directly (org-scoped),
--          and support both kg (material type) and times (activity type) units.
--
-- Schema changes vs migration 005:
--   1. Rename `target_weight_kg` → `target_amount` (more generic)
--   2. Add `target_unit` ('kg' | 'times', default 'kg')
--   3. Add `activity_material_id` FK (replaces obsolete `material_id`)
--   4. Drop `material_id` column (no longer used — targets use activity_material_id instead)
--   5. Update target_level enum: 'sub' → 'activity_material'
--   6. Replace XOR CHECK constraint to reflect new shape
-- ============================================================

-- 1. Rename target_weight_kg → target_amount (only if old name still exists)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='reward_campaign_targets' AND column_name='target_weight_kg'
  ) THEN
    ALTER TABLE reward_campaign_targets RENAME COLUMN target_weight_kg TO target_amount;
  END IF;
END $$;

-- 2. Add target_unit
ALTER TABLE reward_campaign_targets
    ADD COLUMN IF NOT EXISTS target_unit VARCHAR(10) NOT NULL DEFAULT 'kg';

-- 3. Add activity_material_id FK
ALTER TABLE reward_campaign_targets
    ADD COLUMN IF NOT EXISTS activity_material_id BIGINT
        REFERENCES reward_activity_materials(id);

CREATE INDEX IF NOT EXISTS idx_reward_campaign_targets_activity_material
    ON reward_campaign_targets(activity_material_id);

-- 4a. Widen target_level column (was VARCHAR(10) — 'activity_material' is 17 chars)
ALTER TABLE reward_campaign_targets
    ALTER COLUMN target_level TYPE VARCHAR(20);

-- 4b. Migrate any existing 'sub' rows to use activity_material_id (if there were any).
--     Old 'sub' rows used material_id; we don't migrate those (no production data yet).
--     Just relabel the enum.
UPDATE reward_campaign_targets SET target_level = 'activity_material'
 WHERE target_level = 'sub';

-- 5. Drop old XOR CHECK constraint (it referenced material_id + 'sub')
DO $$
DECLARE
    cname TEXT;
BEGIN
    -- Find any check constraint on this table that references material_id or 'sub'
    FOR cname IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'reward_campaign_targets'::regclass
          AND contype = 'c'
    LOOP
        EXECUTE format('ALTER TABLE reward_campaign_targets DROP CONSTRAINT %I', cname);
    END LOOP;
END $$;

-- 6. Drop now-unused material_id column (and its FK)
ALTER TABLE reward_campaign_targets
    DROP COLUMN IF EXISTS material_id;

-- 7. Add fresh CHECK constraints
ALTER TABLE reward_campaign_targets
    ADD CONSTRAINT reward_campaign_targets_level_check
        CHECK (target_level IN ('main', 'activity_material'));

ALTER TABLE reward_campaign_targets
    ADD CONSTRAINT reward_campaign_targets_unit_check
        CHECK (target_unit IN ('kg', 'times'));

ALTER TABLE reward_campaign_targets
    ADD CONSTRAINT reward_campaign_targets_xor_check
        CHECK (
          (target_level = 'main' AND main_material_id IS NOT NULL AND activity_material_id IS NULL) OR
          (target_level = 'activity_material' AND activity_material_id IS NOT NULL AND main_material_id IS NULL)
        );
