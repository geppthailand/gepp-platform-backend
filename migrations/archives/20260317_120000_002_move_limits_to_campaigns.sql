-- Migration: Move points_per_transaction_limit and points_per_day_limit from reward_setup to reward_campaigns
-- Date: 2026-03-17
-- Reason: Allow per-campaign limit configuration instead of global org-level

-- Step 1: Add columns to reward_campaigns (nullable — NULL means no limit)
ALTER TABLE reward_campaigns
    ADD COLUMN IF NOT EXISTS points_per_transaction_limit INTEGER DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS points_per_day_limit INTEGER DEFAULT NULL;

-- Step 2: Remove columns from reward_setup
ALTER TABLE reward_setup
    DROP COLUMN IF EXISTS points_per_transaction_limit,
    DROP COLUMN IF EXISTS points_per_day_limit;
