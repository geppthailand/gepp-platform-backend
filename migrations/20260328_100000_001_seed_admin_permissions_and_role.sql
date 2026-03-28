-- ============================================================================
-- Migration: Add platform_role column and seed system permissions for v3 admin
-- Date: 2026-03-28
-- Description:
--   1. Adds platform_role column to user_locations for admin role identification
--   2. Seeds system_permissions with all v3 frontend pages and features
-- ============================================================================

-- 1. Add platform_role column to user_locations
ALTER TABLE user_locations ADD COLUMN IF NOT EXISTS platform_role VARCHAR(50) DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_user_locations_platform_role ON user_locations(platform_role);

-- 2. Seed system permissions for v3 frontend

-- Sidebar permissions
INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    ('sidebar.dashboard', 'Dashboard', 'Access to Dashboard page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.reports', 'Reports', 'Access to Reports page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.waste_transactions', 'Waste Transactions', 'Access to Waste Transactions page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.traceability', 'Traceability', 'Access to Traceability page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.cost_management', 'Cost Management', 'Access to Cost Management page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.locations', 'Locations', 'Access to Locations page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.users', 'Users', 'Access to Users page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.rewards', 'Rewards', 'Access to Rewards page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.gri', 'GRI', 'Access to GRI Reporting page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.profile', 'Profile', 'Access to Profile page', 'sidebar', TRUE, NOW(), NOW()),
    ('sidebar.notifications', 'Notifications', 'Access to Notifications page', 'sidebar', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;

-- Feature/accessibility permissions
INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    ('feature.waste_transactions.ai_audit', 'AI Audit', 'Access to AI Audit feature in Waste Transactions', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.waste_transactions.manual_audit', 'Manual Audit', 'Access to Manual Audit feature in Waste Transactions', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.waste_transactions.audit_rules', 'Audit Rules', 'Access to Audit Rules management', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.waste_transactions.logistics', 'Logistics', 'Access to Logistics board', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.waste_transactions.export', 'Export Transactions', 'Ability to export transaction data', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.overview', 'Rewards Overview', 'Access to Rewards Overview tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.campaigns', 'Reward Campaigns', 'Access to Reward Campaigns management', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.inventory', 'Reward Inventory', 'Access to Reward Inventory management', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.members', 'Reward Members', 'Access to Reward Members management', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.drop_points', 'Reward Drop Points', 'Access to Reward Drop Points management', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.settings', 'Reward Settings', 'Access to Reward Settings', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.rewards.materials_activities', 'Materials & Activities', 'Access to Materials & Activities in Rewards', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.reports.export', 'Export Reports', 'Ability to export report data', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.traceability.view', 'View Traceability', 'Access to view traceability data', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.cost_management.view', 'View Cost Management', 'Access to view cost management data', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.locations.manage', 'Manage Locations', 'Ability to create/edit/delete locations', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.users.manage', 'Manage Users', 'Ability to create/edit/delete users', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.gri.view', 'View GRI', 'Access to view GRI reporting data', 'accessibility', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;

-- General settings permissions
INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    ('settings.organization_setup', 'Organization Setup', 'Access to organization setup and configuration', 'general_settings', TRUE, NOW(), NOW()),
    ('settings.notification_settings', 'Notification Settings', 'Access to notification configuration', 'general_settings', TRUE, NOW(), NOW()),
    ('settings.audit_settings', 'Audit Settings', 'Access to audit configuration', 'general_settings', TRUE, NOW(), NOW()),
    ('settings.api_settings', 'API Settings', 'Access to API and integration settings', 'general_settings', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;

-- Overview permissions
INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    ('overview.dashboard', 'Dashboard Overview', 'Access to dashboard overview widgets', 'overview', TRUE, NOW(), NOW()),
    ('overview.reports', 'Reports Overview', 'Access to reports overview widgets', 'overview', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;
