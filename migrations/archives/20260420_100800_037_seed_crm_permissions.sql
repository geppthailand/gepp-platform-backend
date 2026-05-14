-- CRM / Marketing: seed permissions consumed by Marketing tab UI + backend endpoints

INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    ('sidebar.marketing', 'Marketing', 'Access to Marketing tab (v3 backoffice)', 'sidebar', TRUE, NOW(), NOW()),
    ('feature.marketing.view', 'View Marketing', 'Access to Marketing module (any sub-feature)', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.analytics.view', 'View CRM Analytics', 'View usage analytics dashboards', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.segments.manage', 'Manage Segments', 'Create/edit/delete user segments', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.templates.manage', 'Manage Email Templates', 'Create/edit/delete email templates', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.campaigns.manage', 'Manage Campaigns', 'Create/start/pause campaigns', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.email_lists.manage', 'Manage Email Lists', 'Create/edit per-org email CC lists', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.ai.generate', 'AI Template Generation', 'Use AI to generate email templates (rate-limited)', 'accessibility', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;
