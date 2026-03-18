-- Migration: Add qr_name column to user_locations
-- Date: 2026-03-18

ALTER TABLE user_locations
    ADD COLUMN IF NOT EXISTS qr_name VARCHAR(255) DEFAULT NULL;
