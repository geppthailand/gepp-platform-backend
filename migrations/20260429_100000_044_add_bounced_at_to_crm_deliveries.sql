-- Description: Sprint 4 — Add bounced_at column to crm_campaign_deliveries
-- This column was referenced by mailchimp_handler.py:~248 (bounced_at = NOW())
-- on hard_bounce events but didn't exist, causing silent UPDATE no-ops.
-- Migration 044 adds the column and backfills existing bounced rows.

ALTER TABLE crm_campaign_deliveries
    ADD COLUMN IF NOT EXISTS bounced_at TIMESTAMPTZ NULL;

-- Backfill: any delivery already marked bounced should have bounced_at set.
-- Use updated_date as the best available approximation of when the bounce occurred.
UPDATE crm_campaign_deliveries
SET bounced_at = updated_date
WHERE status IN ('hard_bounced', 'soft_bounced')
  AND bounced_at IS NULL;

-- Optional index for queries that filter/sort by bounce time.
CREATE INDEX IF NOT EXISTS idx_crm_deliveries_bounced_at
    ON crm_campaign_deliveries (bounced_at DESC NULLS LAST)
    WHERE bounced_at IS NOT NULL;
