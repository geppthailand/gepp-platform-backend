-- ============================================================================
-- Migration: Bind a user to the location they sort at (ผู้คัดแยก)
-- Date: 2026-08-06
-- Description: A "sorter" works at one waste room and records what leaves it.
--              The scale tablet shows that user DESTINATIONS instead of origins,
--              so the server must know which location the material is leaving
--              FROM — the tablet no longer tells us.
--
--              Why a dedicated column instead of a role in user_locations.members:
--                • members[].role is rewritten wholesale by the org-chart save
--                  (the UI only knows admin/dataInput/auditor/viewer and drops
--                  anything else), so a role-based binding is silently destroyed
--                  on the next save of that location.
--                • changing a user's organization_role cascades through
--                  _sync_member_role_in_locations and rewrites their role at
--                  EVERY location at once — a binding stored there cannot stay
--                  unique to one location.
--                • one column per user makes "one user sorts at one place"
--                  true by construction, with no validator to bypass.
--
--              NULL (the default) = not a sorter. Nothing changes for anyone
--              until an admin sets this, so deploying is a no-op.
-- ============================================================================

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS sorter_location_id BIGINT NULL REFERENCES user_locations(id);

-- Reverse lookup: "is this location a waste room / who sorts here". Partial —
-- the column is NULL for all but a handful of rows.
CREATE INDEX IF NOT EXISTS idx_user_locations_sorter_location
    ON user_locations (sorter_location_id)
    WHERE sorter_location_id IS NOT NULL;
