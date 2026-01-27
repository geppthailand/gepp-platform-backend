-- Migration: Add secret column to user_locations for integration authentication
-- Version: v1.056
-- Date: 2025-10-28
-- Description: Add secret key column for API integration authentication

-- Add secret column to user_locations
ALTER TABLE user_locations
ADD COLUMN IF NOT EXISTS secret VARCHAR(255);

-- Add comment explaining the purpose
COMMENT ON COLUMN user_locations.secret IS 'Secret key hash for integration authentication (API key)';

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_locations_secret ON user_locations(secret) WHERE secret IS NOT NULL;
