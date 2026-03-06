-- Migration: Create traceability_transport_transactions table
-- Date: 2025-03-02
-- Description: Transport transactions with traceability group linkage and hierarchy

CREATE TABLE IF NOT EXISTS traceability_transport_transactions (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    origin_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    material_id BIGINT REFERENCES materials(id) ON DELETE SET NULL,
    weight DECIMAL,
    meta_data JSONB,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    transaction_group_id BIGINT REFERENCES traceability_transaction_group(id) ON DELETE SET NULL,
    disposal_method VARCHAR(255),
    arrival_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(100),
    is_root BOOLEAN NOT NULL DEFAULT FALSE,
    parent_id BIGINT REFERENCES traceability_transport_transactions(id) ON DELETE SET NULL,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_transport_transaction_origin_id ON traceability_transport_transactions(origin_id);
CREATE INDEX IF NOT EXISTS idx_transport_transaction_material_id ON traceability_transport_transactions(material_id);
CREATE INDEX IF NOT EXISTS idx_transport_transaction_organization_id ON traceability_transport_transactions(organization_id);
CREATE INDEX IF NOT EXISTS idx_transport_transaction_transaction_group_id ON traceability_transport_transactions(transaction_group_id);
CREATE INDEX IF NOT EXISTS idx_transport_transaction_parent_id ON traceability_transport_transactions(parent_id);
CREATE INDEX IF NOT EXISTS idx_transport_transaction_is_active ON traceability_transport_transactions(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_transport_transaction_deleted ON traceability_transport_transactions(deleted_date) WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_transport_transaction_arrival_date ON traceability_transport_transactions(arrival_date);
CREATE INDEX IF NOT EXISTS idx_transport_transaction_status ON traceability_transport_transactions(status);

-- Add comments
COMMENT ON TABLE traceability_transport_transactions IS 'Transport transactions with traceability group and parent-child hierarchy';
COMMENT ON COLUMN traceability_transport_transactions.origin_id IS 'Origin user_location id';
COMMENT ON COLUMN traceability_transport_transactions.transaction_group_id IS 'Reference to traceability_transaction_group';
COMMENT ON COLUMN traceability_transport_transactions.parent_id IS 'Parent traceability_transport_transactions for hierarchy';
COMMENT ON COLUMN traceability_transport_transactions.is_root IS 'Whether this transaction is a root in the hierarchy';
