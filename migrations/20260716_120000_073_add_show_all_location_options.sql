-- ============================================================================
-- Migration: Add show_all_location_options flag to organization_setup
-- Date: 2026-07-16
-- Description: Boolean "แสดงตัวเลือกสถานที่ทั้งหมด" toggle (General Settings). When true
--              (default), the create-transaction location dropdown also lists each location
--              as a PLAIN row (no tag/tenant) alongside its tag/tenant combos. When false,
--              a location that has tags/tenants shows only the combo rows.
--              Defaults TRUE so existing orgs keep seeing the plain option.
-- ============================================================================

ALTER TABLE organization_setup
    ADD COLUMN IF NOT EXISTS show_all_location_options BOOLEAN NOT NULL DEFAULT TRUE;
