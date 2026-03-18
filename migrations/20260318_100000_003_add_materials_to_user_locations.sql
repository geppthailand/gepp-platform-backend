-- Migration: Add materials JSONB column to user_locations
-- This column stores an array of material IDs associated with the location
-- Example: [1, 5, 12, 34]

ALTER TABLE user_locations
ADD COLUMN IF NOT EXISTS materials JSONB DEFAULT '[]'::jsonb;

-- Index for querying locations by material
CREATE INDEX IF NOT EXISTS idx_user_locations_materials
ON user_locations USING GIN (materials);

COMMENT ON COLUMN user_locations.materials IS 'JSONB array of material IDs (references materials.id) assigned to this location';
