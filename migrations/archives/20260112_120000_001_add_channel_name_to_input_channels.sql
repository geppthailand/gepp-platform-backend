-- Migration: Add channel_name column to user_input_channels
-- Date: 2026-01-12
-- Description: Add channel_name column for better channel identification
--              Channels are now organization-level, not tied to specific users

-- Add channel_name column
ALTER TABLE user_input_channels
ADD COLUMN IF NOT EXISTS channel_name VARCHAR(255);

-- Make user_location_id nullable (channels are now organization-level)
ALTER TABLE user_input_channels
ALTER COLUMN user_location_id DROP NOT NULL;

-- Update existing channels without names to use a default name
UPDATE user_input_channels
SET channel_name = CONCAT('Channel #', id)
WHERE channel_name IS NULL OR channel_name = '';

-- Add index for channel_name for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_input_channels_channel_name
ON user_input_channels(channel_name);

-- Add index for organization_id for faster organization-level queries
CREATE INDEX IF NOT EXISTS idx_user_input_channels_organization_id
ON user_input_channels(organization_id);
