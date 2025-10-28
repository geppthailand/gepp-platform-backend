-- Migration: Add is_active column to integration_tokens table
-- Date: 2025-10-28
-- Description: Add missing is_active column that is inherited from BaseModel

-- Add is_active column to integration_tokens
ALTER TABLE integration_tokens
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

-- Add comment
COMMENT ON COLUMN integration_tokens.is_active IS 'Standard soft delete flag (inherited from BaseModel)';
