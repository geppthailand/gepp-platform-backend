-- Supplier Magic Links for passwordless portal authentication
-- Suppliers access their data submission portal via time-limited tokens

CREATE TABLE IF NOT EXISTS esg_supplier_magic_links (
    id BIGSERIAL PRIMARY KEY,
    supplier_id BIGINT NOT NULL REFERENCES esg_suppliers(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    token VARCHAR(64) NOT NULL UNIQUE,
    email_sent_to VARCHAR(255),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    scope VARCHAR(30) NOT NULL DEFAULT 'data_submission',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_magic_link_scope CHECK (scope IN ('data_submission', 'profile_update'))
);

CREATE INDEX IF NOT EXISTS idx_esg_magic_links_token
    ON esg_supplier_magic_links (token)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_magic_links_supplier
    ON esg_supplier_magic_links (supplier_id)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_supplier_magic_links IS 'Time-limited authentication tokens for supplier portal access without account creation';
