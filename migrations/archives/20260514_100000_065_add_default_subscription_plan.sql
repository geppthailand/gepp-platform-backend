-- Default subscription plan flag
--
-- Problem: when admins edit a subscription plan, the existing convention is to
-- create a new row (with a new auto-increment id) and deactivate the old one.
-- The register flow used to ``filter_by(name='free').first()`` which could pick
-- the wrong row, and other code paths hard-coded subscription_plan_id = 1 — so
-- every newly-registered user got attached to the original, stale plan rather
-- than the currently-active one.
--
-- Fix: introduce ``is_default BOOLEAN`` on subscription_plans. Exactly one row
-- may have ``is_default = true`` at any time, enforced via a partial unique
-- index. Register and other "no plan specified yet" flows pick that row.
--
-- Idempotent: re-running this migration is safe.

-- ─── 1. Add column with default false ─────────────────────────────────────────
ALTER TABLE subscription_plans
    ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

-- ─── 2. Backfill: pick a current default if none exists yet ──────────────────
-- Preference order:
--   a) the currently-active 'free' plan (most-recently created), else
--   b) the most-recently created active plan of any name, else
--   c) the plan with the smallest id (fallback for orgs with no active rows).
DO $$
DECLARE
    target_id BIGINT;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM subscription_plans WHERE is_default = TRUE) THEN
        SELECT id
          INTO target_id
          FROM subscription_plans
         WHERE name = 'free'
           AND is_active = TRUE
         ORDER BY created_date DESC
         LIMIT 1;

        IF target_id IS NULL THEN
            SELECT id
              INTO target_id
              FROM subscription_plans
             WHERE is_active = TRUE
             ORDER BY created_date DESC
             LIMIT 1;
        END IF;

        IF target_id IS NULL THEN
            SELECT id INTO target_id FROM subscription_plans ORDER BY id ASC LIMIT 1;
        END IF;

        IF target_id IS NOT NULL THEN
            UPDATE subscription_plans SET is_default = TRUE WHERE id = target_id;
        END IF;
    END IF;
END $$;

-- ─── 3. Enforce "at most one default" via a partial unique index ──────────────
-- A normal UNIQUE on the column would force every row to a distinct boolean
-- (only two rows possible). The partial index instead permits any number of
-- false rows while allowing only one true row.
CREATE UNIQUE INDEX IF NOT EXISTS subscription_plans_single_default
    ON subscription_plans (is_default)
    WHERE is_default = TRUE;
