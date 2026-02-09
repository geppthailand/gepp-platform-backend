-- Migration: Create ai_audit_rule_sets table
-- Date: 2026-01-22
-- Description: Creates ai_audit_rule_sets table to store different AI audit rule set configurations

-- Create ai_audit_rule_sets table
CREATE TABLE IF NOT EXISTS ai_audit_rule_sets (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    function_name VARCHAR(255) NOT NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_ai_audit_rule_sets_name
ON ai_audit_rule_sets(name);

CREATE INDEX IF NOT EXISTS idx_ai_audit_rule_sets_function_name
ON ai_audit_rule_sets(function_name);

CREATE INDEX IF NOT EXISTS idx_ai_audit_rule_sets_is_active
ON ai_audit_rule_sets(is_active)
WHERE is_active = TRUE;

-- Add trigger for updated_date
CREATE TRIGGER update_ai_audit_rule_sets_updated_date
BEFORE UPDATE ON ai_audit_rule_sets
FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Add comments
COMMENT ON TABLE ai_audit_rule_sets IS 'Stores different AI audit rule set configurations for organizations';
COMMENT ON COLUMN ai_audit_rule_sets.name IS 'Human-readable name of the audit rule set';
COMMENT ON COLUMN ai_audit_rule_sets.function_name IS 'Function name to be used for this audit rule set in the backend';
COMMENT ON COLUMN ai_audit_rule_sets.created_date IS 'Timestamp when the rule set was created';
COMMENT ON COLUMN ai_audit_rule_sets.updated_date IS 'Timestamp when the rule set was last updated';
COMMENT ON COLUMN ai_audit_rule_sets.deleted_date IS 'Timestamp when the rule set was soft deleted';
COMMENT ON COLUMN ai_audit_rule_sets.is_active IS 'Whether the rule set is currently active';

-- Insert default data
INSERT INTO ai_audit_rule_sets (id, name, function_name) VALUES
    (1, 'default', 'default_audit_rule_set'),
    (2, 'bma', 'bma_audit_rule_set')
ON CONFLICT (name) DO NOTHING;

-- Reset sequence to ensure next auto-increment starts after 2
SELECT setval('ai_audit_rule_sets_id_seq', (SELECT MAX(id) FROM ai_audit_rule_sets));
