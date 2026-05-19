-- Migration: add 'iot_screenshot' to the file_type enum
-- Date: 2026-05-12 12:00:00
-- Description:
--   Adds a new value to the existing file_type enum so we can store
--   admin-triggered screenshot captures alongside other uploads in the
--   centralised `files` table. The capture flow:
--     1. Admin clicks "Capture screenshot" in backoffice.
--     2. Server issues a presigned POST for the upcoming file, inserts a
--        File row with status=pending + file_type=iot_screenshot +
--        related_entity_type='iot_device' + related_entity_id=device_id,
--        and queues a 'capture_screenshot' device command with the
--        presigned data in the payload.
--     3. Tablet picks the command up on /sync, snapshots the current
--        screen, multipart-POSTs the PNG directly to S3 using the
--        presigned URL, then acks the command with the file_id.
--     4. The command-ack handler flips the File row to status=uploaded.
--
-- Postgres ALTER TYPE ADD VALUE is non-transactional, so this migration
-- intentionally has no BEGIN/COMMIT wrapper. The IF NOT EXISTS guard
-- makes the statement idempotent across re-runs.

ALTER TYPE file_type ADD VALUE IF NOT EXISTS 'iot_screenshot';

DO $$
BEGIN
    RAISE NOTICE 'Migration 061: file_type enum extended with iot_screenshot';
END $$;
