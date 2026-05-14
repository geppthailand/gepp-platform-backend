-- Add metrics_cached_at column to crm_campaigns for 5-minute metrics cache TTL.
-- Paired with existing metrics_cache JSONB column (already present in migration 033).

ALTER TABLE crm_campaigns
    ADD COLUMN IF NOT EXISTS metrics_cached_at TIMESTAMPTZ;

COMMENT ON COLUMN crm_campaigns.metrics_cached_at IS
    'Timestamp when metrics_cache was last written. Used for 5-minute TTL check in /metrics endpoint.';
