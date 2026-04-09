-- Add LINE LIFF support to user_locations
-- Enables LIFF users to authenticate via LINE User ID

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS line_user_id VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_locations_line_user_id
    ON user_locations (line_user_id)
    WHERE line_user_id IS NOT NULL;

COMMENT ON COLUMN user_locations.line_user_id IS 'LINE User ID (U...) for LIFF authentication';
