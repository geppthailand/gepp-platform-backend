-- ============================================================================
-- Migration: Add level name columns to organization_setup
-- Date: 2026-03-23
-- Description: Adds custom naming columns for branch, building, floor, and room levels
-- ============================================================================

ALTER TABLE organization_setup
    ADD COLUMN IF NOT EXISTS branch_level_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS building_level_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS floor_level_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS room_level_name VARCHAR(255);
