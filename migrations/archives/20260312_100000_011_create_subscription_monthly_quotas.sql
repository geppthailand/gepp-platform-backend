-- Migration: Create subscription_monthly_quotas table
-- Date: 2026-03-12
-- Description: Track AI audit and transaction creation usage per time period (monthly/yearly)
--              Replaces direct usage tracking on subscriptions table.

CREATE TABLE IF NOT EXISTS subscription_monthly_quotas (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    duration_type VARCHAR(20) NOT NULL DEFAULT 'monthly',
    duration_scope VARCHAR(10) NOT NULL,
    ai_audit_limit INTEGER NOT NULL DEFAULT 10,
    ai_audit_usage INTEGER NOT NULL DEFAULT 0,
    create_transaction_limit INTEGER NOT NULL DEFAULT 100,
    create_transaction_usage INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_monthly_quotas_unique
    ON subscription_monthly_quotas(organization_id, duration_type, duration_scope)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_sub_monthly_quotas_org
    ON subscription_monthly_quotas(organization_id);

COMMENT ON TABLE subscription_monthly_quotas IS 'Tracks usage quotas per organization per time period (monthly or yearly). Auto-created on first access each period.';
COMMENT ON COLUMN subscription_monthly_quotas.duration_type IS 'monthly or yearly — determines how duration_scope is formatted';
COMMENT ON COLUMN subscription_monthly_quotas.duration_scope IS 'Time period identifier: YYYY-MM for monthly, YYYY for yearly';
