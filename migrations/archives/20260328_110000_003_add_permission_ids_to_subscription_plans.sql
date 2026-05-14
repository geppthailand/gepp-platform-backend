-- Add permission_ids JSONB column to subscription_plans
-- Stores an array of system_permission IDs for each plan, e.g. [1, 2, 5, 8]
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS permission_ids JSONB NOT NULL DEFAULT '[]';
