-- Migration: Convert user_location_tags from single location to many-to-many relationship
-- Date: 2026-01-14
-- Description:
--   1. Add user_locations JSONB column to user_location_tags
--   2. Migrate existing user_location_id data to user_locations array
--   3. Add tags JSONB column to user_locations

-- Step 1: Add user_locations column to user_location_tags if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_location_tags'
        AND column_name = 'user_locations'
    ) THEN
        ALTER TABLE user_location_tags
        ADD COLUMN user_locations JSONB DEFAULT '[]'::jsonb;

        RAISE NOTICE 'Added user_locations column to user_location_tags';
    ELSE
        RAISE NOTICE 'user_locations column already exists in user_location_tags';
    END IF;
END $$;

-- Step 2: Migrate existing user_location_id data to user_locations array
UPDATE user_location_tags
SET user_locations = jsonb_build_array(user_location_id)
WHERE user_location_id IS NOT NULL
  AND (user_locations IS NULL OR user_locations = '[]'::jsonb);

-- Step 3: Add tags column to user_locations if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_locations'
        AND column_name = 'tags'
    ) THEN
        ALTER TABLE user_locations
        ADD COLUMN tags JSONB DEFAULT '[]'::jsonb;

        RAISE NOTICE 'Added tags column to user_locations';
    ELSE
        RAISE NOTICE 'tags column already exists in user_locations';
    END IF;
END $$;

-- Step 4: Populate the tags column in user_locations based on existing user_location_tags
-- This creates the bidirectional relationship
UPDATE user_locations ul
SET tags = (
    SELECT COALESCE(jsonb_agg(ult.id), '[]'::jsonb)
    FROM user_location_tags ult
    WHERE ult.user_location_id = ul.id
      AND ult.deleted_date IS NULL
      AND ult.is_active = true
)
WHERE ul.is_location = true
  AND (ul.tags IS NULL OR ul.tags = '[]'::jsonb);

-- Step 5: Verify migration
DO $$
DECLARE
    tag_count INTEGER;
    location_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO tag_count FROM user_location_tags WHERE user_locations IS NOT NULL AND user_locations != '[]'::jsonb;
    SELECT COUNT(*) INTO location_count FROM user_locations WHERE tags IS NOT NULL AND tags != '[]'::jsonb;

    RAISE NOTICE 'Migration complete:';
    RAISE NOTICE '  - Tags with user_locations populated: %', tag_count;
    RAISE NOTICE '  - Locations with tags populated: %', location_count;
END $$;
