-- Migration: Create audit_rules table for AI-based auditing system
-- Version: v1.043
-- Date: 2025-09-25
-- Description: Create audit_rules table to store audit rules with configurable actions and conditions

-- Create enum type for rule_type
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rule_type_enum') THEN
        CREATE TYPE rule_type_enum AS ENUM (
            'consistency',
            'redundancy',
            'completeness',
            'accuracy',
            'validity',
            'compliance'
        );
    END IF;
END
$$;

-- Create audit_rules table
CREATE TABLE IF NOT EXISTS audit_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_id VARCHAR(20) NOT NULL UNIQUE,
    rule_type rule_type_enum NOT NULL,
    rule_name VARCHAR(500) NOT NULL,
    process VARCHAR(255),
    condition TEXT,
    thresholds TEXT,
    metrics TEXT,
    actions JSONB NOT NULL DEFAULT '[]',
    is_global BOOLEAN NOT NULL DEFAULT TRUE,
    organization_id BIGINT REFERENCES organizations(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_audit_rules_rule_id ON audit_rules(rule_id);
CREATE INDEX IF NOT EXISTS idx_audit_rules_rule_type ON audit_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_audit_rules_is_global ON audit_rules(is_global);
CREATE INDEX IF NOT EXISTS idx_audit_rules_organization_id ON audit_rules(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_rules_is_active ON audit_rules(is_active);
CREATE INDEX IF NOT EXISTS idx_audit_rules_created_date ON audit_rules(created_date);

-- Create GIN index for JSONB actions column for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_rules_actions_gin ON audit_rules USING GIN(actions);

-- Add table comment
COMMENT ON TABLE audit_rules IS 'Audit rules for AI-based auditing system with configurable actions and conditions';

-- Add column comments
COMMENT ON COLUMN audit_rules.rule_id IS 'Unique rule identifier (e.g., DC-01, CR-02)';
COMMENT ON COLUMN audit_rules.rule_type IS 'Type of audit rule based on sheet names in Excel file';
COMMENT ON COLUMN audit_rules.rule_name IS 'Human-readable name of the rule';
COMMENT ON COLUMN audit_rules.process IS 'Process or workflow this rule applies to';
COMMENT ON COLUMN audit_rules.condition IS 'Condition that triggers this rule';
COMMENT ON COLUMN audit_rules.thresholds IS 'Threshold values for rule evaluation';
COMMENT ON COLUMN audit_rules.metrics IS 'Key Data Points / Metrics for measurement';
COMMENT ON COLUMN audit_rules.actions IS 'JSON array of actions with types: system_action, human_action, recommendations';
COMMENT ON COLUMN audit_rules.is_global IS 'Whether this rule applies to all organizations (true) or is organization-specific (false)';
COMMENT ON COLUMN audit_rules.organization_id IS 'Organization ID for organization-specific rules, NULL for global rules';

-- Create trigger to automatically update updated_date
CREATE OR REPLACE FUNCTION update_audit_rules_updated_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_audit_rules_updated_date
    BEFORE UPDATE ON audit_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_audit_rules_updated_date();