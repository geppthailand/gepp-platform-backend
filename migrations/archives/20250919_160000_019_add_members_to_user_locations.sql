-- Migration: Add members column to user_locations table
-- Date: 2025-09-19
-- Description: Add members field to support user assignments for locations

-- Add members column to user_locations table
ALTER TABLE user_locations
ADD COLUMN members JSONB;

-- Add comment explaining the column purpose
COMMENT ON COLUMN user_locations.members IS 'JSON array of member objects with user_id and role for location user assignments, e.g. [{"user_id": "27", "role": "admin"}]';

-- Add index for members queries (optional, for performance)
-- Using jsonb_path_ops for efficient JSON queries
CREATE INDEX IF NOT EXISTS idx_user_locations_members
ON user_locations USING GIN (members jsonb_path_ops)
WHERE members IS NOT NULL;

COMMENT ON INDEX idx_user_locations_members IS 'GIN index for efficient JSON queries on members field';