-- CRM Lead Management permissions — Sprint 9 Phase 2.
-- Seeded into system_permissions table.

INSERT INTO system_permissions (code, description, category)
VALUES
    ('sidebar.marketing.leads',           'View leads sidebar menu',              'sidebar'),
    ('feature.marketing.leads.manage',    'Create, view, update and delete leads','feature'),
    ('feature.marketing.leads.assign',    'Assign leads to team members',         'feature'),
    ('feature.marketing.leads.convert',   'Convert leads to users',               'feature'),
    ('feature.marketing.leads.import',    'Bulk-import leads via CSV',            'feature')
ON CONFLICT (code) DO UPDATE
    SET description = EXCLUDED.description,
        category    = EXCLUDED.category,
        updated_date = NOW();
