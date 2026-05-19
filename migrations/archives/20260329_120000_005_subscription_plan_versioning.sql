-- Migration: Support subscription_plan versioning (historical tracking)
-- When permissions change, a new row is inserted and the old row is deactivated.
-- Only one row per plan name can be active at a time.

-- Drop the unique constraint on name (allows multiple rows with same name for history)
ALTER TABLE subscription_plans DROP CONSTRAINT IF EXISTS subscription_plans_name_key;

-- Add partial unique index: only one active plan per name
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_plans_active_name
ON subscription_plans (name) WHERE is_active = true;
