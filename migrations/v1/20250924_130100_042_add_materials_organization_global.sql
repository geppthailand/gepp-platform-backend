-- Migration: Add organization and is_global columns to materials table
-- Version: v1.042
-- Date: 2025-09-24
-- Description: Add organization_id and is_global columns to materials table for multi-tenant support

-- Add is_global column with default true (all materials are currently global)
ALTER TABLE materials
ADD COLUMN IF NOT EXISTS is_global BOOLEAN NOT NULL DEFAULT TRUE;

-- Add organization_id column (nullable, for global materials)
ALTER TABLE materials
ADD COLUMN IF NOT EXISTS organization_id BIGINT;

-- Add foreign key constraint to organizations table (with existence check)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_materials_organization_id'
        AND table_name = 'materials'
    ) THEN
        ALTER TABLE materials
        ADD CONSTRAINT fk_materials_organization_id
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_materials_is_global
ON materials(is_global);

CREATE INDEX IF NOT EXISTS idx_materials_organization_id
ON materials(organization_id);

CREATE INDEX IF NOT EXISTS idx_materials_global_org_lookup
ON materials(is_global, organization_id);

-- Set all existing materials to be global with NULL organization
UPDATE materials
SET is_global = TRUE,
    organization_id = NULL
WHERE is_global IS NULL OR organization_id IS NOT NULL;

-- Add check constraint to ensure logical consistency
-- Global materials should have NULL organization_id
-- Non-global materials should have a valid organization_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'chk_materials_global_organization'
        AND table_name = 'materials'
    ) THEN
        ALTER TABLE materials
        ADD CONSTRAINT chk_materials_global_organization
        CHECK (
            (is_global = TRUE AND organization_id IS NULL) OR
            (is_global = FALSE AND organization_id IS NOT NULL)
        );
    END IF;
END $$;

-- Add comments
COMMENT ON COLUMN materials.is_global IS 'Whether this material is globally available to all organizations';
COMMENT ON COLUMN materials.organization_id IS 'Organization that owns this material (NULL for global materials)';