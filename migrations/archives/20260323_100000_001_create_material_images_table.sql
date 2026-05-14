-- ============================================================================
-- Migration: Create material_images table
-- Date: 2026-03-23
-- Description: Stores image references for materials
-- ============================================================================

CREATE TABLE IF NOT EXISTS material_images (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    image_url TEXT NOT NULL,
    material_id BIGINT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_material_images_material_id ON material_images(material_id);
CREATE INDEX IF NOT EXISTS idx_material_images_is_active ON material_images(is_active);
