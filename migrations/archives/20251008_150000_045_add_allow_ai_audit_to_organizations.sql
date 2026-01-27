-- Migration: Add allow_ai_audit column to organizations table
-- Date: 2025-10-08 15:00:00
-- Description: Adds allow_ai_audit boolean column to control AI audit permissions for organizations

-- Add allow_ai_audit column to organizations table
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS allow_ai_audit BOOLEAN DEFAULT FALSE;

-- Add comment to explain the column
COMMENT ON COLUMN organizations.allow_ai_audit IS 'Controls whether the organization has granted permission to use AI for transaction auditing. Default is FALSE for security and privacy compliance.';

-- Create index for faster queries on allow_ai_audit
CREATE INDEX IF NOT EXISTS idx_organizations_allow_ai_audit
ON organizations(allow_ai_audit)
WHERE allow_ai_audit = TRUE;
