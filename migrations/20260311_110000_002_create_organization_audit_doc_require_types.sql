-- Migration: Create organization_audit_doc_require_types table
-- Date: 2026-03-11
-- Description: Per-organization required document types for AI audit

CREATE TABLE IF NOT EXISTS organization_audit_doc_require_types (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    transaction_document_requires JSONB NOT NULL DEFAULT '[]'::jsonb,
    record_document_requires JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    CONSTRAINT uq_org_audit_doc_require_org UNIQUE (organization_id)
);

CREATE INDEX IF NOT EXISTS idx_org_audit_doc_require_org ON organization_audit_doc_require_types(organization_id);

COMMENT ON TABLE organization_audit_doc_require_types IS 'Per-organization configuration of required document types for AI audit. If no record exists for an org, no documents are required.';
COMMENT ON COLUMN organization_audit_doc_require_types.transaction_document_requires IS 'JSONB array of ai_audit_document_types IDs required at the transaction level. e.g. [1, 4]';
COMMENT ON COLUMN organization_audit_doc_require_types.record_document_requires IS 'JSONB array of ai_audit_document_types IDs required at the transaction_record level. e.g. [4, 5]';
