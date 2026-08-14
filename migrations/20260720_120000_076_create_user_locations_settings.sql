-- ============================================================================
-- Migration: Per-user data-entry settings (user_locations_settings)
-- Date: 2026-07-20
-- Description: Moves the two "ตั้งค่าทั่วไป" General-Settings toggles —
--              input_destination ("กรอกปลายทาง") and show_all_location_options
--              ("แสดงตัวเลือกสถานที่ทั้งหมด") — from per-ORG (organization_setup)
--              to PER-USER. Each user (a user_locations row with is_user=true) gets at
--              most one live settings row. When a user has no row, the app falls back to
--              the system defaults (input_destination=false, show_all_location_options=true).
--              The organization_setup columns stay in place (harmless) but are no longer
--              read for these toggles.
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_locations_settings (
    id                        BIGSERIAL PRIMARY KEY,
    user_location_id          BIGINT NOT NULL REFERENCES user_locations(id),
    organization_id           BIGINT REFERENCES organizations(id),
    input_destination         BOOLEAN NOT NULL DEFAULT FALSE,
    show_all_location_options BOOLEAN NOT NULL DEFAULT TRUE,
    created_date              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date              TIMESTAMPTZ
);

-- One live settings row per user (soft-deleted rows don't block a fresh one).
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_locations_settings_user
    ON user_locations_settings (user_location_id)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_user_locations_settings_org
    ON user_locations_settings (organization_id);
