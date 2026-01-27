-- Migration: Create custom_apis table
-- Date: 2026-01-26
-- Description: Creates table to store available custom API endpoints

CREATE TABLE IF NOT EXISTS custom_apis (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    service_path VARCHAR(255) NOT NULL UNIQUE,
    root_fn_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_custom_apis_service_path ON custom_apis(service_path);
CREATE INDEX IF NOT EXISTS idx_custom_apis_root_fn_name ON custom_apis(root_fn_name);
CREATE INDEX IF NOT EXISTS idx_custom_apis_deleted ON custom_apis(deleted_date) WHERE deleted_date IS NULL;

-- Add comments
COMMENT ON TABLE custom_apis IS 'Stores available custom API endpoints that can be enabled per organization';
COMMENT ON COLUMN custom_apis.service_path IS 'URL path segment for the API (e.g., ai_audit/v1)';
COMMENT ON COLUMN custom_apis.root_fn_name IS 'Python function name to execute for this API';

-- Insert initial AI Audit V1 API
INSERT INTO custom_apis (id, name, description, service_path, root_fn_name)
VALUES (
    1,
    'AI Audit V1',
    'AI-powered waste transaction audit API. Analyzes images and validates waste classification.',
    'ai_audit/v1',
    'ai_audit_v1'
) ON CONFLICT (service_path) DO NOTHING;

-- Reset sequence if needed
SELECT setval('custom_apis_id_seq', GREATEST((SELECT MAX(id) FROM custom_apis), 1));
