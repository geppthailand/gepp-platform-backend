-- ============================================================================
-- Migration: Split QR Input image-upload into two independent flags
-- Date: 2026-07-20
-- Description: The single `enable_upload_image` flag on user_input_channels gated BOTH
--              transaction-level photo upload AND per-material (transaction_record) photo
--              upload. Add a second flag so the two are independent:
--                • enable_upload_image             → "อัปโหลดรูปภาพทั้ง Transaction" (unchanged)
--                • enable_upload_image_per_material → "อัปโหลดรูปภาพราย Material" (new)
--              Backfill the new column from the old one so existing channels keep their
--              current behaviour (a channel that had upload ON keeps both ON) — no regression.
-- ============================================================================

ALTER TABLE user_input_channels
    ADD COLUMN IF NOT EXISTS enable_upload_image_per_material BOOLEAN NOT NULL DEFAULT FALSE;

-- No-regression backfill: existing channels with upload enabled keep per-material upload too.
UPDATE user_input_channels
    SET enable_upload_image_per_material = enable_upload_image
    WHERE enable_upload_image = TRUE;
