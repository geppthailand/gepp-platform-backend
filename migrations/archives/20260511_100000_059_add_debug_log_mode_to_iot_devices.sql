-- Debug-log mode toggle + log-capture table.
--
-- Active-flag storage: `iot_device_health.raw -> 'debug_log_until'`
-- (UTC ISO-8601 string). Same JSONB pattern as `admin_watching_until`.
-- No DDL needed for the flag itself — `iot_device_health.raw` already
-- exists as JSONB. Admin toggle writes the timestamp; sync handler
-- compares to NOW() to decide if the mode is active. Auto-off is
-- implicit (no cron, no expiry job).
--
-- This migration only creates the capture table.

CREATE TABLE IF NOT EXISTS iot_debug_logs (
    id BIGSERIAL PRIMARY KEY,
    iot_device_id BIGINT NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    captured_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    level VARCHAR(16) NOT NULL,
    tag VARCHAR(64) NULL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_iot_debug_logs_device_at
    ON iot_debug_logs (iot_device_id, captured_at DESC);

-- Daily-rollover cleanup will trim `received_at < NOW() - INTERVAL '7 days'`
-- in the existing iot_devices_handlers._run_daily_log_cleanup pass.
