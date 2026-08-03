-- ============================================================
-- Teardown for seed_gri306_mock.sql + seed_traceability_mock.sql
-- Removes ONLY the GRI 306 + traceability transport rows this seed created for
-- :target_org (tracked in reward_mock_seed_ids). Real data is never touched.
-- Run: psql "$DATABASE_URL" -v target_org=2783 -f scripts/unseed_gri_traceability_mock.sql
-- ============================================================
\set ON_ERROR_STOP on
\if :{?target_org}
\else
  \set target_org 2783
\endif
\echo 'Un-seeding GRI 306 + Traceability for org' :target_org

BEGIN;

-- Traceability (onward legs before roots due to self-FK parent_id)
DELETE FROM traceability_consolidation_sources WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_consol_source');
DELETE FROM traceability_consolidations         WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_consolidation');
DELETE FROM traceability_transport_transactions WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport') AND parent_id IS NOT NULL;
DELETE FROM traceability_transport_transactions WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport');

-- GRI 306 (gri306_2 references gri306_1 via approached_id -> delete first)
DELETE FROM gri306_2      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_2');
DELETE FROM gri306_1      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_1');
DELETE FROM gri306_3      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_3');
DELETE FROM gri306_export WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_export');

DELETE FROM reward_mock_seed_ids WHERE organization_id=:target_org
  AND entity IN ('trace_transport','trace_consolidation','trace_consol_source','gri306_1','gri306_2','gri306_3','gri306_export');

\echo 'Remaining GRI/trace registry rows for org (expect 0):'
SELECT COUNT(*) FROM reward_mock_seed_ids WHERE organization_id=:target_org
  AND entity IN ('trace_transport','trace_consolidation','trace_consol_source','gri306_1','gri306_2','gri306_3','gri306_export');

COMMIT;
