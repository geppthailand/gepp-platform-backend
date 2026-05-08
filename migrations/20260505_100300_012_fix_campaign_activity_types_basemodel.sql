-- ============================================================
-- Rewards v3 — Phase 2 fix: complete BaseModel columns on
-- reward_campaign_activity_types
-- Date: 2026-05-05
--
-- Migration 010 created the join table without is_active /
-- updated_date / deleted_date which BaseModel expects. ORM was
-- writing those on INSERT (and selecting them back), causing
-- psycopg2 UndefinedColumn errors when creating an activity-based
-- campaign. Add the 3 missing columns to align with BaseModel.
-- ============================================================

ALTER TABLE reward_campaign_activity_types
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE reward_campaign_activity_types
    ADD COLUMN IF NOT EXISTS updated_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE reward_campaign_activity_types
    ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE NULL;
