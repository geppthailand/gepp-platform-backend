-- Migration: Create traceability_transaction_group table
-- Date: 2025-03-02
-- Description: Groups of traceability transactions with linked transaction records/groups

CREATE TABLE IF NOT EXISTS traceability_transaction_group (
    id BIGSERIAL PRIMARY KEY,
    origin_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    material_id BIGINT REFERENCES materials(id) ON DELETE SET NULL,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    transaction_record_id BIGINT[] NOT NULL DEFAULT '{}',
    transaction_group_id BIGINT[] NOT NULL DEFAULT '{}',
    transaction_year INTEGER,
    transaction_month INTEGER,
    location_tag_id BIGINT,
    tenant_id BIGINT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_origin_id ON traceability_transaction_group(origin_id);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_material_id ON traceability_transaction_group(material_id);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_organization_id ON traceability_transaction_group(organization_id);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_is_active ON traceability_transaction_group(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_deleted ON traceability_transaction_group(deleted_date) WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_transaction_record_id ON traceability_transaction_group USING GIN(transaction_record_id);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_transaction_group_id ON traceability_transaction_group USING GIN(transaction_group_id);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_transaction_year ON traceability_transaction_group(transaction_year);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_transaction_month ON traceability_transaction_group(transaction_month);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_year_month ON traceability_transaction_group(transaction_year, transaction_month);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_location_tag_id ON traceability_transaction_group(location_tag_id);
CREATE INDEX IF NOT EXISTS idx_traceability_transaction_group_tenant_id ON traceability_transaction_group(tenant_id);

-- Add comments
COMMENT ON TABLE traceability_transaction_group IS 'Groups of traceability transactions with linked transaction records/groups';
COMMENT ON COLUMN traceability_transaction_group.origin_id IS 'Origin user_location id';
COMMENT ON COLUMN traceability_transaction_group.transaction_record_id IS 'List of transaction_record ids';
COMMENT ON COLUMN traceability_transaction_group.transaction_group_id IS 'List of traceability_transaction_group ids (nested groups)';
COMMENT ON COLUMN traceability_transaction_group.transaction_year IS 'Year of the transaction (e.g. 2025)';
COMMENT ON COLUMN traceability_transaction_group.transaction_month IS 'Month of the transaction (1-12)';
COMMENT ON COLUMN traceability_transaction_group.location_tag_id IS 'user_location_tags.id';
COMMENT ON COLUMN traceability_transaction_group.tenant_id IS 'user_tenants.id';
