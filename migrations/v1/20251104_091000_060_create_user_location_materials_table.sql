-- Migration: Create user_location_materials table (link user_locations and materials)
-- Date: 2025-11-04
-- Description: Associates locations with materials with soft-delete support

-- Create user_location_materials table
CREATE TABLE IF NOT EXISTS user_location_materials (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    location_id BIGINT NOT NULL,
    materials_id BIGINT NOT NULL,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    CONSTRAINT fk_ulm_location
        FOREIGN KEY (location_id)
        REFERENCES user_locations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ulm_material
        FOREIGN KEY (materials_id)
        REFERENCES materials(id)
        ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ulm_location ON user_location_materials (location_id);
CREATE INDEX IF NOT EXISTS idx_ulm_material ON user_location_materials (materials_id);
CREATE INDEX IF NOT EXISTS idx_ulm_active ON user_location_materials (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_ulm_not_deleted ON user_location_materials (deleted_date) WHERE deleted_date IS NULL;

-- Prevent duplicate active links for the same location/material pair
CREATE UNIQUE INDEX IF NOT EXISTS uq_ulm_location_material_active
ON user_location_materials (location_id, materials_id)
WHERE deleted_date IS NULL;

-- Comments
COMMENT ON TABLE user_location_materials IS 'Links user_locations to materials with soft-delete and uniqueness per active pair';
COMMENT ON COLUMN user_location_materials.location_id IS 'References user_locations(id)';
COMMENT ON COLUMN user_location_materials.materials_id IS 'References materials(id)';

