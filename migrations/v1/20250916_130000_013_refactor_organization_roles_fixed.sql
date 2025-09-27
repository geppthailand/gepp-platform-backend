-- Migration: Refactor business roles to organization roles (Fixed)
-- Date: 2025-09-16 13:00:00
-- Description: Fix the remaining issues from the previous migration

-- Begin transaction
BEGIN;

-- Step 1: Remove existing foreign key constraint for business_role_id (if it still exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints
               WHERE constraint_name = 'user_locations_business_role_id_fkey') THEN
        ALTER TABLE user_locations DROP CONSTRAINT user_locations_business_role_id_fkey;
    END IF;
END $$;

-- Step 2: Rename business_role_id column to organization_role_id (if not already done)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'user_locations' AND column_name = 'business_role_id') THEN
        ALTER TABLE user_locations RENAME COLUMN business_role_id TO organization_role_id;
    END IF;
END $$;

-- Step 3: Add foreign key constraint to organization_roles table (if not already added)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                   WHERE constraint_name = 'user_locations_organization_role_id_fkey') THEN
        ALTER TABLE user_locations
        ADD CONSTRAINT user_locations_organization_role_id_fkey
        FOREIGN KEY (organization_role_id) REFERENCES organization_roles(id);
    END IF;
END $$;

-- Step 4: Update index name
DROP INDEX IF EXISTS idx_user_locations_business_role;
CREATE INDEX IF NOT EXISTS idx_user_locations_organization_role ON user_locations(organization_role_id);

-- Step 5: Update user_invitations table - rename intended_business_role to intended_organization_role
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_invitations'
        AND column_name = 'intended_business_role'
    ) THEN
        ALTER TABLE user_invitations RENAME COLUMN intended_business_role TO intended_organization_role_id;

        -- Update the column type to be a foreign key to organization_roles
        ALTER TABLE user_invitations ALTER COLUMN intended_organization_role_id TYPE BIGINT;

        -- Add foreign key constraint if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                       WHERE constraint_name = 'user_invitations_intended_organization_role_id_fkey') THEN
            ALTER TABLE user_invitations
            ADD CONSTRAINT user_invitations_intended_organization_role_id_fkey
            FOREIGN KEY (intended_organization_role_id) REFERENCES organization_roles(id);
        END IF;
    END IF;
END $$;

-- Commit transaction
COMMIT;