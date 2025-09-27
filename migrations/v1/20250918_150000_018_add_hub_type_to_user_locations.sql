-- Migration: Add hub_type column to user_locations table
-- Date: 2025-09-18
-- Description: Add hub_type field to support waste management hub classification

-- Add hub_type column to user_locations table
ALTER TABLE user_locations
ADD COLUMN hub_type TEXT;

-- Add comment explaining the column purpose
COMMENT ON COLUMN user_locations.hub_type IS 'Hub type for waste management locations (from hubData.type), e.g. Collectors, Sorters, Aggregators, etc.';

-- Add index for hub_type queries (optional, for performance)
CREATE INDEX IF NOT EXISTS idx_user_locations_hub_type
ON user_locations(hub_type)
WHERE hub_type IS NOT NULL;

COMMENT ON INDEX idx_user_locations_hub_type IS 'Index for efficient queries on hub_type field';