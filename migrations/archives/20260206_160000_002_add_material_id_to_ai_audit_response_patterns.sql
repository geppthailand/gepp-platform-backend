-- Migration: Add material_id to ai_audit_response_patterns
-- Date: 2026-02-06
-- Description: Add material_id column to allow material-specific response patterns

-- Add material_id column (nullable - NULL means applies to all materials)
ALTER TABLE ai_audit_response_patterns
ADD COLUMN IF NOT EXISTS material_id INTEGER;

-- Add foreign key constraint to main_materials table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_response_patterns_material'
    ) THEN
        ALTER TABLE ai_audit_response_patterns
        ADD CONSTRAINT fk_response_patterns_material
        FOREIGN KEY (material_id) REFERENCES main_materials(id)
        ON DELETE CASCADE;
    END IF;
END $$;

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_response_patterns_material_id
ON ai_audit_response_patterns(material_id);

-- Add composite index for organization + material lookup
CREATE INDEX IF NOT EXISTS idx_response_patterns_org_material
ON ai_audit_response_patterns(organization_id, material_id);

-- Add comment
COMMENT ON COLUMN ai_audit_response_patterns.material_id IS 'Material ID this pattern applies to. NULL means applies to all materials (default/fallback pattern).';
