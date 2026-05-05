-- Migration 054 — Per-tablet GPS location reporting
-- Date: 2026-05-05
--
-- Tablets opportunistically report their GPS coords (COARSE accuracy is
-- enough — these are stationary scale stations) every full heartbeat
-- cycle. The backend stores the latest fix on the iot_hardwares row, so
-- the location follows the *physical* tablet across iot_devices logins
-- (rather than per-iot_devices login). This drives the new "Map" tab
-- on /v3-iot-devices which plots the fleet with marker-cluster grouping.
--
-- Why on iot_hardwares (not iot_devices):
--   * The tablet is the thing that has a physical location.
--   * If admin re-pairs hardware → new iot_devices login, the location
--     stays correct because hardware row didn't move.
--   * `last_location_at` lets the UI mark stale fixes (e.g. > 24 h old).

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS last_lng DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS last_location_accuracy_m DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS last_location_at TIMESTAMPTZ;

-- Partial index for efficient bbox queries on the Map tab.
CREATE INDEX IF NOT EXISTS iot_hardwares_location
    ON iot_hardwares (last_lat, last_lng)
    WHERE last_lat IS NOT NULL;

COMMENT ON COLUMN iot_hardwares.last_lat IS 'WGS-84 latitude of the most recent /sync that included GPS. Null if tablet hasn''t reported / permission denied.';
COMMENT ON COLUMN iot_hardwares.last_lng IS 'WGS-84 longitude.';
COMMENT ON COLUMN iot_hardwares.last_location_accuracy_m IS 'Reported accuracy radius in meters (Geolocator/Android estimate). Lower = more confident.';
COMMENT ON COLUMN iot_hardwares.last_location_at IS 'Server-side timestamp the location was received. UI greys-out fixes older than 24 h.';
