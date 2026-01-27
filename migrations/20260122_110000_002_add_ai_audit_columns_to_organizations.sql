-- Migration: Add AI audit configuration columns to organizations table
-- Date: 2026-01-22
-- Description: Adds ai_audit_rule_set_id, enable_ai_audit_response_setting, and enable_ai_audit_api columns to organizations

-- Add ai_audit_rule_set_id column with foreign key to ai_audit_rule_sets
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS ai_audit_rule_set_id BIGINT DEFAULT 1;

-- Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_organizations_ai_audit_rule_set_id'
        AND table_name = 'organizations'
    ) THEN
        ALTER TABLE organizations
        ADD CONSTRAINT fk_organizations_ai_audit_rule_set_id
        FOREIGN KEY (ai_audit_rule_set_id) REFERENCES ai_audit_rule_sets(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add enable_ai_audit_response_setting column
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS enable_ai_audit_response_setting BOOLEAN DEFAULT FALSE;

-- Add enable_ai_audit_api column
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS enable_ai_audit_api BOOLEAN DEFAULT FALSE;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_organizations_ai_audit_rule_set_id
ON organizations(ai_audit_rule_set_id);

CREATE INDEX IF NOT EXISTS idx_organizations_enable_ai_audit_response_setting
ON organizations(enable_ai_audit_response_setting)
WHERE enable_ai_audit_response_setting = TRUE;

CREATE INDEX IF NOT EXISTS idx_organizations_enable_ai_audit_api
ON organizations(enable_ai_audit_api)
WHERE enable_ai_audit_api = TRUE;

-- Add comments to explain the columns
COMMENT ON COLUMN organizations.ai_audit_rule_set_id IS 'Foreign key reference to ai_audit_rule_sets table. Determines which AI audit rule set to use for this organization. Defaults to 1 (default rule set).';
COMMENT ON COLUMN organizations.enable_ai_audit_response_setting IS 'Controls whether AI audit response settings are enabled for this organization. Default is FALSE.';
COMMENT ON COLUMN organizations.enable_ai_audit_api IS 'Controls whether AI audit API access is enabled for this organization. Default is FALSE.';
