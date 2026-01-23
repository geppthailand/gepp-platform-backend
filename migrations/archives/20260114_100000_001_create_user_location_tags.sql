-- Migration: Create user_location_tags table
-- Date: 2026-01-14
-- Description: Creates the user_location_tags table for managing location tags
--              Tags can be assigned to locations with optional date ranges (events)

-- Create user_location_tags table
CREATE TABLE IF NOT EXISTS user_location_tags (
    id SERIAL PRIMARY KEY,

    -- Basic info
    name VARCHAR(255) NOT NULL,
    note TEXT,

    -- Relationships
    user_location_id INTEGER NOT NULL REFERENCES user_locations(id),
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    created_by_id INTEGER REFERENCES user_locations(id),

    -- Members (JSONB array of user_location IDs assigned to this tag)
    members JSONB DEFAULT '[]'::jsonb,

    -- Event date range (optional - for time-based tags/events)
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,

    -- Standard audit fields
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE,
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_user_location_tags_user_location_id ON user_location_tags(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_location_tags_organization_id ON user_location_tags(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_location_tags_is_active ON user_location_tags(is_active);
CREATE INDEX IF NOT EXISTS idx_user_location_tags_deleted_date ON user_location_tags(deleted_date);

-- Add comment for documentation
COMMENT ON TABLE user_location_tags IS 'Location tags for categorizing and grouping waste origin points within locations';
COMMENT ON COLUMN user_location_tags.members IS 'JSONB array of user_location IDs assigned as tag members';
COMMENT ON COLUMN user_location_tags.start_date IS 'Optional start date for time-based tags/events';
COMMENT ON COLUMN user_location_tags.end_date IS 'Optional end date for time-based tags/events';
