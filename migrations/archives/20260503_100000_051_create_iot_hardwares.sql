-- Migration 051 — Physical hardware registry + iot_devices pairing
-- Date: 2026-05-03
--
-- Concept:
--   * `iot_devices` is a LOGICAL account (device_name + password) that an
--     organization owns. It can be reassigned across physical units.
--   * `iot_hardwares` is the PHYSICAL tablet (MAC, serial, model). Every
--     tablet that opens the app reports here every ~15 s — even before
--     anyone has logged in — so ops can see "what tablets are out there"
--     and pair them to an iot_devices account remotely (force-login),
--     instead of needing someone on-site to type credentials.
--
-- Pairing is many-to-one over time but exclusive at any given moment:
--   * Each iot_devices row may point to at most one current hardware
--     (`iot_devices.hardware_id`).
--   * Each iot_hardwares row may point to at most one current iot_devices
--     (`iot_hardwares.paired_iot_device_id`).
--   * Both columns are kept in sync by the pair / unpair admin endpoints.

CREATE TABLE IF NOT EXISTS iot_hardwares (
    id              BIGSERIAL PRIMARY KEY,
    -- Identity captured by the app on first checkin. MAC is the primary
    -- "is this the same physical unit?" key on Android.
    mac_address     VARCHAR(64) UNIQUE,
    serial_number   VARCHAR(128),
    device_code     VARCHAR(128),
    device_model    VARCHAR(128),
    os_version      VARCHAR(64),
    app_version     VARCHAR(32),
    -- Latest checkin metadata.
    last_checkin_at TIMESTAMPTZ,
    last_ip_address VARCHAR(64),
    -- Paired iot_devices account (NULL when un-paired).
    paired_iot_device_id BIGINT REFERENCES iot_devices(id) ON DELETE SET NULL,
    paired_at       TIMESTAMPTZ,
    paired_by       BIGINT, -- admin user_locations.id who triggered pair
    -- Soft delete + housekeeping.
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_date    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS iot_hardwares_paired_iot_device
    ON iot_hardwares(paired_iot_device_id)
    WHERE paired_iot_device_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS iot_hardwares_last_checkin
    ON iot_hardwares(last_checkin_at DESC);

COMMENT ON TABLE iot_hardwares IS
    'Physical-tablet registry. Every device that opens the IoT scale app self-reports here every ~15 s pre-login, so ops can pair-to-login remotely.';

-- Reverse pointer on iot_devices so the admin Devices list can show the
-- bound MAC + Hardware ID without an extra round-trip.
ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS hardware_id BIGINT REFERENCES iot_hardwares(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS iot_devices_hardware_id
    ON iot_devices(hardware_id)
    WHERE hardware_id IS NOT NULL;

COMMENT ON COLUMN iot_devices.hardware_id IS
    'Currently-paired physical hardware (FK iot_hardwares.id). NULL when no tablet is bound. Set/cleared by /admin/iot-hardwares/{id}/pair and /unpair.';
