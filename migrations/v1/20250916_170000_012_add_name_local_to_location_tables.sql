-- Migration: Add name_local columns to location tables
-- Date: 2025-09-16 17:00:00
-- Description: Add name_local columns to location_countries, location_provinces, location_districts, and location_subdistricts tables

-- Add name_local column to location_countries table
ALTER TABLE location_countries
ADD COLUMN IF NOT EXISTS name_local VARCHAR(255);

-- Add name_local column to location_provinces table
ALTER TABLE location_provinces
ADD COLUMN IF NOT EXISTS name_local VARCHAR(255);

-- Add name_local column to location_districts table
ALTER TABLE location_districts
ADD COLUMN IF NOT EXISTS name_local VARCHAR(255);

-- Add name_local column to location_subdistricts table
ALTER TABLE location_subdistricts
ADD COLUMN IF NOT EXISTS name_local VARCHAR(255);

-- Add name_local column to location_regions table
ALTER TABLE location_regions
ADD COLUMN IF NOT EXISTS name_local VARCHAR(255);

-- Add helpful comment
DO $$
BEGIN
    RAISE NOTICE 'Location tables updated successfully';
    RAISE NOTICE 'Added name_local columns to all location tables';
END $$;