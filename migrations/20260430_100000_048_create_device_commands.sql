-- Migration 048 — Create device_commands table
-- Date: 2026-04-30
-- Description: Admin → device command queue (force_login, navigate, restart_app, etc.).
--              Phase 1 of scale-concept.md remote-management layer.

CREATE TABLE IF NOT EXISTS device_commands (
    id            BIGSERIAL PRIMARY KEY,
    device_id     BIGINT NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    command_type  VARCHAR(48) NOT NULL,
    -- force_login | force_logout | navigate | reset_to_home | reset_input
    -- overwrite_cache | clear_storage | restart_app | ota_update | ping
    payload       JSONB,                  -- {user_id, route, key, value, ...}
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    -- pending | delivered | acked | succeeded | failed | expired
    issued_by     BIGINT NOT NULL,        -- admin user_locations.id
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at  TIMESTAMPTZ,
    acked_at      TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    result        JSONB,                  -- error message or output
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '5 minutes')
);

CREATE INDEX IF NOT EXISTS device_commands_pending
    ON device_commands(device_id, status)
    WHERE status IN ('pending','delivered');
CREATE INDEX IF NOT EXISTS device_commands_issued
    ON device_commands(issued_at DESC);

COMMENT ON TABLE device_commands IS
    'Admin-issued commands queued for IoT devices. Devices fetch pending rows on /sync, ack via /sync ack endpoint. Status FSM: pending → delivered → acked → succeeded|failed (or expired by TTL).';
