-- Migration: Create organization_audit_check_columns table
-- Date: 2026-03-11
-- Description: Per-organization column check configuration for AI audit data matching

CREATE TABLE IF NOT EXISTS organization_audit_check_columns (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    transaction_checks JSONB NOT NULL DEFAULT '{}'::jsonb,
    transaction_record_checks JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    CONSTRAINT uq_org_audit_check_columns_org UNIQUE (organization_id)
);

CREATE INDEX IF NOT EXISTS idx_org_audit_check_columns_org ON organization_audit_check_columns(organization_id);

COMMENT ON TABLE organization_audit_check_columns IS 'Per-organization configuration of which columns to verify during AI audit evidence matching.';
COMMENT ON COLUMN organization_audit_check_columns.transaction_checks IS 'JSONB object mapping transaction column names to check. e.g. {"origin_id": true, "destination_ids": true}';
COMMENT ON COLUMN organization_audit_check_columns.transaction_record_checks IS 'JSONB object mapping transaction_record column names to check. e.g. {"material_id": true, "origin_weight_kg": true, "total_amount": true}';
