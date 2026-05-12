-- Add from_lead_id to user_locations — links a converted user back to their origin lead.
-- Sprint 9 Phase 2.

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS from_lead_id BIGINT REFERENCES crm_leads(id);

CREATE INDEX IF NOT EXISTS idx_user_locations_from_lead
    ON user_locations (from_lead_id)
    WHERE from_lead_id IS NOT NULL;

COMMENT ON COLUMN user_locations.from_lead_id IS
    'Back-link to the crm_leads row that was converted to create this user. '
    'Populated by lead_service.convert_lead(). NULL for users not created via lead conversion.';
