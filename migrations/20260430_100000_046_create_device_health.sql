-- Migration 046 — Create device_health table
-- Date: 2026-04-30
-- Description: Single-row-per-device realtime health snapshot, upserted on heartbeat.
--              Belongs to the IoT remote-management layer (Phase 1 of scale-concept.md).

-- NOTE on `online`: NOT a stored column. Postgres GENERATED ALWAYS AS ... STORED
-- requires an IMMUTABLE expression, but NOW() is STABLE. A stored generated value
-- would also be wrong semantically — it would only refresh on row writes, so an
-- offline device would keep online=true until the next heartbeat. Instead, the
-- backend computes online at SELECT time:
--   SELECT (last_seen_at > NOW() - INTERVAL '30 seconds') AS online ...
CREATE TABLE IF NOT EXISTS device_health (
    device_id        BIGINT PRIMARY KEY REFERENCES iot_devices(id) ON DELETE CASCADE,
    last_seen_at     TIMESTAMPTZ NOT NULL,
    -- hardware
    battery_level    INT,            -- 0–100
    battery_charging BOOLEAN,
    cpu_temp_c       NUMERIC(5,2),
    network_type     VARCHAR(16),    -- wifi | cellular | ethernet | none
    network_strength INT,            -- 0–100 (RSSI normalized)
    ip_address       VARCHAR(64),
    storage_free_mb  INT,
    ram_free_mb      INT,
    os_version       VARCHAR(64),
    app_version      VARCHAR(32),
    -- app
    current_route        VARCHAR(128),  -- /data-entry, /login, etc.
    current_user_id      BIGINT,        -- FK user_locations.id (logged-in admin)
    current_org_id       BIGINT,        -- FK organizations.id
    current_location_id  BIGINT,        -- FK user_locations.id
    scale_connected      BOOLEAN,
    scale_mac_bt         VARCHAR(64),
    cache_summary        JSONB,         -- {materials_count, pending_records, ...}
    raw                  JSONB          -- full last heartbeat for debugging
);

CREATE INDEX IF NOT EXISTS device_health_org ON device_health(current_org_id);
CREATE INDEX IF NOT EXISTS device_health_seen ON device_health(last_seen_at DESC);

COMMENT ON TABLE device_health IS
    'One row per IoT device — latest health snapshot, upserted on each /sync heartbeat. The "online" status is NOT stored: compute it as (last_seen_at > NOW() - INTERVAL ''30 seconds'') in SELECTs.';
