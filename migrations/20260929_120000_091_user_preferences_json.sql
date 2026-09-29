-- ============================================================================
-- Migration: Per-user UI preferences (report + transaction list)
-- Date: 2026-09-29
-- Description: Adds two JSONB columns to user_locations_settings (one live row per
--              user, see migration 076):
--                report_preferences      — report mode (location/tag/tenant), overview
--                                          chart granularity, comparison mode. Read by the
--                                          Reports page AND the PDF export so a download
--                                          matches what the user set up on screen.
--                transaction_preferences — visible columns + their order for the
--                                          transaction list and the record (sub-transaction)
--                                          tables.
--              Both default to an empty object; the app fills in defaults for missing keys.
-- ============================================================================

ALTER TABLE user_locations_settings
    ADD COLUMN IF NOT EXISTS report_preferences JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE user_locations_settings
    ADD COLUMN IF NOT EXISTS transaction_preferences JSONB NOT NULL DEFAULT '{}'::jsonb;
