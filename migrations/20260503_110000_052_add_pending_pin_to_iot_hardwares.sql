-- Migration 052 — Admin-settable settings PIN, delivered to the tablet on next checkin.
-- Date: 2026-05-03
--
-- When an admin pairs a hardware to an iot_device, they may also set the
-- "settings PIN" (the PIN the on-device Settings screen uses to gate
-- destructive actions). The PIN is stored transiently here:
--
--   1. Admin POST /admin/iot-hardwares/{id}/pair  body: {iot_device_id, pin?}
--      → sets `pending_pin` on the hardware row.
--   2. Tablet's NEXT POST /iot-hardwares/checkin reads `pending_pin`
--      alongside `paired_iot_device_id`. The handler includes it in the
--      `force_login` directive AND clears the column in the same UPDATE.
--   3. Tablet stores the PIN in EncryptedSharedPreferences and the value is
--      gone from the server.
--
-- We accept the trade-off that the PIN sits in plaintext for at most one
-- 15 s checkin window. Encrypt-at-rest would push the secret-management
-- problem onto the server (KMS / per-row key) without meaningful gain
-- against an attacker who already has DB read access.

ALTER TABLE iot_hardwares
    ADD COLUMN IF NOT EXISTS pending_pin VARCHAR(32);

COMMENT ON COLUMN iot_hardwares.pending_pin IS
    'Transient settings-PIN set by admin during pair; consumed and cleared by the next /checkin response (`force_login.pin`). Plaintext on purpose — only present for ~15 s.';
