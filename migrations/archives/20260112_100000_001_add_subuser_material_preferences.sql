-- Migration: Add subuser_material_preferences column to user_input_channels
-- This column stores per-subuser material preferences for the mobile input form
-- Date: 2026-01-12

-- Add the new column for storing subuser material preferences
ALTER TABLE user_input_channels
ADD COLUMN IF NOT EXISTS subuser_material_preferences JSONB DEFAULT '{}'::jsonb;

-- Add a comment to document the column
COMMENT ON COLUMN user_input_channels.subuser_material_preferences IS
    'Stores material preferences per subuser. Format: {"subuser_name": [material_id1, material_id2, ...]}';

-- Create an index for faster lookups on the JSON column
CREATE INDEX IF NOT EXISTS idx_user_input_channels_subuser_prefs
    ON user_input_channels USING gin (subuser_material_preferences);
