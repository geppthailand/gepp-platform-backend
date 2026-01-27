-- Migration: Add first_name and last_name columns to user_locations
-- Date: 2026-01-14
-- Description: Add first_name and last_name fields for user profile data

-- Add first_name column
ALTER TABLE user_locations
ADD COLUMN IF NOT EXISTS first_name VARCHAR(255);

-- Add last_name column
ALTER TABLE user_locations
ADD COLUMN IF NOT EXISTS last_name VARCHAR(255);

-- Add comment for documentation
COMMENT ON COLUMN user_locations.first_name IS 'User first name';
COMMENT ON COLUMN user_locations.last_name IS 'User last name';
