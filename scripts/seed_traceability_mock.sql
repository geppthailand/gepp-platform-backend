-- ============================================================
-- Traceability demo seed — builds a transport flow over the org's EXISTING groups
-- Target org via :target_org (default 2783 "Demo").
--
-- org 2783 already has ~239 traceability_transaction_group rows (auto-generated from
-- its real transactions) but an empty transport tree, so the Traceability "Summary"
-- tree and the kanban In-Transit/Destination columns render empty. This seed
-- hand-inserts (option b) a consistent 2-level transport flow:
--   root leg   : origin (collection floor) -> hub (Branch 1), status 'arrived', is_root
--   onward leg : hub -> processor/recycler (Building 1), terminal (disposal_method set)
-- Weight per group = SUM(transaction_records.origin_weight_kg) for that group.
-- absolute_percentage: root=100; single onward child=100 (100 * w/Σsiblings).
--
-- Customer-ready (no markers). Idempotent via reward_mock_seed_ids registry.
-- Does NOT touch the org's pre-existing transport rows or its groups/transactions.
-- Run: psql "$DATABASE_URL" -v target_org=2783 -f scripts/seed_traceability_mock.sql
-- ============================================================
\set ON_ERROR_STOP on
\if :{?target_org}
\else
  \set target_org 2783
\endif
\echo 'Seeding Traceability transport flow for org' :target_org

BEGIN;

CREATE TABLE IF NOT EXISTS reward_mock_seed_ids (
  id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL,
  entity VARCHAR(40) NOT NULL, entity_id BIGINT NOT NULL,
  created_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cleanup prior mock (children/onward legs before roots due to self-FK parent_id)
DELETE FROM traceability_consolidation_sources WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_consol_source');
DELETE FROM traceability_consolidations         WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_consolidation');
DELETE FROM traceability_transport_transactions WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport') AND parent_id IS NOT NULL;
DELETE FROM traceability_transport_transactions WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport');
DELETE FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity IN ('trace_transport','trace_consolidation','trace_consol_source');

-- Resolve hub + processor destinations (org's own locations)
DROP TABLE IF EXISTS _tcfg;
CREATE TEMP TABLE _tcfg AS
SELECT (:target_org)::bigint AS org_id,
       (SELECT id FROM user_locations WHERE organization_id=:target_org AND is_location=TRUE AND deleted_date IS NULL ORDER BY id LIMIT 1)        AS hub_id,
       (SELECT id FROM user_locations WHERE organization_id=:target_org AND is_location=TRUE AND deleted_date IS NULL ORDER BY id OFFSET 1 LIMIT 1) AS proc_id;

DO $$
BEGIN
  IF (SELECT hub_id FROM _tcfg) IS NULL THEN RAISE EXCEPTION 'No org location to use as transport hub/destination'; END IF;
END $$;

-- All 2026 groups that carry weight, ALL months (Jan–Jun) so every month shows flow
DROP TABLE IF EXISTS _grp;
CREATE TEMP TABLE _grp AS
SELECT g.id AS group_id, g.origin_id, g.material_id,
       COALESCE((SELECT SUM(tr.origin_weight_kg) FROM transaction_records tr WHERE tr.id = ANY(g.transaction_record_id)), 0) AS kg
FROM traceability_transaction_group g
WHERE g.organization_id = :target_org AND g.transaction_year = 2026 AND g.origin_id IS NOT NULL AND g.material_id IS NOT NULL;
DELETE FROM _grp WHERE kg <= 0;

-- Root legs: collection origin -> hub, arrived
WITH ins AS (
  INSERT INTO traceability_transport_transactions
    (is_active, organization_id, transaction_group_id, origin_id, destination_id, material_id, weight, status, arrival_date, is_root, parent_id, absolute_percentage, created_date, updated_date)
  SELECT TRUE, :target_org, group_id, origin_id, (SELECT hub_id FROM _tcfg), material_id, round(kg::numeric,1),
         'arrived', NOW() - ((random()*40)::int || ' days')::interval, TRUE, NULL, 100, NOW(), NOW()
  FROM _grp
  RETURNING id
)
INSERT INTO reward_mock_seed_ids (organization_id, entity, entity_id) SELECT :target_org,'trace_transport',id FROM ins;

-- Onward legs: hub -> processor/recycler for ~half the roots (terminal, disposal_method set)
DROP TABLE IF EXISTS _roots;
CREATE TEMP TABLE _roots AS
SELECT tt.id AS root_id, tt.transaction_group_id, tt.destination_id, tt.material_id, tt.weight,
       row_number() OVER (ORDER BY tt.id) AS rn
FROM traceability_transport_transactions tt
WHERE tt.organization_id=:target_org AND tt.is_root
  AND tt.id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport');

WITH ins AS (
  INSERT INTO traceability_transport_transactions
    (is_active, organization_id, transaction_group_id, origin_id, destination_id, material_id, weight, status, arrival_date, is_root, parent_id, absolute_percentage, disposal_method, created_date, updated_date)
  SELECT TRUE, :target_org, r.transaction_group_id, r.destination_id, (SELECT proc_id FROM _tcfg), r.material_id, r.weight,
         'arrived', NOW() - ((random()*15)::int || ' days')::interval, FALSE, r.root_id, 100,
         (ARRAY['Recycling (Own)','Recycle','Incineration with energy','Composted by municipality'])[1 + (r.rn % 4)],
         NOW(), NOW()
  FROM _roots r
  WHERE r.rn % 2 = 0 AND (SELECT proc_id FROM _tcfg) IS NOT NULL
  RETURNING id
)
INSERT INTO reward_mock_seed_ids (organization_id, entity, entity_id) SELECT :target_org,'trace_transport',id FROM ins;

-- ------------------------------------------------------------
-- Summary
-- ------------------------------------------------------------
\echo ''
\echo 'Traceability seed summary:'
SELECT 'root_transports'  AS kind, COUNT(*) FROM traceability_transport_transactions
  WHERE organization_id=:target_org AND is_root AND id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport')
UNION ALL SELECT 'onward_transports', COUNT(*) FROM traceability_transport_transactions
  WHERE organization_id=:target_org AND NOT is_root AND id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport')
UNION ALL SELECT 'groups_now_with_transport', COUNT(DISTINCT transaction_group_id) FROM traceability_transport_transactions
  WHERE organization_id=:target_org AND id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport');

\echo ''
\echo 'Transport weight by material (kg) + hub/processor used:'
SELECT COALESCE(mt.name_en,'?') material, round(SUM(tt.weight)::numeric,0) kg, COUNT(*) legs
FROM traceability_transport_transactions tt LEFT JOIN materials mt ON mt.id=tt.material_id
WHERE tt.organization_id=:target_org AND tt.id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='trace_transport')
GROUP BY 1 ORDER BY kg DESC;
SELECT 'hub_id='||hub_id||' proc_id='||COALESCE(proc_id::text,'NULL') FROM _tcfg;

COMMIT;
