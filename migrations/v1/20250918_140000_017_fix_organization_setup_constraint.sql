-- Migration: Fix organization_setup unique constraint
-- Date: 2025-09-18
-- Description: Fix the unique constraint to only apply when is_active=true

-- Drop the existing constraint that prevents multiple inactive records
ALTER TABLE organization_setup DROP CONSTRAINT IF EXISTS uq_organization_setup_current_version;

-- Create a partial unique index that only applies when is_active=true
-- This allows multiple inactive versions per organization but only one active version
CREATE UNIQUE INDEX IF NOT EXISTS uq_organization_setup_active_version
    ON organization_setup(organization_id)
    WHERE is_active = true;

-- Update the trigger function to be more robust
CREATE OR REPLACE FUNCTION ensure_single_active_organization_setup()
RETURNS TRIGGER AS $$
BEGIN
    -- If setting is_active to true, deactivate all other versions for this organization
    IF NEW.is_active = TRUE THEN
        -- Use a more explicit update to avoid constraint violations
        UPDATE organization_setup
        SET is_active = FALSE, updated_date = NOW()
        WHERE organization_id = NEW.organization_id
          AND id != COALESCE(NEW.id, -1)  -- Handle case where NEW.id might be null during INSERT
          AND is_active = TRUE;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add a comment explaining the constraint
COMMENT ON INDEX uq_organization_setup_active_version IS 'Ensures only one active version per organization while allowing multiple inactive versions';