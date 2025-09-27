-- Migration: Add missing columns to main_materials table
-- Version: v1.040
-- Date: 2025-09-23
-- Description: Add color and display_order columns to main_materials table

-- Add color column with default value
ALTER TABLE main_materials
ADD COLUMN IF NOT EXISTS color VARCHAR(7) NOT NULL DEFAULT '#808080';

-- Add display_order column with default value
ALTER TABLE main_materials
ADD COLUMN IF NOT EXISTS display_order BIGINT NOT NULL DEFAULT 0;

-- Create index on display_order for efficient sorting
CREATE INDEX IF NOT EXISTS idx_main_materials_display_order
ON main_materials(display_order);

-- Update existing records to have proper display order (optional)
-- This will set display_order based on creation date to maintain some ordering
UPDATE main_materials
SET display_order = subq.row_num - 1
FROM (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY created_date, id) as row_num
    FROM main_materials
    WHERE display_order = 0
) subq
WHERE main_materials.id = subq.id;

-- Add comment
COMMENT ON COLUMN main_materials.color IS 'Hex color code for UI display (e.g., #FF0000)';
COMMENT ON COLUMN main_materials.display_order IS 'Order for sorting materials in UI (0-based)';