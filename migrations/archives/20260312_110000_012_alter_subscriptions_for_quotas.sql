-- Migration: Alter subscriptions table for quota system
-- Date: 2026-03-12
-- Description: Add duration_type and allow_ai_audit_exceed_quota columns.
--              Remove usage columns (now tracked in subscription_monthly_quotas).

ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS duration_type VARCHAR(20) NOT NULL DEFAULT 'monthly';
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS allow_ai_audit_exceed_quota BOOLEAN NOT NULL DEFAULT FALSE;

-- Remove usage columns — now tracked per-period in subscription_monthly_quotas
ALTER TABLE subscriptions DROP COLUMN IF EXISTS ai_audit_usage;
ALTER TABLE subscriptions DROP COLUMN IF EXISTS create_transaction_usage;
