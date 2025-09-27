-- Migration: Add deleted_date columns to tables that are missing them
-- Date: 2025-01-09
-- Description: Add deleted_date columns to support soft delete functionality across all main tables

-- Core foundation tables
ALTER TABLE location_countries ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE location_regions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE location_provinces ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE location_districts ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE location_subdistricts ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE banks ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE currencies ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE nationalities ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE phone_number_country_codes ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE material_mains ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE materials ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE locales ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- User management tables
ALTER TABLE user_roles ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_business_roles ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_locations ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_input_channels ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_analytics ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_organization_roles ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_point_balances ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- Organization and subscription tables
ALTER TABLE organization_info ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE system_permissions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE organization_permissions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE organization_roles ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE subscription_permissions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- EPR compliance tables
ALTER TABLE epr_programs ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_registrations ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_targets ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_reports ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_payments ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_data_submissions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_audits ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE epr_notifications ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- Transaction system tables
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE transaction_items ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE transaction_payments ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE transaction_documents ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE transaction_analytics ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE transaction_status_history ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE waste_collections ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE waste_processing ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- GRI and rewards tables
ALTER TABLE gri_reports ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE gri_indicators ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE gri_standards ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE gri_report_data ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE reward_redemptions ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE rewards_catalog ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE km_files ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE km_chunks ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- Chat system tables
ALTER TABLE experts ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE chats ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE meeting_participants ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- Audit and logging tables
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE platform_logs ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE system_events ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMP WITH TIME ZONE;

-- Create indexes for better query performance on deleted_date columns
-- Core tables
CREATE INDEX IF NOT EXISTS idx_user_locations_deleted_date ON user_locations(deleted_date);
CREATE INDEX IF NOT EXISTS idx_user_roles_deleted_date ON user_roles(deleted_date);
CREATE INDEX IF NOT EXISTS idx_user_business_roles_deleted_date ON user_business_roles(deleted_date);
CREATE INDEX IF NOT EXISTS idx_organizations_deleted_date ON organizations(deleted_date);

-- Transaction tables (high volume)
CREATE INDEX IF NOT EXISTS idx_transactions_deleted_date ON transactions(deleted_date);
CREATE INDEX IF NOT EXISTS idx_transaction_items_deleted_date ON transaction_items(deleted_date);

-- Audit tables (high volume)
CREATE INDEX IF NOT EXISTS idx_audit_logs_deleted_date ON audit_logs(deleted_date);
CREATE INDEX IF NOT EXISTS idx_platform_logs_deleted_date ON platform_logs(deleted_date);

-- Chat tables
CREATE INDEX IF NOT EXISTS idx_chat_history_deleted_date ON chat_history(deleted_date);
CREATE INDEX IF NOT EXISTS idx_experts_deleted_date ON experts(deleted_date);