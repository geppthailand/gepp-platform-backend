-- ============================================================================
-- Migration: Point a location at the waste room its material is collected in
-- Date: 2026-08-11
-- Description: Migration 079 answered "which waste room does this USER sort at".
--              This one answers the other half: "when material is weighed in AT
--              this location, which waste room does it physically go to". The
--              server needs it to route the first traceability hop by itself,
--              so nobody has to open the web board and drag a card.
--
--              Why a column and not a key inside organization_setup.root_nodes,
--              which is where the org tree actually lives:
--                • the org-chart save replaces each node dict wholesale with the
--                  client's copy, so any key the web app forgets to send back is
--                  destroyed on the next save;
--                • the Excel setup importer rebuilds root_nodes from scratch and
--                  only re-attaches is_destination, so the key would not survive
--                  a re-import either.
--              This is the same trap that made 079 use a column instead of
--              user_locations.members.
--
--              Why not infer it from the tree: a building can hold many rooms and
--              nothing marks which one is the waste room. is_destination is a
--              different question ("may material be shipped here"), and it is set
--              on external hubs too.
--
--              NULL (the default) = no routing, exactly today's behaviour. No row
--              is written by this migration, so deploying it is a no-op.
-- ============================================================================

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS waste_room_location_id BIGINT NULL REFERENCES user_locations(id);

-- Reverse lookup: "what feeds this waste room". Partial — the column is NULL for
-- every row until an admin sets it.
CREATE INDEX IF NOT EXISTS idx_user_locations_waste_room
    ON user_locations (waste_room_location_id)
    WHERE waste_room_location_id IS NOT NULL;

COMMENT ON COLUMN user_locations.waste_room_location_id IS
    'Location whose waste room collects material weighed in at this location. NULL = no auto-routing. See migration 081.';
