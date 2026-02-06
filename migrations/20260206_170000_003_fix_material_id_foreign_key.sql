-- Migration: Fix material_id foreign key to point to materials table
-- Date: 2026-02-06
-- Description: Change foreign key from main_materials to materials table

-- Drop the incorrect foreign key constraint
ALTER TABLE ai_audit_response_patterns
DROP CONSTRAINT IF EXISTS fk_response_patterns_material;

-- Add correct foreign key constraint to materials table
ALTER TABLE ai_audit_response_patterns
ADD CONSTRAINT fk_response_patterns_material
FOREIGN KEY (material_id) REFERENCES materials(id)
ON DELETE CASCADE;
