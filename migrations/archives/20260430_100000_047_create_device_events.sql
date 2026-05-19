-- Migration 047 — Create device_events table
-- Date: 2026-04-30
-- Description: Append-only IoT device action trail (nav/click/input/error/login/logout/command_executed).
--              Phase 1 of scale-concept.md remote-management layer.
-- Retention: scheduled job deletes rows older than 30 days (separate task, out of scope for v1).

CREATE TABLE IF NOT EXISTS device_events (
    id          BIGSERIAL PRIMARY KEY,
    device_id   BIGINT NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type  VARCHAR(48) NOT NULL,  -- nav | click | input | error | login | logout | command_executed
    route       VARCHAR(128),
    payload     JSONB,                  -- {target: 'input1', value: 'xyz'} etc.
    user_id     BIGINT,
    session_id  VARCHAR(64)             -- groups events between login/logout
);

CREATE INDEX IF NOT EXISTS device_events_device_time ON device_events(device_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS device_events_session ON device_events(device_id, session_id);

COMMENT ON TABLE device_events IS
    'Append-only audit trail for IoT devices — captures user navigation, clicks, inputs, errors and command executions. Source for /api/admin/iot-devices/{id}/events.';
