-- ============================================================
-- Undo scripts/seed_esg_mock.sql for one organization.
--
-- Removes ONLY rows recorded in the esg_mock_seed_ids registry, so anything
-- a human or the app created in the same tables is left untouched.
--
-- Run: psql "$DATABASE_URL" -v target_org=2783 -f scripts/unseed_esg_mock.sql
-- ============================================================
\set ON_ERROR_STOP on
\if :{?target_org}
\else
  \set target_org 2783
\endif
\echo 'Removing GEPP-ESG demo seed for org' :target_org

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                 WHERE table_schema='public' AND table_name='esg_mock_seed_ids') THEN
    RAISE EXCEPTION 'esg_mock_seed_ids registry not found — nothing was seeded by this script';
  END IF;
END $$;

\echo '── about to delete ──'
SELECT entity, count(*) AS rows
FROM esg_mock_seed_ids WHERE organization_id = :target_org
GROUP BY entity ORDER BY entity;

-- Children before parents.
DELETE FROM esg_xbrl_report_values      WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_xbrl_report_values');
DELETE FROM esg_supplier_chasers        WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_supplier_chasers');
DELETE FROM esg_supplier_magic_links    WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_supplier_magic_links');
DELETE FROM esg_supplier_submissions    WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_supplier_submissions');
DELETE FROM esg_scope3_entries          WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_scope3_entries');
DELETE FROM esg_suppliers               WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_suppliers');
DELETE FROM esg_cbam_reports            WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_cbam_reports');
DELETE FROM esg_cbam_products           WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_cbam_products');
DELETE FROM esg_macc_initiatives        WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_macc_initiatives');
DELETE FROM esg_records                 WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_records');
DELETE FROM esg_documents               WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_documents');
DELETE FROM esg_organization_data_extraction WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_organization_data_extraction');
DELETE FROM esg_line_messages           WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_line_messages');
DELETE FROM esg_materiality_submissions WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_materiality_submissions');
DELETE FROM esg_user_materiality        WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_user_materiality');
DELETE FROM esg_external_invitation_links WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_external_invitation_links');
DELETE FROM esg_external_platform_binding WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_external_platform_binding');
DELETE FROM esg_users                   WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_users');
DELETE FROM esg_organization_setup      WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_organization_setup');
DELETE FROM esg_organization_settings   WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids WHERE organization_id=:target_org AND entity='esg_organization_settings');

DELETE FROM esg_mock_seed_ids WHERE organization_id = :target_org;

\echo '── remaining ESG rows for this org (should be 0 unless created outside the seed) ──'
SELECT 'esg_records' AS t, count(*) FROM esg_records WHERE organization_id = :target_org
UNION ALL SELECT 'esg_suppliers', count(*) FROM esg_suppliers WHERE organization_id = :target_org
UNION ALL SELECT 'esg_documents', count(*) FROM esg_documents WHERE organization_id = :target_org
UNION ALL SELECT 'esg_settings', count(*) FROM esg_organization_settings WHERE organization_id = :target_org;

COMMIT;
\echo 'DONE — seed removed for org' :target_org
