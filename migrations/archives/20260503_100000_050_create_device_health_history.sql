-- Migration 050 — Aggregated history of device_health (5-min buckets)
-- Date: 2026-05-03
-- Description: One row per device per 5-min bucket, written by a periodic
--              snapshot worker (or by ops calling
--              `POST /admin/iot-devices/snapshot-aggregate`).
--
-- Drives:
--   * 24h fleet "online %" trend chart on the admin dashboard
--   * 24h per-device sparklines (battery, network) extending the
--     client-buffered 3-minute strip already shipped in the show.tsx
--     Status tab.
--
-- Retention: rows older than 7 days deleted by the same worker (or via a
-- separate cleanup job). 7 d × 24 h × 12 buckets/h × ~100 devices ≈ 200k
-- rows — comfortably small.

CREATE TABLE IF NOT EXISTS device_health_history (
    device_id    BIGINT NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    bucket_start TIMESTAMPTZ NOT NULL,
    online       BOOLEAN NOT NULL,
    battery_level    INT,
    battery_charging BOOLEAN,
    network_type     VARCHAR(16),
    network_strength INT,
    last_seen_at TIMESTAMPTZ,
    PRIMARY KEY (device_id, bucket_start)
);

-- Drives `WHERE bucket_start >= NOW() - INTERVAL '24 hours' GROUP BY bucket_start`
-- queries used by the fleet-wide online% chart.
CREATE INDEX IF NOT EXISTS device_health_history_bucket
    ON device_health_history (bucket_start DESC);

COMMENT ON TABLE device_health_history IS
    'Aggregated 5-min snapshots of device_health for trend charts. One row per device per bucket. PK guards against double-writes when a worker retries. Retention 7 days.';
