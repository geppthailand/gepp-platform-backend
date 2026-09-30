-- Migration 092 — scale serial number + per-device document library
-- Date: 2026-09-30
--
-- Two asks from ops, one migration, because they are the same job: the people
-- who service a weighing scale need the paperwork that came with it attached to
-- the device record, not in a shared drive nobody can find from the backoffice.
--
--   1. `iot_devices.serial_number` — the number stamped on the SCALE itself.
--   2. A place to keep photos of its settings screen / nameplate sticker, plus
--      calibration certificates, manuals and warranty paperwork (pdf/xlsx/docx).
--
-- ── Why only ONE new column ────────────────────────────────────────────────
--
-- The documents need NO new table. `files` already carries
-- `related_entity_type` + `related_entity_id` (with `idx_files_related_entity`
-- over exactly that pair), and the IoT screenshots feature already writes
-- `related_entity_type='iot_device'` rows — 50 of them today. A parallel
-- `iot_device_documents` table would mean two answers to "what files does this
-- device have?", two S3 lifecycles and two delete paths to keep in step.
--
-- So a device document is:
--     files.related_entity_type = 'iot_device'
--     files.related_entity_id   = <iot_devices.id>
--     files.file_type           = 'document'      (screenshots use 'iot_screenshot')
--
-- `file_type='document'` already exists in the enum, so there is no ALTER TYPE
-- here either — and `file_type` alone keeps the Documents tab and the
-- Screenshots tab from ever showing each other's rows.
--
-- The per-document category (settings photo / nameplate / calibration / manual
-- / warranty / other) and the admin's note live in `files.metadata`, which is
-- JSONB and already defaulted. Categories are a presentation concern that ops
-- will want to rename and extend; a column or a CHECK constraint would make
-- each of those a migration.
--
-- ── Why serial_number is NOT on iot_hardwares ──────────────────────────────
--
-- `iot_hardwares.serial_number` already exists and is the TABLET's serial. The
-- scale is a different physical object with its own plate, and a tablet gets
-- swapped or re-paired without the scale changing. Putting both on one row
-- would silently overwrite one when the other is replaced.
--
-- Nullable, and deliberately NOT unique: these are typed in from a sticker that
-- is often scratched or partly painted over, duplicates and typos happen, and a
-- unique index would block saving the rest of a device's details over a field
-- nobody can verify from a desk. `iot_hardwares.serial_number` made the same
-- call.

BEGIN;

ALTER TABLE iot_devices
    ADD COLUMN IF NOT EXISTS serial_number VARCHAR(128);

COMMENT ON COLUMN iot_devices.serial_number IS
    'Serial number printed on the SCALE itself. Not the tablet — that is '
    'iot_hardwares.serial_number. Free text: transcribed from a physical '
    'plate, so not unique and not validated.';

-- Indexed because a serial read off a machine in the field is how a device gets
-- identified when nobody knows its id — today from a direct query, and from the
-- device-list filter when one is added. Partial: most rows will be NULL for a
-- long time and there is no reason to index those.
CREATE INDEX IF NOT EXISTS idx_iot_devices_serial_number
    ON iot_devices (serial_number)
    WHERE serial_number IS NOT NULL;

-- The Documents tab lists one device's documents, newest first. The existing
-- `idx_files_related_entity` covers (related_entity_type, related_entity_id)
-- but not file_type, so every listing would also walk that device's
-- screenshots. Few rows per device today, but screenshots accumulate on their
-- own schedule and this keeps the tab's cost independent of them.
CREATE INDEX IF NOT EXISTS idx_files_iot_device_documents
    ON files (related_entity_id, created_date DESC)
    WHERE related_entity_type = 'iot_device'
      AND file_type = 'document'
      AND is_active = TRUE;

COMMIT;
