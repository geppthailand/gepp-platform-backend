-- Migration: Add color column to material_categories table
-- Version: v1.041
-- Date: 2025-09-24
-- Description: Add color column to material_categories table for better UI categorization

-- Add color column with default value
ALTER TABLE material_categories
ADD COLUMN IF NOT EXISTS color VARCHAR(7) NOT NULL DEFAULT '#808080';

-- Create index on color for potential filtering
CREATE INDEX IF NOT EXISTS idx_material_categories_color
ON material_categories(color);

-- Update existing records with nice pastel colors for the 7 main categories
-- These are pleasant, distinguishable pastel colors that work well in UI
UPDATE material_categories
SET color = CASE
    WHEN name_en ILIKE '%recyclable%' OR name_en ILIKE '%recycle%' THEN '#A7F3D0'  -- Soft mint green
    WHEN name_en ILIKE '%electronic%' OR name_en ILIKE '%electric%' THEN '#BFDBFE'  -- Soft blue
    WHEN name_en ILIKE '%organic%' OR name_en ILIKE '%food%' THEN '#FDE68A'         -- Soft yellow
    WHEN name_en ILIKE '%general%' OR name_en ILIKE '%mixed%' THEN '#D1D5DB'        -- Soft gray
    WHEN name_en ILIKE '%hazardous%' OR name_en ILIKE '%dangerous%' THEN '#FCA5A5'  -- Soft red
    WHEN name_en ILIKE '%medical%' OR name_en ILIKE '%infectious%' THEN '#F3E8FF'   -- Soft purple
    WHEN name_en ILIKE '%construction%' OR name_en ILIKE '%building%' THEN '#FED7AA' -- Soft orange
    ELSE '#E5E7EB'  -- Default soft gray for any other categories
END
WHERE color = '#808080';  -- Only update default colors

-- Add comment
COMMENT ON COLUMN material_categories.color IS 'Hex color code for UI display and categorization (e.g., #A7F3D0)';