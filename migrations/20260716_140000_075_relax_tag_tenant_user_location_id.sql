-- ============================================================================
-- Migration: Relax user_location_id NOT NULL on user_location_tags / user_tenants
-- Date: 2026-07-16
-- Description: `user_location_id` is a legacy single-location reference — the models already
--              declare it nullable ("use the user_locations JSONB array instead"), but the DB
--              still enforced NOT NULL. Org-level tags/tenants (e.g. from the back-office
--              "Import Organization Setup") are not tied to one location, so they must allow a
--              NULL user_location_id. DROP NOT NULL is idempotent (safe to re-run) and does not
--              touch existing rows.
-- ============================================================================

ALTER TABLE user_location_tags ALTER COLUMN user_location_id DROP NOT NULL;
ALTER TABLE user_tenants       ALTER COLUMN user_location_id DROP NOT NULL;
