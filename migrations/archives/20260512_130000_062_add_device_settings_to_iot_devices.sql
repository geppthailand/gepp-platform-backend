-- Migration: add device_settings JSONB column on iot_devices
-- Date: 2026-05-12 13:00:00
-- Description:
--   Stores per-device runtime tunables that admins can flip from the
--   backoffice without having to redeploy the tablet APK. The tablet
--   reads this object out of every /sync response and writes it into
--   the existing SharedPreferences keys, so all on-device call sites
--   keep working unchanged.
--
-- Schema:
--   {
--     "login_methods": { "qr": true, "user_id": true, "pin": true },
--     "require_photo_on_save": true,
--     "show_user_manual": true,
--     "font_scale": 1.0
--   }
--
-- Validation lives at the admin-write endpoint, not the column —
-- JSONB lets us add fields later without another migration. NULL is
-- treated as "use the tablet's local defaults".

ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS device_settings JSONB;

COMMENT ON COLUMN iot_devices.device_settings IS
    'Per-device runtime settings pushed to the tablet on every /sync. '
    'Keys: login_methods{qr,user_id,pin}, require_photo_on_save, '
    'show_user_manual, font_scale (0.85–1.5).';

DO $$
BEGIN
    RAISE NOTICE 'Migration 062: iot_devices.device_settings JSONB added';
END $$;
