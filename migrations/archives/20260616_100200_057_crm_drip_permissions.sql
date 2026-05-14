-- Sprint 10: CRM Drip Sequence permissions
-- Migration: 20260616_100200_057_crm_drip_permissions.sql

INSERT INTO system_permissions (code, description, category, created_date, updated_date)
VALUES
    ('sidebar.marketing.drip',      'Drip Sequences sidebar item', 'sidebar',  NOW(), NOW()),
    ('feature.marketing.drip.manage', 'Manage drip sequences',      'feature',  NOW(), NOW())
ON CONFLICT (code) DO NOTHING;
