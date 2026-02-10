-- Migration: Add tenant_id column to transactions table
-- Date: 2026-02-03
-- Description: Adds tenant_id to link transactions to user_tenants (organization-level tenant).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'transactions'
        AND column_name = 'tenant_id'
    ) THEN
        ALTER TABLE transactions
        ADD COLUMN tenant_id BIGINT;
        RAISE NOTICE 'Added tenant_id column to transactions';
    ELSE
        RAISE NOTICE 'Column tenant_id already exists in transactions';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_transactions_tenant_id ON transactions(tenant_id);

COMMENT ON COLUMN transactions.tenant_id IS 'References user_tenants.id - organization-level tenant for this transaction';
