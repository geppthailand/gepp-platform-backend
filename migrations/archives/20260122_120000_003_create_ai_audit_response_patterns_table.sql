-- Migration: Create ai_audit_response_patterns table
-- Date: 2026-01-22
-- Description: Creates ai_audit_response_patterns table to store customizable AI audit response messages per organization

-- Create ai_audit_response_patterns table
CREATE TABLE IF NOT EXISTS ai_audit_response_patterns (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    condition JSONB NOT NULL DEFAULT '[]',
    priority INTEGER NOT NULL DEFAULT 0,
    pattern TEXT NOT NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_ai_audit_response_patterns_organization_id
ON ai_audit_response_patterns(organization_id);

CREATE INDEX IF NOT EXISTS idx_ai_audit_response_patterns_priority
ON ai_audit_response_patterns(organization_id, priority)
WHERE is_active = TRUE AND deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_ai_audit_response_patterns_condition_gin
ON ai_audit_response_patterns USING GIN (condition);

CREATE INDEX IF NOT EXISTS idx_ai_audit_response_patterns_is_active
ON ai_audit_response_patterns(is_active, organization_id)
WHERE is_active = TRUE;

-- Add trigger for updated_date
CREATE TRIGGER update_ai_audit_response_patterns_updated_date
BEFORE UPDATE ON ai_audit_response_patterns
FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Add comments
COMMENT ON TABLE ai_audit_response_patterns IS 'Stores customizable AI audit response message patterns for organizations';
COMMENT ON COLUMN ai_audit_response_patterns.name IS 'Human-readable name of the response pattern';
COMMENT ON COLUMN ai_audit_response_patterns.condition IS 'JSONB array of conditions to match (e.g., ["remark.code == ''wrong_category''"])';
COMMENT ON COLUMN ai_audit_response_patterns.priority IS 'Priority level - 0 is highest priority, larger numbers are lower priority';
COMMENT ON COLUMN ai_audit_response_patterns.pattern IS 'Response message template with placeholders (e.g., "จากรูป {claimed_type} ตรวจพบว่าเป็น {remark.details.detected}")';
COMMENT ON COLUMN ai_audit_response_patterns.organization_id IS 'Organization that owns this response pattern';
COMMENT ON COLUMN ai_audit_response_patterns.created_date IS 'Timestamp when the pattern was created';
COMMENT ON COLUMN ai_audit_response_patterns.updated_date IS 'Timestamp when the pattern was last updated';
COMMENT ON COLUMN ai_audit_response_patterns.deleted_date IS 'Timestamp when the pattern was soft deleted';
COMMENT ON COLUMN ai_audit_response_patterns.is_active IS 'Whether the pattern is currently active';
