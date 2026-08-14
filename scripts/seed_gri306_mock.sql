-- ============================================================
-- GRI 306 (Waste) demo seed — derived from the org's REAL waste transactions
-- Target org via :target_org (default 2783 "Demo").
--
-- Feature: gepp-business-v3 /gri (3-step wizard 306-1/2/3). Tables gri306_1/2/3/export
-- are org-scoped via `organization`; created_by = user_locations.id. weight is stored
-- in KG (UI shows tonnes).
--
-- IMPORTANT render rules (from FE):
--   * gri306_1 renders only for output_material that ALSO appears in the org's
--     transaction_records for that record_year -> we key rows on real material_id.
--   * output_category = material_categories.id (NOT main_materials).
--   * a material is "fully allocated" when its 306-1 weights == transaction total
--     -> we insert one row per (year, material) carrying the full weight.
--   * gri306_2.approached_id must reference a real gri306_1.id (inner-joined) -> we
--     attach management rows to seeded 306-1 rows.
--   * method uses the 8 canonical FE values (diverted / directed to disposal).
--
-- Customer-ready (no visible markers). Idempotent via reward_mock_seed_ids registry.
-- Run: psql "$DATABASE_URL" -v target_org=2783 -f scripts/seed_gri306_mock.sql
-- ============================================================
\set ON_ERROR_STOP on
\if :{?target_org}
\else
  \set target_org 2783
\endif
\echo 'Seeding GRI 306 demo for org' :target_org

BEGIN;

CREATE TABLE IF NOT EXISTS reward_mock_seed_ids (
  id BIGSERIAL PRIMARY KEY, organization_id BIGINT NOT NULL,
  entity VARCHAR(40) NOT NULL, entity_id BIGINT NOT NULL,
  created_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cleanup prior GRI mock (children first: 306_2 references 306_1)
DELETE FROM gri306_2      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_2');
DELETE FROM gri306_1      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_1');
DELETE FROM gri306_3      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_3');
DELETE FROM gri306_export WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_export');
DELETE FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity IN ('gri306_1','gri306_2','gri306_3','gri306_export');

DROP TABLE IF EXISTS _gcfg;
CREATE TEMP TABLE _gcfg AS
SELECT (:target_org)::bigint AS org_id,
       (SELECT id FROM user_locations WHERE organization_id=:target_org AND is_user=TRUE AND deleted_date IS NULL ORDER BY id LIMIT 1) AS admin_id;

-- ------------------------------------------------------------
-- 306-1: one row per (record_year, material) carrying full transaction weight.
--        method/value-chain assigned by material_categories.id.
-- ------------------------------------------------------------
WITH agg AS (
  SELECT extract(year FROM t.transaction_date)::int AS yr, tr.material_id AS mat, tr.category_id AS cat,
         MAX(COALESCE(mt.name_th, mt.name_en)) AS matname,
         SUM(COALESCE(tr.origin_weight_kg,0)) AS kg
  FROM transaction_records tr
  JOIN transactions t ON t.id = tr.created_transaction_id AND t.organization_id = :target_org
  LEFT JOIN materials mt ON mt.id = tr.material_id
  WHERE tr.material_id IS NOT NULL AND tr.category_id IS NOT NULL
    AND extract(year FROM t.transaction_date) IN (2025,2026)
    AND COALESCE(tr.origin_weight_kg,0) > 0
  GROUP BY 1,2,3
),
catmap AS (
  SELECT * FROM (VALUES
    (1,'Recycling (Own)',           TRUE,  'Own Operation','คัดแยกและรีไซเคิลภายในองค์กร'),
    (2,'Recycle',                   FALSE, 'Downstream',   'รีไซเคิลขยะอิเล็กทรอนิกส์'),
    (3,'Composted by municipality', FALSE, 'Downstream',   'หมักทำปุ๋ยอินทรีย์'),
    (4,'Municipality receive',      FALSE, 'Downstream',   'เทศบาลรับไปกำจัด'),
    (5,'Other recover operation',   FALSE, 'Downstream',   'บำบัดของเสียอันตรายโดยผู้รับอนุญาต'),
    (6,'Incineration without energy',FALSE,'Downstream',   'เผาทำลายของเสียติดเชื้อ'),
    (7,'Other recover operation',   FALSE, 'Downstream',   'คัดแยกวัสดุก่อสร้าง'),
    (8,'Recycling (Own)',           TRUE,  'Own Operation','รีไซเคิลยาง'),
    (9,'Incineration with energy',  FALSE, 'Downstream',   'ผลิตพลังงานจากเชื้อเพลิงขยะ (RDF)')
  ) AS c(cat, method, onsite, vcp, activity)
),
ins AS (
  INSERT INTO gri306_1 (is_active, input_material, activity, output_material, output_category, method, onsite, weight, record_year, organization, created_by, value_chain_position, description, created_date, updated_date)
  SELECT TRUE,
         COALESCE(agg.matname,'วัสดุ'),
         COALESCE(cm.activity,'จัดการของเสีย'),
         agg.mat, agg.cat,
         COALESCE(cm.method,'Municipality receive'),
         COALESCE(cm.onsite, FALSE),
         round(agg.kg::numeric,1),
         agg.yr::text, :target_org, (SELECT admin_id FROM _gcfg),
         COALESCE(cm.vcp,'Downstream'),
         'บันทึกการจัดการของเสียตามมาตรฐาน GRI 306', NOW(), NOW()
  FROM agg LEFT JOIN catmap cm ON cm.cat = agg.cat
  RETURNING id
)
INSERT INTO reward_mock_seed_ids (organization_id, entity, entity_id) SELECT :target_org,'gri306_1',id FROM ins;

-- ------------------------------------------------------------
-- 306-2: ONE management approach per 306-1 activity (every row, both years) so the
--        306-2 step is fully complete (no activity left "pending an approach").
--        record_year matches the approached 306-1 row.
-- ------------------------------------------------------------
WITH src AS (
  SELECT g1.id, g1.record_year, row_number() OVER (ORDER BY g1.id) AS rn
  FROM gri306_1 g1
  WHERE g1.organization=:target_org
    AND g1.id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_1')
),
ins AS (
  INSERT INTO gri306_2 (is_active, approached_id, prevention_action, verify_method, collection_method, record_year, organization, created_by, created_date, updated_date)
  SELECT TRUE, s.id,
    (ARRAY['Eco-design / Redesign, Internal Reuse, Supply Chain Collaboration','Lean Production, Internal Reuse','Eco-design / Redesign, Supply Chain Collaboration','Internal Reuse, Lean Production'])[1 + (s.rn % 4)],
    (ARRAY['License Check, Site Audit, Manifest Check','Manifest Check','License Check','License Check, Site Audit'])[1 + (s.rn % 4)],
    (ARRAY['Weighing (ชั่งน้ำหนัก)','Provider Data (ข้อมูลผู้รับ)'])[1 + (s.rn % 2)],
    s.record_year, :target_org, (SELECT admin_id FROM _gcfg), NOW(), NOW()
  FROM src s
  RETURNING id
)
INSERT INTO reward_mock_seed_ids (organization_id, entity, entity_id) SELECT :target_org,'gri306_2',id FROM ins;

-- ------------------------------------------------------------
-- 306-3: significant spills (2026)
-- ------------------------------------------------------------
WITH ins AS (
  INSERT INTO gri306_3 (is_active, spill_type, surface_type, location, volume, unit, cleanup_cost, record_year, organization, created_by, created_date, updated_date)
  SELECT TRUE, x.st, x.sf, x.loc, x.vol, 'Liters', x.cost, x.yr, :target_org, (SELECT admin_id FROM _gcfg), NOW(), NOW()
  FROM (VALUES
    ('Fuel Spills','Soil','โรงคัดแยก จ.ระยอง',120, 15000,'2026'),
    ('Oil Spills','Water','คลังสินค้าส่วนกลาง',45, 8000,'2026')
  ) AS x(st, sf, loc, vol, cost, yr)
  RETURNING id
)
INSERT INTO reward_mock_seed_ids (organization_id, entity, entity_id) SELECT :target_org,'gri306_3',id FROM ins;

-- ------------------------------------------------------------
-- 306 export versions
-- ------------------------------------------------------------
WITH ins AS (
  INSERT INTO gri306_export (is_active, version, export_file_url, record_year, organization, created_by, created_date, updated_date)
  SELECT TRUE, x.v, NULL, x.yr, :target_org, (SELECT admin_id FROM _gcfg), NOW(), NOW()
  FROM (VALUES ('v1.0','2025'), ('v1.0','2026')) AS x(v, yr)
  RETURNING id
)
INSERT INTO reward_mock_seed_ids (organization_id, entity, entity_id) SELECT :target_org,'gri306_export',id FROM ins;

-- ------------------------------------------------------------
-- Summary + render-gate check
-- ------------------------------------------------------------
\echo ''
\echo 'GRI 306 seed counts:'
SELECT 'gri306_1' tbl, COUNT(*) FROM gri306_1 WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_1')
UNION ALL SELECT 'gri306_2', COUNT(*) FROM gri306_2 WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_2')
UNION ALL SELECT 'gri306_3', COUNT(*) FROM gri306_3 WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_3')
UNION ALL SELECT 'gri306_export', COUNT(*) FROM gri306_export WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_export')
ORDER BY tbl;

\echo ''
\echo '306-1 waste by year x method (tonnes) — should split diverted vs directed:'
SELECT record_year, method, round((SUM(weight)/1000)::numeric,2) AS tonnes
FROM gri306_1 WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_1')
GROUP BY record_year, method ORDER BY record_year, tonnes DESC;

\echo ''
\echo 'Render-gate: every seeded 306-1 output_material present in transaction_records for its year? (unmatched should be 0)'
SELECT g.record_year, COUNT(*) AS unmatched
FROM gri306_1 g
WHERE g.id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='gri306_1')
  AND NOT EXISTS (
    SELECT 1 FROM transaction_records tr JOIN transactions t ON t.id=tr.created_transaction_id AND t.organization_id=:target_org
    WHERE tr.material_id=g.output_material AND extract(year FROM t.transaction_date)::text=g.record_year)
GROUP BY g.record_year;

COMMIT;
