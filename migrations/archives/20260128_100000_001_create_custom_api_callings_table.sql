-- Create custom_api_callings table
-- Records each custom API call with affected transaction data

CREATE TABLE IF NOT EXISTS custom_api_callings (
    id BIGSERIAL PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    api_path VARCHAR(255),
    custom_api_id BIGINT REFERENCES custom_apis(id),
    full_path TEXT,
    api_method VARCHAR(10),
    caller_id BIGINT REFERENCES user_locations(id),

    created_transactions JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_transactions JSONB NOT NULL DEFAULT '[]'::jsonb,
    deleted_transactions JSONB NOT NULL DEFAULT '[]'::jsonb,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

CREATE INDEX idx_custom_api_callings_org_id ON custom_api_callings(organization_id);
CREATE INDEX idx_custom_api_callings_status ON custom_api_callings(status);
CREATE INDEX idx_custom_api_callings_caller_id ON custom_api_callings(caller_id);
CREATE INDEX idx_custom_api_callings_created_date ON custom_api_callings(created_date);
