-- Migration 049 — Add tags + maintenance metadata to iot_devices
-- Date: 2026-05-03
-- Description: Operational labels (tags) for filtering / cohort analysis,
--              independent of organization assignment. Plus a maintenance
--              mode boolean used by the backoffice to suppress alerts and
--              by the device app (future) to show a maintenance banner.
--
-- Rationale: tags answer "find me all firmware-v2 devices in pilot group A"
-- without requiring a separate cohort table. Maintenance mode lets ops mute
-- known-disconnected devices during scheduled hardware swaps so the alerts
-- panel doesn't drown the rest of the fleet.

ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS maintenance_mode BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS maintenance_reason TEXT;

ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS maintenance_until TIMESTAMPTZ;

-- Index supports `WHERE tags @> '["pilot-group-a"]'::jsonb` filters from
-- the admin list endpoint.
CREATE INDEX IF NOT EXISTS iot_devices_tags_gin
    ON iot_devices USING GIN (tags);

-- Index supports `WHERE maintenance_mode = TRUE` filtering for the
-- "show only maintenance devices" admin view.
CREATE INDEX IF NOT EXISTS iot_devices_maintenance_mode
    ON iot_devices(maintenance_mode)
    WHERE maintenance_mode = TRUE;

COMMENT ON COLUMN iot_devices.tags IS
    'Operational labels (string array) — e.g. ["pilot-group-a","firmware-v2"]. Independent of organization. Filtered with @> operator.';
COMMENT ON COLUMN iot_devices.maintenance_mode IS
    'When TRUE, device is suppressed from alerts panel and proactive notifications.';
COMMENT ON COLUMN iot_devices.maintenance_until IS
    'Optional auto-clear timestamp; backend cron flips maintenance_mode=FALSE when NOW() > maintenance_until.';
