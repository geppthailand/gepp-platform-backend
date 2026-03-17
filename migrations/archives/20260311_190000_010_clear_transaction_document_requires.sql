-- Migration: Clear transaction_document_requires
-- Date: 2026-03-11
-- Description: Remove all transaction-level document type requirements.
--              Only record-level document requirements are used going forward.

-- Clear all existing transaction_document_requires data
UPDATE organization_audit_doc_require_types
SET transaction_document_requires = '[]'::jsonb,
    updated_date = NOW()
WHERE transaction_document_requires != '[]'::jsonb;

-- Also clear transaction_checks from organization_audit_check_columns
UPDATE organization_audit_check_columns
SET transaction_checks = '{}'::jsonb,
    updated_date = NOW()
WHERE transaction_checks != '{}'::jsonb;
