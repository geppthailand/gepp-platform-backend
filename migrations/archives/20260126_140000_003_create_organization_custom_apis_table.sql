-- Migration: Create organization_custom_apis table
-- Date: 2026-01-26
-- Description: Creates junction table for organization-specific API access control

CREATE TABLE IF NOT EXISTS organization_custom_apis (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    custom_api_id BIGINT NOT NULL REFERENCES custom_apis(id) ON DELETE CASCADE,
    api_call_quota INTEGER DEFAULT 1000,
    api_call_used INTEGER DEFAULT 0,
    process_quota INTEGER DEFAULT 10000,
    process_used INTEGER DEFAULT 0,
    enable BOOLEAN DEFAULT TRUE,
    expired_date TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    UNIQUE(organization_id, custom_api_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_org_custom_apis_org_id ON organization_custom_apis(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_custom_apis_custom_api_id ON organization_custom_apis(custom_api_id);
CREATE INDEX IF NOT EXISTS idx_org_custom_apis_enable ON organization_custom_apis(enable) WHERE enable = TRUE;
CREATE INDEX IF NOT EXISTS idx_org_custom_apis_deleted ON organization_custom_apis(deleted_date) WHERE deleted_date IS NULL;

-- Add comments
COMMENT ON TABLE organization_custom_apis IS 'Controls which custom APIs are enabled for each organization with quotas';
COMMENT ON COLUMN organization_custom_apis.api_call_quota IS 'Maximum number of API calls allowed';
COMMENT ON COLUMN organization_custom_apis.api_call_used IS 'Current API call count';
COMMENT ON COLUMN organization_custom_apis.process_quota IS 'Maximum processing units (e.g., images processed)';
COMMENT ON COLUMN organization_custom_apis.process_used IS 'Current processing units used';
COMMENT ON COLUMN organization_custom_apis.expired_date IS 'When the API access expires (NULL = never expires)';

-- Insert initial configuration for organization 8 with AI Audit V1
INSERT INTO organization_custom_apis (
    id, organization_id, custom_api_id, 
    api_call_quota, process_quota, 
    enable, expired_date
)
VALUES (
    1, 8, 1,
    1000, 10000,
    TRUE, '2027-01-26 00:00:00+07'
) ON CONFLICT (organization_id, custom_api_id) DO UPDATE SET
    api_call_quota = EXCLUDED.api_call_quota,
    process_quota = EXCLUDED.process_quota,
    enable = EXCLUDED.enable,
    expired_date = EXCLUDED.expired_date,
    updated_date = NOW();

-- Reset sequence if needed
SELECT setval('organization_custom_apis_id_seq', GREATEST((SELECT MAX(id) FROM organization_custom_apis), 1));
