-- Per-hardware tags (physical-tablet level). Mirrors the existing
-- `iot_devices.tags` column added in migration 049, but lives on
-- `iot_hardwares` because tags here describe the *device itself*
-- (location, pilot batch, hardware revision) rather than the logical
-- iot_device pairing — so tags follow the tablet across re-pairings.
--
-- Normalised server-side: trim + lowercase + dedupe, cap 20 tags per
-- hardware, each tag ≤ 64 chars. The admin endpoint enforces this.

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;

-- GIN index for tag-filter queries (e.g. WHERE tags ?| ARRAY['pilot-a']).
-- Index name follows the same convention as the iot_devices.tags index.
CREATE INDEX IF NOT EXISTS idx_iot_hardwares_tags
    ON iot_hardwares USING GIN (tags);
