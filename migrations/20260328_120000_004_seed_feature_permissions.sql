-- Seed granular feature permissions for complex pages:
-- Reports (5 tabs), Traceability (2 modes), GRI (3 actions), Locations (5 tabs/sub-tabs)

INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    -- Reports tab permissions
    ('feature.reports.overview', 'Reports Overview', 'Access to Reports Overview tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.reports.performance', 'Reports Performance', 'Access to Reports Performance tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.reports.trend_analysis', 'Reports Trend Analysis', 'Access to Reports Trend Analysis tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.reports.materials', 'Reports Materials', 'Access to Reports Materials tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.reports.waste_diversion', 'Reports Waste Diversion', 'Access to Reports Waste Diversion tab', 'accessibility', TRUE, NOW(), NOW()),
    -- Traceability mode permissions
    ('feature.traceability.manage', 'Traceability Manage', 'Access to Traceability Kanban manage mode', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.traceability.summary', 'Traceability Summary', 'Access to Traceability summary/hierarchy view', 'accessibility', TRUE, NOW(), NOW()),
    -- GRI action permissions
    ('feature.gri.create_version', 'GRI Create Version', 'Ability to create GRI report versions', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.gri.export', 'GRI Export', 'Ability to export GRI data', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.gri.delete_version', 'GRI Delete Version', 'Ability to delete GRI report versions', 'accessibility', TRUE, NOW(), NOW()),
    -- Locations tab permissions
    ('feature.locations.structure', 'Locations Structure', 'Access to Organization Chart tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.locations.members', 'Locations Members', 'Access to Members/user management sub-tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.locations.tags', 'Locations Tags', 'Access to Location tag management sub-tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.locations.qr_input', 'Locations QR Input', 'Access to QR Input management sub-tab', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.locations.notifications', 'Locations Notifications', 'Access to Notification settings sub-tab', 'accessibility', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;
