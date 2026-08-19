-- ============================================================
-- GEPP-ESG demo seed — full-dimension mock for one organization
--
-- Target org via :target_org (default 2783 "Demo", login watth.test@geppdata.com).
-- Plan + rationale: scripts/ESG_PROD_MOCK_PLAN.md
--
-- IMPORTANT modelling rules (derived from the reading services):
--   * Scope 3 donut  → esg_dashboard_service._scope3_breakdown joins
--     EsgRecord.category_id = esg_data_category.id WHERE is_scope3 AND
--     scope3_category_id IS NOT NULL. So Scope 3 rows MUST use
--     category_id 27..41, NOT category_id 3.
--   * Data Warehouse tree → esg_service.get_data_warehouse_hierarchy walks
--     datapoints[].datapoint_id against esg_datapoint.id. The 15 Scope 3
--     categories own no datapoints, so Scope 3 rows carry category_id 27..41
--     (for the donut) but a datapoint_id from subcategories 6..20 under
--     category 3 (for the tree). The taxonomy stores the 15 categories twice;
--     each copy feeds a different view.
--   * pillar is CHAR(1) — 'E'/'S'/'G', copied from esg_data_category.pillar.
--   * kgco2e is in KILOGRAMS. The dashboard divides by 1000.
--   * Vocabularies: ghg_status computed|insufficient|method_unknown ·
--     ghg_method activity_ef|spend_based · status VERIFIED|PENDING_VERIFY ·
--     entry_source LIFF_MANUAL|LINE_CHAT.
--
-- Deterministic: no random() anywhere, so re-runs produce identical data.
-- Idempotent via the esg_mock_seed_ids registry (own rows deleted first).
-- Customer-ready: no TEST/MOCK markers in any user-visible field. TH + EN.
--
-- Run: psql "$DATABASE_URL" -v target_org=2783 -f scripts/seed_esg_mock.sql
-- Undo: psql "$DATABASE_URL" -v target_org=2783 -f scripts/unseed_esg_mock.sql
-- ============================================================
\set ON_ERROR_STOP on
\if :{?target_org}
\else
  \set target_org 2783
\endif
-- Product scope is Scope 3 only, so the S / G / non-carbon-E disclosure block
-- (§5) is OFF by default: seeding it makes the Data Warehouse tree read as a
-- full three-pillar ESG product. Turn on with -v include_disclosures=1 if the
-- scope ever widens back out.
\if :{?include_disclosures}
\else
  \set include_disclosures 0
\endif
\timing off
\echo 'Seeding GEPP-ESG demo for org' :target_org

BEGIN;

-- ------------------------------------------------------------
-- 0. Registry + cleanup of any prior run (children first)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS esg_mock_seed_ids (
  id BIGSERIAL PRIMARY KEY,
  organization_id BIGINT NOT NULL,
  entity VARCHAR(48) NOT NULL,
  entity_id BIGINT NOT NULL,
  created_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS esg_mock_seed_ids_org_entity_idx
  ON esg_mock_seed_ids (organization_id, entity);

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
DELETE FROM esg_mock_seed_ids WHERE organization_id=:target_org;

-- ------------------------------------------------------------
-- 1. Config: the admin user + org-level ESG settings
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _cfg;
CREATE TEMP TABLE _cfg AS
SELECT (:target_org)::bigint AS org_id,
       (SELECT id FROM user_locations
         WHERE organization_id = :target_org AND is_user = TRUE
           AND deleted_date IS NULL
         ORDER BY (lower(email) = 'watth.test@geppdata.com') DESC, id
         LIMIT 1) AS admin_id;

DO $$
BEGIN
  IF (SELECT admin_id FROM _cfg) IS NULL THEN
    RAISE EXCEPTION 'No is_user row in user_locations for org % — cannot seed', (SELECT org_id FROM _cfg);
  END IF;
END $$;

-- base_year + reduction target are what make the trajectory, SBTi alignment
-- and the praise rules produce any output at all.
WITH ins AS (
  INSERT INTO esg_organization_settings (
    organization_id, reporting_year, methodology, organizational_boundary,
    base_year, reduction_target_percent, reduction_target_year,
    focus_mode, enabled_scope3_categories, is_active, created_date)
  SELECT org_id, 2026, 'ghg_protocol', 'operational_control',
         2023, 30, 2030,
         -- Scope-3-only product scope. Must match VITE_FOCUS_MODE on the
         -- frontend build, which drives FocusGate + the category whitelist.
         'scope3_only', '[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]'::jsonb,
         TRUE, '2026-01-08 09:00+07'
  FROM _cfg
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_organization_settings', id FROM ins;

WITH ins AS (
  INSERT INTO esg_organization_setup (
    organization_id, industry_sector, employee_count, revenue_currency,
    annual_revenue, reporting_framework, fiscal_year_start,
    auto_extract_enabled, notification_enabled, is_active, created_date)
  SELECT org_id, 'manufacturing', 420, 'THB',
         1850000000, 'gri', 1, TRUE, TRUE, TRUE, '2026-01-08 09:00+07'
  FROM _cfg
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_organization_setup', id FROM ins;

-- ------------------------------------------------------------
-- 2. Emission narrative — annual targets in KG CO2e
--
--    3 consecutive reduction years so "Sustained Reducer" fires;
--    Scope 3 ~68% of total so the supply-chain recommendation fires
--    while Scope 2 stays big enough to justify the renewable one.
--    2026 is partial (Jan–Aug) so deadline/data-gap rules have input.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _years;
CREATE TEMP TABLE _years (y int, n_months int, s1_kg numeric, s2_kg numeric, s3_kg numeric);
-- Shares are tuned against the *graded* thresholds in
-- services/esg/esg_insight_engine.py so the dashboard insight cards populate:
--   s3_pct > 50  → supplier-engagement opportunity
--   s2_pct > 25  → renewable procurement (PPA/REC) opportunity
--   yoy   < -5%  → "keep the momentum" praise, 3 years running
-- Note ~1/13 of Scope 3 rows are deliberately left un-costed (see §4), so the
-- realised Scope 3 total lands ~4% below the figure below. That is intentional.
INSERT INTO _years VALUES
  (2023, 12, 2050000, 6300000, 14100000),
  (2024, 12, 1960000, 5900000, 13600000),
  (2025, 12, 1880000, 5500000, 13050000),
  (2026,  8, 1180000, 3400000,  8240000);

-- Seasonal shape, always positive. Normalised per (year, series) by a window
-- sum below, which guarantees the annual totals land exactly on target.
CREATE OR REPLACE FUNCTION _mseason(m int) RETURNS numeric LANGUAGE sql IMMUTABLE AS
$$ SELECT 1 + 0.16 * cos(2*pi()*(m-1)/12.0) + 0.05 * sin(2*pi()*(m-1)/6.0) $$;

-- Deterministic spread in [0,1) — replaces random() so re-runs are identical.
CREATE OR REPLACE FUNCTION _det(n bigint) RETURNS numeric LANGUAGE sql IMMUTABLE AS
$$ SELECT (mod(n * 7919, 997))::numeric / 997 $$;

-- ------------------------------------------------------------
-- 3. Scope 1 + Scope 2 records (category_id 1 and 2)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _direct;
CREATE TEMP TABLE _direct (
  cat_id int, sub_id int, dp_id int, unit text, share numeric, ef numeric,
  label_th text, label_en text, src text);
INSERT INTO _direct VALUES
  (1,  1, 130, 'hours',  0.46, 52.0,    'ชั่วโมงเดินเครื่องหม้อไอน้ำ', 'Boiler operating hours',   'TGO Emission Factor 2022'),
  (1,  2, 148, 'liters', 0.31, 2.681,   'น้ำมันดีเซลรถขนส่งภายใน',     'Fleet diesel consumption', 'TGO Emission Factor 2022'),
  (1,  3, 162, 'kg',     0.15, 2088.0,  'สารทำความเย็นที่เติมชดเชย',    'Refrigerant top-up (R-410A)', 'IPCC AR6 GWP100'),
  (1, 51, 374, 'tonnes', 0.08, 180.0,   'ปริมาณการผลิต (ก๊าซจากกระบวนการ)', 'Production volume (process emissions)', 'TGO Emission Factor 2022'),
  (2,  4, 163, 'kWh',    0.88, 0.4999,  'ค่าไฟฟ้าที่ซื้อจากกริด',       'Purchased grid electricity', 'TGO Grid EF 2022'),
  (2,  5, 179, 'kWh',    0.12, 0.2300,  'ไอน้ำที่ซื้อจากภายนอก',        'Purchased steam',           'TGO Emission Factor 2022');

WITH grid AS (
  SELECT d.*, y.y, m.m,
         CASE WHEN d.cat_id = 1 THEN y.s1_kg ELSE y.s2_kg END AS series_kg
  FROM _direct d
  CROSS JOIN _years y
  CROSS JOIN LATERAL generate_series(1, y.n_months) AS m(m)
), weighted AS (
  SELECT g.*,
         _mseason(g.m) AS w,
         SUM(_mseason(g.m)) OVER (PARTITION BY g.y, g.cat_id, g.sub_id) AS w_tot
  FROM grid g
), calc AS (
  SELECT w.*,
         ROUND(w.series_kg * w.share * w.w / w.w_tot, 2) AS kg,
         (ROW_NUMBER() OVER (ORDER BY w.y, w.m, w.cat_id, w.sub_id))::int AS rn
  FROM weighted w
), ins AS (
  INSERT INTO esg_records (
    organization_id, user_id, category_id, subcategory_id, scope3_category_id,
    pillar, record_label, entry_date, datapoints, kgco2e,
    ghg_status, ghg_method, ghg_missing_fields,
    ghg_source_name, ghg_source_url, ghg_ef_value, ghg_ef_unit,
    status, entry_source, is_active, created_date)
  SELECT c.org_id, c.admin_id, calc.cat_id, calc.sub_id, NULL,
         'E',
         calc.label_th || ' — ' || to_char(make_date(calc.y, calc.m, 1), 'Mon YYYY'),
         make_date(calc.y, calc.m, 2 + (mod(calc.rn * 7, 24))::int),
         -- Every numeric datapoint under the subcategory, so the Data Warehouse
         -- tree fills instead of showing one leaf per branch. The representative
         -- datapoint carries the exact activity value that backs kgco2e; the
         -- siblings get a deterministic derived value in their own unit.
         (SELECT jsonb_agg(jsonb_build_object(
             'datapoint_id', d.id,
             'datapoint_name', d.name,
             'canonical_name', CASE COALESCE(d.unit, '') WHEN 'kWh' THEN 'energy_kwh'
                                                         WHEN 'liters' THEN 'volume_litres'
                                                         WHEN 'kg' THEN 'weight_kg'
                                                         ELSE NULL END,
             'is_canonical', COALESCE(d.unit, '') IN ('kWh','liters','kg'),
             'value', CASE WHEN d.id = calc.dp_id
                           THEN ROUND(calc.kg / calc.ef, 2)
                           ELSE ROUND((calc.kg / calc.ef) * (0.18 + _det(d.id) * 0.9), 2) END,
             'unit', COALESCE(d.unit, 'unit'),
             'confidence', 1.0,
             'tags', jsonb_build_array()) ORDER BY d.sort_order, d.id)
          FROM esg_datapoint d
          WHERE d.esg_data_subcategory_id = calc.sub_id
            AND d.is_active AND d.data_type = 'numeric'),
         calc.kg,
         'computed', 'activity_ef', '[]'::jsonb,
         calc.src, 'https://thaicarbonlabel.tgo.or.th/',
         ROUND(calc.ef / 1000.0, 9), 'tCO2e/' || calc.unit,
         CASE WHEN mod(calc.rn, 7) = 0 THEN 'PENDING_VERIFY' ELSE 'VERIFIED' END,
         CASE WHEN mod(calc.rn, 3) = 0 THEN 'LINE_CHAT' ELSE 'LIFF_MANUAL' END,
         TRUE,
         (make_date(calc.y, calc.m, 2 + (mod(calc.rn * 7, 24))::int) + interval '3 days')
  FROM calc CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_records', id FROM ins;

-- ------------------------------------------------------------
-- 4. Scope 3 records — all 15 categories, Pareto-weighted
--    cadence: 12 = monthly, 4 = quarterly, 1 = annual
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _s3;
CREATE TEMP TABLE _s3 (
  cat_no int, cat_id int, sub_id int, dp_id int, unit text,
  share numeric, cadence int, ef numeric, method text,
  label_th text, label_en text);
INSERT INTO _s3 VALUES
  ( 1, 34,  6,   1, 'THB',     0.467433, 12, 0.045,  'spend_based',  'จัดซื้อวัตถุดิบและบริการ',      'Purchased goods & services'),
  ( 4, 28,  9,  27, 'km',      0.141762, 12, 0.120,  'activity_ef',  'ขนส่งวัตถุดิบขาเข้า',           'Inbound freight'),
  ( 5, 36, 10,  37, 'kg',      0.095019, 12, 0.467,  'activity_ef',  'ของเสียจากการดำเนินงาน',        'Operational waste'),
  ( 9, 27, 14,  74, 'km',      0.083525, 12, 0.120,  'activity_ef',  'ขนส่งสินค้าถึงลูกค้า',          'Outbound distribution'),
  ( 3, 33,  8,  18, 'liters',  0.067433,  4, 0.620,  'activity_ef',  'พลังงานต้นน้ำ (WTT)',           'Fuel & energy upstream (WTT)'),
  ( 6, 37, 11,  48, 'km',      0.047510,  4, 0.133,  'activity_ef',  'การเดินทางเพื่อธุรกิจ',         'Business travel'),
  ( 7, 38, 12,  59, 'km',      0.041379,  4, 0.090,  'activity_ef',  'การเดินทางมาทำงานของพนักงาน',   'Employee commuting'),
  ( 2, 31,  7,  11, 'THB',     0.031418,  4, 0.038,  'spend_based',  'สินค้าทุนและเครื่องจักร',       'Capital goods'),
  (12, 41, 17,  93, 'kg',      0.013793,  1, 0.350,  'activity_ef',  'การจัดการสินค้าเมื่อหมดอายุ',   'End-of-life treatment'),
  (11, 40, 16,  86, 'kWh',     0.006897,  1, 0.4999, 'activity_ef',  'การใช้งานสินค้าที่ขาย',          'Use of sold products'),
  ( 8, 39, 13,  67, 'sqm',     0.000766,  1, 45.0,   'activity_ef',  'สินทรัพย์เช่าต้นน้ำ',            'Upstream leased assets'),
  (10, 30, 15,  81, 'kWh',     0.000766,  1, 0.4999, 'activity_ef',  'การแปรรูปสินค้าที่ขาย',          'Processing of sold products'),
  (13, 35, 18,  99, 'sqm',     0.000766,  1, 38.0,   'activity_ef',  'สินทรัพย์เช่าปลายน้ำ',           'Downstream leased assets'),
  (14, 29, 19, 104, 'outlets', 0.000766,  1, 2500.0, 'activity_ef',  'แฟรนไชส์',                       'Franchises'),
  (15, 32, 20, 111, 'THB',     0.000766,  1, 0.020,  'spend_based',  'พอร์ตการลงทุน',                  'Investments');

WITH grid AS (
  SELECT s.*, y.y,
         -- monthly → 1..n_months; quarterly → 3,6,9,12 (clipped); annual → 12
         CASE s.cadence
           WHEN 12 THEN p.p
           WHEN 4  THEN p.p * 3
           ELSE LEAST(12, y.n_months)
         END AS m,
         y.s3_kg, y.n_months
  FROM _s3 s
  CROSS JOIN _years y
  CROSS JOIN LATERAL generate_series(
    1,
    CASE s.cadence
      WHEN 12 THEN y.n_months
      WHEN 4  THEN GREATEST(1, y.n_months / 3)
      ELSE 1
    END) AS p(p)
), weighted AS (
  SELECT g.*, _mseason(g.m) AS w,
         SUM(_mseason(g.m)) OVER (PARTITION BY g.y, g.cat_no) AS w_tot
  FROM grid g
), calc AS (
  SELECT w.*,
         ROUND(w.s3_kg * w.share * w.w / w.w_tot, 2) AS kg,
         (ROW_NUMBER() OVER (ORDER BY w.y, w.m, w.cat_no))::int AS rn
  FROM weighted w
), ins AS (
  INSERT INTO esg_records (
    organization_id, user_id, category_id, subcategory_id, scope3_category_id,
    pillar, record_label, entry_date, datapoints, kgco2e,
    ghg_status, ghg_method, ghg_missing_fields, ghg_reason,
    ghg_source_name, ghg_source_url, ghg_ef_value, ghg_ef_unit,
    currency, status, entry_source, is_active, created_date)
  SELECT c.org_id, c.admin_id,
         calc.cat_id,          -- 27..41 → feeds the Scope 3 donut
         NULL,                 -- those categories own no subcategories
         calc.cat_no,
         'E',
         calc.label_th || ' — ' ||
           CASE calc.cadence WHEN 12 THEN to_char(make_date(calc.y, calc.m, 1), 'Mon YYYY')
                             WHEN 4  THEN 'Q' || ((calc.m + 2) / 3)::text || ' ' || calc.y::text
                             ELSE 'FY' || calc.y::text END,
         make_date(calc.y, calc.m, 2 + (mod(calc.rn * 11, 24))::int),
         -- datapoint_ids come from subcategories 6..20 (which own the 456
         -- datapoints) while category_id above stays 27..41 for the donut —
         -- the two halves of the duplicated Scope 3 taxonomy feed two views.
         (SELECT jsonb_agg(jsonb_build_object(
             'datapoint_id', d.id,
             'datapoint_name', d.name,
             'canonical_name', CASE COALESCE(d.unit, '') WHEN 'km' THEN 'distance_km'
                                                         WHEN 'kg' THEN 'weight_kg'
                                                         WHEN 'kWh' THEN 'energy_kwh'
                                                         WHEN 'liters' THEN 'volume_litres'
                                                         WHEN 'THB' THEN 'amount'
                                                         ELSE NULL END,
             'is_canonical', COALESCE(d.unit, '') IN ('km','kg','kWh','liters','THB'),
             'value', CASE WHEN d.id = calc.dp_id
                           THEN ROUND(calc.kg / calc.ef, 2)
                           ELSE ROUND((calc.kg / calc.ef) * (0.18 + _det(d.id) * 0.9), 2) END,
             'unit', COALESCE(d.unit, 'unit'),
             'confidence', 1.0,
             'tags', jsonb_build_array()) ORDER BY d.sort_order, d.id)
          FROM esg_datapoint d
          WHERE d.esg_data_subcategory_id = calc.sub_id
            AND d.is_active AND d.data_type = 'numeric'),
         -- ~8% deliberately left un-costed so the data-quality rules fire
         CASE WHEN mod(calc.rn, 13) = 0 THEN NULL ELSE calc.kg END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN 'insufficient' ELSE 'computed' END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN NULL ELSE calc.method END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN '["emission_factor"]'::jsonb ELSE '[]'::jsonb END,
         CASE WHEN mod(calc.rn, 13) = 0
              THEN 'ยังไม่มีค่าการปล่อยที่เหมาะสมสำหรับรายการนี้' ELSE NULL END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN NULL
              WHEN calc.method = 'spend_based' THEN 'DEFRA 2024 spend-based factors'
              ELSE 'TGO Emission Factor 2022' END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN NULL ELSE 'https://thaicarbonlabel.tgo.or.th/' END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN NULL ELSE ROUND(calc.ef / 1000.0, 9) END,
         CASE WHEN mod(calc.rn, 13) = 0 THEN NULL ELSE 'tCO2e/' || calc.unit END,
         CASE WHEN calc.unit = 'THB' THEN 'THB' ELSE NULL END,
         CASE WHEN mod(calc.rn, 8) = 0 THEN 'PENDING_VERIFY' ELSE 'VERIFIED' END,
         CASE WHEN mod(calc.rn, 3) = 0 THEN 'LINE_CHAT' ELSE 'LIFF_MANUAL' END,
         TRUE,
         (make_date(calc.y, calc.m, 2 + (mod(calc.rn * 11, 24))::int) + interval '4 days')
  FROM calc CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_records', id FROM ins;

-- ------------------------------------------------------------
-- 5. Non-GHG disclosures — the rest of E, plus all of S and G
--    One annual record per subcategory per year. These have no emission
--    factor by nature (no EF exists for "number of board members"), hence
--    ghg_status='method_unknown' and kgco2e NULL. They populate the Data
--    Warehouse tree, /completeness and the GRI export.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _disc;
CREATE TEMP TABLE _disc (
  cat_id int, sub_id int, dp_id int, pillar char(1), unit text,
  base numeric, drift numeric, label_th text, label_en text);
INSERT INTO _disc VALUES
  -- E — water / waste / energy / biodiversity / air / materials
  ( 4, 21, 200, 'E', 'm3',            168000,  -0.030, 'ปริมาณน้ำใช้สุทธิ',            'Net water consumed'),
  ( 4, 22, 186, 'E', 'm3',            214000,  -0.025, 'ปริมาณน้ำที่ดึงมาใช้',          'Water withdrawn'),
  ( 4, 23, 194, 'E', 'm3',             46000,  -0.020, 'ปริมาณน้ำทิ้ง',                 'Water discharged'),
  ( 5, 24, 218, 'E', 'kg',            742000,  -0.040, 'ของเสียไม่อันตราย',             'Non-hazardous waste'),
  ( 5, 25, 224, 'E', 'kg',            512000,   0.050, 'ของเสียที่นำกลับมาใช้ใหม่',      'Waste diverted from landfill'),
  ( 5, 26, 206, 'E', 'kg',             38500,  -0.030, 'ของเสียอันตราย',                'Hazardous waste'),
  ( 5, 52, 391, 'E', 'tonnes',            96,  -0.060, 'พลาสติกที่ใช้ทั้งหมด',           'Total plastic used'),
  ( 6, 27, 233, 'E', 'kWh',          1180000,   0.220, 'พลังงานหมุนเวียนที่ผลิตได้',     'Renewable energy generated'),
  ( 6, 28, 238, 'E', 'kWh',           640000,   0.120, 'พลังงานที่ประหยัดได้',           'Energy saved'),
  ( 6, 29, 227, 'E', 'kWh',          8360000,  -0.040, 'พลังงานที่ใช้ทั้งหมด',           'Total energy consumed'),
  ( 6, 53, 393, 'E', 'kWh',           210000,   0.080, 'พลังงานที่ขายออก',               'Energy sold'),
  ( 7, 30, 252, 'E', 'species',            3,   0.000, 'ชนิดพันธุ์ที่ได้รับผลกระทบ',      'Species affected'),
  ( 7, 31, 248, 'E', 'hectares',        12.4,   0.000, 'พื้นที่ดำเนินงานทั้งหมด',        'Total operational area'),
  ( 8, 32, 257, 'E', 'kg',              8600,  -0.050, 'ปริมาณมลพิษทางอากาศ (NOx)',      'Air pollutant emitted (NOx)'),
  ( 8, 54, 399, 'E', 'kg CFC-11 eq',     1.8,  -0.080, 'สารทำลายชั้นโอโซน',              'Ozone-depleting substances'),
  (22, 49, 364, 'E', 'kg',           4250000,  -0.020, 'วัตถุดิบที่ใช้',                 'Materials used'),
  (22, 50, 368, 'E', 'kg',            318000,   0.090, 'วัสดุที่นำกลับคืนมา',            'Materials reclaimed'),
  -- S — labour / H&S / human rights / community / D&I / training / supply chain / product / privacy
  ( 9, 34, 279, 'S', 'persons',          420,   0.020, 'จำนวนพนักงานทั้งหมด',            'Total employees'),
  ( 9, 35, 285, 'S', '%',                 96,   0.010, 'ความครอบคลุมสวัสดิการ',          'Benefits coverage'),
  (10, 36, 298, 'S', 'hours',           3480,   0.060, 'ชั่วโมงอบรมความปลอดภัย',         'Safety training hours'),
  (10, 37, 290, 'S', 'cases',              6,  -0.150, 'อุบัติเหตุที่บันทึกได้',          'Recordable incidents'),
  (10, 58, 417, 'S', 'persons',            0,   0.000, 'ผู้เสียชีวิตจากโรคจากการทำงาน',   'Fatalities from ill health'),
  (11, 38, 301, 'S', 'assessments',        4,   0.250, 'การประเมินสิทธิมนุษยชน',          'Human rights assessments'),
  (12, 39, 309, 'S', 'persons',         2400,   0.150, 'ผู้ได้รับประโยชน์จากชุมชน',       'Community beneficiaries'),
  (13, 40, 310, 'S', '%',               43.5,   0.020, 'สัดส่วนพนักงานหญิง',              'Female employees'),
  (14, 41, 318, 'S', 'hours',           26.4,   0.080, 'ชั่วโมงอบรมต่อพนักงาน',           'Training hours per employee'),
  (15, 42, 325, 'S', 'suppliers',         86,   0.180, 'คู่ค้าที่ผ่านการคัดกรองด้านสังคม', 'Suppliers screened on social criteria'),
  (23, 55, 410, 'S', 'cases',              0,   0.000, 'การไม่ปฏิบัติตามด้านฉลาก',        'Labeling non-compliance'),
  (23, 56, 406, 'S', '%',                 92,   0.030, 'สินค้าที่ประเมินความปลอดภัย',     'Products assessed for H&S'),
  (24, 57, 416, 'S', 'cases',              1,  -0.300, 'ข้อร้องเรียนด้านความเป็นส่วนตัว',  'Customer privacy complaints'),
  -- G — board / anti-corruption / risk / compliance / ethics / privacy / economic / tax
  (16, 43, 328, 'G', 'persons',            9,   0.000, 'จำนวนกรรมการบริษัท',              'Board members'),
  (17, 44, 336, 'G', 'persons',          398,   0.040, 'พนักงานที่อบรมต่อต้านทุจริต',      'Employees trained on anti-corruption'),
  (18, 45, 339, 'G', 'risks',             24,   0.080, 'ความเสี่ยงที่ระบุได้',            'Risks identified'),
  (19, 46, 347, 'G', 'cases',              0,   0.000, 'การละเมิดกฎระเบียบ',              'Regulatory violations'),
  (20, 47, 348, 'G', '%',                 98,   0.010, 'ความครอบคลุมอบรมจริยธรรม',        'Ethics training coverage'),
  (21, 48, 358, 'G', 'incidents',          0,   0.000, 'เหตุการณ์ข้อมูลรั่วไหล',          'Data breach incidents'),
  (25, 59, 438, 'G', '%',                 68,   0.040, 'สัดส่วนการจัดซื้อในท้องถิ่น',      'Local procurement share'),
  (26, 60, 439, 'G', 'persons',          420,   0.020, 'จำนวนพนักงาน (รายงานภาษี)',       'Employees (country-by-country)');

\if :include_disclosures
WITH calc AS (
  SELECT d.*, y.y, y.n_months,
         ROUND(d.base * power(1 + d.drift, y.y - 2023), 2) AS val,
         (ROW_NUMBER() OVER (ORDER BY y.y, d.pillar, d.cat_id, d.sub_id))::int AS rn
  FROM _disc d CROSS JOIN _years y
), ins AS (
  INSERT INTO esg_records (
    organization_id, user_id, category_id, subcategory_id, scope3_category_id,
    pillar, record_label, entry_date, datapoints, kgco2e,
    ghg_status, ghg_missing_fields, ghg_reason,
    status, entry_source, notes, is_active, created_date)
  SELECT c.org_id, c.admin_id, calc.cat_id, calc.sub_id, NULL,
         calc.pillar,
         calc.label_th || ' — FY' || calc.y::text,
         make_date(calc.y, LEAST(12, calc.n_months), 20),
         jsonb_build_array(jsonb_build_object(
           'datapoint_id', calc.dp_id,
           'datapoint_name', calc.label_en,
           'canonical_name', NULL,
           'is_canonical', FALSE,
           'value', calc.val,
           'unit', calc.unit,
           'confidence', 1.0,
           'tags', jsonb_build_array())),
         NULL,
         'method_unknown', '[]'::jsonb,
         'ตัวชี้วัดเชิงเปิดเผยข้อมูล ไม่มีค่าการปล่อยก๊าซเรือนกระจก',
         CASE WHEN calc.y = 2026 THEN 'PENDING_VERIFY' ELSE 'VERIFIED' END,
         'LIFF_MANUAL',
         calc.label_en || ' · FY' || calc.y::text,
         TRUE,
         (make_date(calc.y, LEAST(12, calc.n_months), 20) + interval '6 days')
  FROM calc CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_records', id FROM ins;
\endif

-- ------------------------------------------------------------
-- 6. Suppliers (24) — tiered, Pareto spend, varied data quality
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _sup;
CREATE TEMP TABLE _sup (n int, nm text, sector text, tier text, country text,
                        spend numeric, cat int, lvl text, srcmode text, dq numeric, st text);
INSERT INTO _sup VALUES
  ( 1,'สหวัฒน์ โพลิเมอร์ จำกัด','plastics','tier1','THA',148000000, 1,'3','supplier_specific',0.94,'active'),
  ( 2,'ไทยสตีล เซ็นเตอร์','metals','tier1','THA',126000000, 1,'3','supplier_specific',0.91,'active'),
  ( 3,'บางกอก แพคเกจจิ้ง','packaging','tier1','THA', 98000000, 1,'2','hybrid',0.82,'active'),
  ( 4,'อีสเทิร์น เคมิคอล','chemicals','tier1','THA', 86500000, 1,'2','hybrid',0.78,'active'),
  ( 5,'Kerry Logistics (Thailand)','logistics','tier1','THA', 74000000, 4,'2','hybrid',0.80,'active'),
  ( 6,'ลำพูน อิเล็กทรอนิกส์','electronics','tier1','THA', 62000000, 1,'2','hybrid',0.75,'active'),
  ( 7,'Flash Express','logistics','tier1','THA', 54000000, 9,'2','hybrid',0.72,'active'),
  ( 8,'ศรีราชา ฮาร์ดแวร์','components','tier1','THA', 47500000, 1,'1','default',0.61,'active'),
  ( 9,'PTT Oil and Retail','energy','tier1','THA', 41000000, 3,'3','supplier_specific',0.88,'active'),
  (10,'Wongpanit Recycling','waste','tier1','THA', 33500000, 5,'2','hybrid',0.83,'active'),
  (11,'นครปฐม กระดาษ','paper','tier2','THA', 28000000, 1,'1','default',0.58,'active'),
  (12,'Shenzhen Precision Parts','components','tier2','CHN', 24500000, 1,'1','default',0.52,'active'),
  (13,'อยุธยา คอนเทนเนอร์','packaging','tier2','THA', 21000000, 1,'1','default',0.55,'active'),
  (14,'Singapore Trading Hub','distribution','tier2','SGP', 18500000, 4,'1','default',0.49,'active'),
  (15,'ระยอง อินซูเลชั่น','materials','tier2','THA', 16000000, 1,'1','default',0.53,'active'),
  (16,'Hanoi Textile Works','textiles','tier2','VNM', 13500000, 1,'1','default',0.47,'pending'),
  (17,'ขอนแก่น ทรานสปอร์ต','logistics','tier2','THA', 11500000, 4,'1','default',0.51,'active'),
  (18,'Grab Business (Thailand)','mobility','tier2','THA',  9200000, 6,'2','hybrid',0.68,'active'),
  (19,'เชียงใหม่ เมนเทนแนนซ์','services','tier2','THA',  7800000,12,'1','default',0.42,'active'),
  (20,'Jakarta Raw Materials','materials','tier3','IDN',  6400000, 1,'1','default',0.38,'pending'),
  (21,'สงขลา ซัพพลาย','components','tier3','THA',  5100000, 1,'1','default',0.36,'active'),
  (22,'Kuala Lumpur Coatings','chemicals','tier3','MYS',  4200000, 1,'1','default',0.34,'inactive'),
  (23,'ภูเก็ต คลีนนิ่ง เซอร์วิส','services','tier3','THA',  3300000,12,'1','default',0.31,'active'),
  (24,'Tokyo Instrument Co.','instruments','tier3','JPN',  2600000, 2,'1','default',0.44,'active');

WITH ins AS (
  INSERT INTO esg_suppliers (
    organization_id, supplier_name, supplier_code, tax_id, country,
    industry_sector, contact_email, contact_name, tier, data_collection_level,
    annual_spend, spend_currency, primary_scope3_category, emission_data_source,
    total_reported_tco2e, data_quality_score, status, metadata, is_active, created_date)
  SELECT c.org_id, s.nm,
         'SUP-' || lpad(s.n::text, 4, '0'),
         '0' || lpad((1050000000000 + s.n * 37)::text, 12, '0'),
         s.country, s.sector,
         'esg.contact' || s.n || '@' || 'supplier-' || s.n || '.example',
         'ฝ่ายความยั่งยืน',
         s.tier, s.lvl, s.spend, 'THB', s.cat, s.srcmode,
         ROUND(s.spend / 1000000.0 * (32 + _det(s.n) * 26), 2),
         s.dq, s.st, jsonb_build_object('onboarded_year', 2024 + mod(s.n, 2)),
         TRUE, make_date(2024 + mod(s.n, 2), 1 + mod(s.n * 5, 12), 1 + mod(s.n * 3, 27))
  FROM _sup s CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_suppliers', id FROM ins;

-- Stable handle on the seeded suppliers, ordered like _sup.
DROP TABLE IF EXISTS _supids;
CREATE TEMP TABLE _supids AS
SELECT s.id, s.supplier_name, s.tier, s.annual_spend, s.primary_scope3_category,
       s.data_quality_score,
       (ROW_NUMBER() OVER (ORDER BY s.annual_spend DESC))::int AS n
FROM esg_suppliers s
WHERE s.id IN (SELECT entity_id FROM esg_mock_seed_ids
               WHERE organization_id=:target_org AND entity='esg_suppliers');

-- ------------------------------------------------------------
-- 7. Supplier submissions (2024–2026) + chasers + one live magic link
-- ------------------------------------------------------------
WITH grid AS (
  SELECT sp.*, y.y
  FROM _supids sp
  CROSS JOIN (VALUES (2024), (2025), (2026)) AS y(y)
  WHERE sp.n <= 14 OR y.y >= 2025          -- long tail only engaged recently
), calc AS (
  SELECT g.*, (ROW_NUMBER() OVER (ORDER BY g.y, g.n))::int AS rn
  FROM grid g
), ins AS (
  INSERT INTO esg_supplier_submissions (
    supplier_id, organization_id, reporting_year, reporting_period,
    scope3_category, submission_status, submitted_at, verified_at, verified_by_id,
    data_tier, raw_data, calculated_tco2e, anomaly_flags, notes, is_active, created_date)
  SELECT calc.id, c.org_id, calc.y, 'annual', calc.primary_scope3_category,
         CASE WHEN calc.y = 2026 AND mod(calc.rn, 3) = 0 THEN 'pending'
              WHEN calc.y = 2026 THEN 'submitted'
              WHEN mod(calc.rn, 9) = 0 THEN 'submitted'
              ELSE 'verified' END,
         CASE WHEN calc.y = 2026 AND mod(calc.rn, 3) = 0 THEN NULL
              ELSE make_date(calc.y, 2 + mod(calc.rn, 4), 5 + mod(calc.rn * 3, 20))::timestamptz END,
         CASE WHEN calc.y < 2026 AND mod(calc.rn, 9) <> 0
              THEN make_date(calc.y, 4 + mod(calc.rn, 3), 8 + mod(calc.rn * 5, 18))::timestamptz
              ELSE NULL END,
         CASE WHEN calc.y < 2026 AND mod(calc.rn, 9) <> 0 THEN c.admin_id ELSE NULL END,
         CASE WHEN calc.data_quality_score >= 0.85 THEN '3'
              WHEN calc.data_quality_score >= 0.65 THEN '2' ELSE '1' END,
         jsonb_build_object(
           'annual_spend_thb', calc.annual_spend,
           'reported_scope1_tco2e', ROUND(calc.annual_spend / 1000000.0 * 6.5, 2),
           'reported_scope2_tco2e', ROUND(calc.annual_spend / 1000000.0 * 11.2, 2),
           'renewable_share_pct', ROUND(8 + _det(calc.n * calc.y) * 42, 1),
           'has_third_party_assurance', calc.data_quality_score >= 0.85),
         ROUND(calc.annual_spend / 1000000.0 * (32 + _det(calc.n) * 26)
               * power(0.96, calc.y - 2024)::numeric, 2),
         -- a few outliers so the anomaly panel has something to show
         CASE WHEN mod(calc.rn, 11) = 0
              THEN '["yoy_variance_gt_40pct"]'::jsonb
              WHEN calc.data_quality_score < 0.40
              THEN '["low_data_quality"]'::jsonb
              ELSE '[]'::jsonb END,
         NULL, TRUE,
         make_date(calc.y, 2 + mod(calc.rn, 4), 1 + mod(calc.rn * 3, 20))
  FROM calc CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_supplier_submissions', id FROM ins;

WITH ins AS (
  INSERT INTO esg_supplier_chasers (
    supplier_id, organization_id, chaser_type, scheduled_date, sent_at,
    status, reminder_count, message_template, response_received, is_active, created_date)
  SELECT sp.id, c.org_id,
         CASE WHEN mod(sp.n, 4) = 0 THEN 'line' ELSE 'email' END,
         make_date(2026, 8, 10 + mod(sp.n, 18))::timestamptz,
         CASE WHEN mod(sp.n, 3) <> 0 THEN make_date(2026, 8, 10 + mod(sp.n, 18))::timestamptz END,
         CASE WHEN mod(sp.n, 3) = 0 THEN 'scheduled'
              WHEN mod(sp.n, 7) = 0 THEN 'failed' ELSE 'sent' END,
         mod(sp.n, 3),
         'supplier_annual_reminder_th',   -- varchar(50): a template key, not body text
         mod(sp.n, 5) = 0, TRUE, '2026-08-01'
  FROM _supids sp CROSS JOIN _cfg c
  WHERE sp.n <= 15
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_supplier_chasers', id FROM ins;

-- One unexpired link so /supplier/:token is demoable; two historical.
WITH ins AS (
  INSERT INTO esg_supplier_magic_links (
    supplier_id, organization_id, token, email_sent_to, expires_at, used_at,
    scope, is_active, created_date)
  SELECT sp.id, c.org_id,
         encode(digest('gepp-esg-demo-' || c.org_id || '-' || sp.id, 'sha256'), 'hex'),
         'esg.contact' || sp.n || '@' || 'supplier-' || sp.n || '.example',
         CASE sp.n WHEN 1 THEN '2026-12-31 23:59+07'::timestamptz
                   ELSE make_date(2026, 6, 30)::timestamptz END,
         CASE WHEN sp.n = 2 THEN '2026-06-12 10:24+07'::timestamptz END,
         'data_submission', TRUE, '2026-06-01'
  FROM _supids sp CROSS JOIN _cfg c
  WHERE sp.n <= 3
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_supplier_magic_links', id FROM ins;

-- ------------------------------------------------------------
-- 8. Scope 3 entries — method mix drives the calculation-method chart
-- ------------------------------------------------------------
WITH grid AS (
  SELECT s.cat_no, s.share, y.y, y.s3_kg,
         m.method, m.dq,
         (ROW_NUMBER() OVER (ORDER BY y.y, s.cat_no, m.method))::int AS rn
  FROM _s3 s
  CROSS JOIN _years y
  CROSS JOIN (VALUES ('spend_based','estimated'),
                     ('average_data','secondary'),
                     ('supplier_specific','primary')) AS m(method, dq)
  WHERE y.y >= 2024
    AND (s.share > 0.03 OR m.method = 'spend_based')   -- long tail = spend-based only
), ins AS (
  INSERT INTO esg_scope3_entries (
    organization_id, category_number, supplier_id, reporting_year, reporting_month,
    calculation_method, activity_data, activity_unit,
    emission_factor_value, emission_factor_source, calculated_tco2e,
    spend_amount, spend_currency, data_quality_indicator, notes, metadata,
    is_active, created_date)
  SELECT c.org_id, g.cat_no,
         (SELECT sp.id FROM _supids sp
           WHERE sp.primary_scope3_category = g.cat_no
           ORDER BY sp.n LIMIT 1),
         g.y, NULL, g.method,
         ROUND(g.s3_kg * g.share / 1000.0 * (0.28 + _det(g.rn) * 0.12), 2),
         CASE g.method WHEN 'spend_based' THEN 'THB' ELSE 'unit' END,
         CASE g.method WHEN 'spend_based' THEN 0.000045
                       WHEN 'average_data' THEN 0.000120
                       ELSE 0.000098 END,
         CASE g.method WHEN 'spend_based' THEN 'DEFRA 2024 spend-based'
                       WHEN 'average_data' THEN 'TGO Emission Factor 2022'
                       ELSE 'Supplier-reported (assured)' END,
         ROUND(g.s3_kg * g.share / 1000.0 * (0.28 + _det(g.rn) * 0.12), 2),
         CASE g.method WHEN 'spend_based'
              THEN ROUND(g.s3_kg * g.share / 1000.0 * 24000, 0) END,
         CASE g.method WHEN 'spend_based' THEN 'THB' END,
         g.dq, NULL,
         jsonb_build_object('seeded_view', 'scope3_method_mix'),
         TRUE, make_date(g.y, 12, 15)
  FROM grid g CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_scope3_entries', id FROM ins;

-- ------------------------------------------------------------
-- 9. CBAM — 5 CN codes + 2 quarterly reports
-- ------------------------------------------------------------
WITH p AS (
  SELECT * FROM (VALUES
    ('7208 51 20','Hot-rolled steel sheet','เหล็กแผ่นรีดร้อน',      4820, 'tonnes', 1.86, 0.42, 0.31, 'third_party_verified'),
    ('7601 20 20','Aluminium alloy billet','อะลูมิเนียมอัลลอยบิลเล็ต',1240, 'tonnes', 6.74, 1.18, 0.88, 'third_party_verified'),
    ('7318 15 90','Steel fasteners','สลักเกลียวเหล็ก',                 386, 'tonnes', 2.14, 0.51, 0.44, 'self_declared'),
    ('2523 29 00','Portland cement','ปูนซีเมนต์ปอร์ตแลนด์',           9600, 'tonnes', 0.62, 0.09, 0.04, 'third_party_verified'),
    ('3102 10 10','Urea fertiliser','ปุ๋ยยูเรีย',                     2150, 'tonnes', 1.32, 0.24, 0.19, 'self_declared')
  ) AS t(cn, nm, nm_th, vol, unit, direct, indirect, precursor, vstat)
), ins AS (
  INSERT INTO esg_cbam_products (
    organization_id, cn_code, product_name, product_name_th,
    production_volume, production_unit,
    direct_emissions_tco2e, indirect_emissions_tco2e, precursor_emissions_tco2e,
    total_embedded_emissions, specific_embedded_emissions, default_value_tco2e,
    reporting_period_start, reporting_period_end, installation_id,
    verification_status, metadata, is_active, created_date)
  SELECT c.org_id, p.cn, p.nm, p.nm_th, p.vol, p.unit,
         ROUND(p.vol * p.direct, 2), ROUND(p.vol * p.indirect, 2), ROUND(p.vol * p.precursor, 2),
         ROUND(p.vol * (p.direct + p.indirect + p.precursor), 2),
         ROUND(p.direct + p.indirect + p.precursor, 4),
         ROUND((p.direct + p.indirect + p.precursor) * 1.28, 4),
         '2026-04-01', '2026-06-30',
         'TH-INST-' || lpad((row_number() OVER (ORDER BY p.cn))::int::text, 3, '0'),
         p.vstat, jsonb_build_object('route', 'export_eu'), TRUE, '2026-07-05'
  FROM p CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_cbam_products', id FROM ins;

WITH q AS (SELECT * FROM (VALUES (1, 'submitted', '2026-04-28'), (2, 'draft', NULL)) AS t(qq, st, sub)),
ins AS (
  INSERT INTO esg_cbam_reports (
    organization_id, reporting_quarter, reporting_year, status, report_data,
    submitted_at, is_active, created_date)
  SELECT c.org_id, q.qq, 2026, q.st,
         jsonb_build_object(
           'declarant', 'GEPP ESG Demo Co., Ltd.',
           'total_embedded_tco2e',
             (SELECT ROUND(SUM(total_embedded_emissions), 2) FROM esg_cbam_products
               WHERE id IN (SELECT entity_id FROM esg_mock_seed_ids
                            WHERE organization_id = c.org_id AND entity='esg_cbam_products')),
           'product_count', 5,
           'method', 'actual_values'),
         q.sub::timestamptz, TRUE, make_date(2026, 1 + q.qq * 3, 10)
  FROM q CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_cbam_reports', id FROM ins;

-- ------------------------------------------------------------
-- 10. MACC — org-level initiatives cloned from the global templates
-- ------------------------------------------------------------
WITH ins AS (
  INSERT INTO esg_macc_initiatives (
    organization_id, name, name_th, description, category, applicable_scope,
    abatement_potential_tco2e, implementation_cost, annual_operating_cost,
    annual_savings, cost_per_tco2e, payback_years, implementation_timeline,
    difficulty, is_template, industry_sector, source, status, metadata,
    is_active, created_date)
  SELECT c.org_id, t.name, t.name_th, t.description, t.category, t.applicable_scope,
         t.abatement_potential_tco2e, t.implementation_cost, t.annual_operating_cost,
         t.annual_savings, t.cost_per_tco2e, t.payback_years, t.implementation_timeline,
         t.difficulty, FALSE, 'manufacturing', t.source,
         CASE WHEN mod(t.id, 5) = 0 THEN 'completed'
              WHEN mod(t.id, 3) = 0 THEN 'in_progress' ELSE 'available' END,
         jsonb_build_object('cloned_from_template', t.id),
         TRUE, '2026-02-10'
  FROM esg_macc_initiatives t CROSS JOIN _cfg c
  WHERE t.is_template = TRUE AND t.is_active = TRUE
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_macc_initiatives', id FROM ins;

-- ------------------------------------------------------------
-- 11. LINE / LIFF: members, binding, invitations, messages
-- ------------------------------------------------------------
-- NOTE: the desktop login is deliberately left WITHOUT a LINE binding —
-- esg_dashboard_service._base_query treats a bound user as user-scoped, so
-- binding watth.test would shrink the dashboard to that user's own rows.
WITH m AS (
  SELECT * FROM (VALUES
    (1, 'U8a41d9c2e7b5460f9d3c1a8e6f204b73', 'คุณปกรณ์ (ฝ่ายจัดซื้อ)'),
    (2, 'U3f92b7e18a6c45d0b2e9174c8a5d36e1', 'คุณศิริพร (ฝ่ายโรงงาน)'),
    (3, 'Ub57c04e9d1a842f6b8c35e97a2f61d40', 'คุณธนกฤต (ฝ่ายขนส่ง)'),
    (4, 'Ud26f8b103c9e47a5b1d70f2e84c95a67', 'คุณอารยา (ฝ่ายความยั่งยืน)')
  ) AS t(n, uid, nm)
), ins AS (
  INSERT INTO esg_users (organization_id, platform, platform_user_id, display_name,
                         is_active, created_date)
  SELECT c.org_id, 'line', m.uid, m.nm, TRUE, make_date(2025, 3 + m.n, 4 + m.n * 3)
  FROM m CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_users', id FROM ins;

WITH ins AS (
  INSERT INTO esg_external_platform_binding (organization_id, channel, auth_json,
                                             is_active, created_date)
  SELECT c.org_id, 'line',
         jsonb_build_object('bound', TRUE, 'channel_name', 'GEPP ESG Demo OA'),
         TRUE, '2025-03-04'
  FROM _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_external_platform_binding', id FROM ins;

WITH ins AS (
  INSERT INTO esg_external_invitation_links (organization_id, token, expires_at,
                                             is_active, created_date)
  SELECT c.org_id,
         encode(digest('gepp-esg-invite-' || c.org_id || '-' || g, 'sha256'), 'hex'),
         CASE WHEN g = 1 THEN '2026-12-31 23:59+07'::timestamptz
              ELSE make_date(2026, 5, 31)::timestamptz END,
         TRUE, make_date(2026, 4, 1 + g)
  FROM generate_series(1, 3) g CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_external_invitation_links', id FROM ins;

WITH u AS (
  SELECT eu.id, eu.platform_user_id, eu.display_name,
         (ROW_NUMBER() OVER (ORDER BY eu.id))::int AS n
  FROM esg_users eu
  WHERE eu.id IN (SELECT entity_id FROM esg_mock_seed_ids
                  WHERE organization_id=:target_org AND entity='esg_users')
), g AS (
  SELECT u.*, s.k, (ROW_NUMBER() OVER (ORDER BY u.n, s.k))::int AS rn
  FROM u CROSS JOIN generate_series(1, 8) s(k)
), ins AS (
  INSERT INTO esg_line_messages (organization_id, line_message_id, line_user_id,
                                 message_type, processing_status, is_active, created_date)
  SELECT c.org_id,
         '5' || lpad((491000000000 + g.rn * 137)::text, 15, '0'),
         g.platform_user_id,
         CASE WHEN mod(g.rn, 4) = 0 THEN 'text' ELSE 'image' END,
         CASE WHEN mod(g.rn, 9) = 0 THEN 'failed' ELSE 'processed' END,
         TRUE,
         make_date(2026, 1 + mod(g.rn, 8), 3 + mod(g.rn * 5, 24))
  FROM g CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_line_messages', id FROM ins;

-- ------------------------------------------------------------
-- 12. Materiality — completed, so the wizard shows results not a restart
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _mat;
CREATE TEMP TABLE _mat AS SELECT
  jsonb_build_object(
    'q1_industry',      jsonb_build_object('kind','single','selected','manufacturing'),
    'q2_offering',      jsonb_build_object('kind','multi','selected', jsonb_build_array('physical_b2b','physical_b2c')),
    'q3_distribution',  jsonb_build_object('kind','single','selected','own_fleet'),
    'q4_workforce',     jsonb_build_object('kind','multi','selected', jsonb_build_array('office_bound','hybrid_workforce')),
    'q5_assets',        jsonb_build_object('kind','multi','selected', jsonb_build_array('own_facilities','lease_equipment')),
    'q6_energy_waste',  jsonb_build_object('kind','multi','selected', jsonb_build_array('heavy_electricity')),
    'q7_lifecycle',     jsonb_build_object('kind','multi','selected', jsonb_build_array('single_use_disposable'))
  ) AS answers,
  '[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]'::jsonb AS derived,
  jsonb_build_object('1',9.6,'2',6.1,'3',7.4,'4',8.8,'5',8.2,'6',6.6,'7',6.3,
                     '8',3.1,'9',8.0,'10',3.4,'11',4.2,'12',5.1,'13',2.8,
                     '14',2.4,'15',2.2) AS scores;

WITH ins AS (
  INSERT INTO esg_user_materiality (user_id, organization_id, questions_version,
    answers, derived_categories, category_scores, last_question_id, completed_at,
    is_active, created_date)
  SELECT c.admin_id, c.org_id, 1, m.answers, m.derived, m.scores,
         'q7_lifecycle', '2026-02-14 11:20+07', TRUE, '2026-02-14 11:05+07'
  FROM _cfg c CROSS JOIN _mat m
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_user_materiality', id FROM ins;

WITH ins AS (
  INSERT INTO esg_materiality_submissions (user_id, organization_id, submitter_name,
    questions_version, answers, derived_categories, category_scores,
    submitted_at, is_active, created_date)
  SELECT c.admin_id, c.org_id, 'ฝ่ายความยั่งยืน', '1',
         m.answers, m.derived, m.scores, '2026-02-14 11:20+07', TRUE, '2026-02-14 11:20+07'
  FROM _cfg c CROSS JOIN _mat m
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_materiality_submissions', id FROM ins;

-- ------------------------------------------------------------
-- 13. Documents + extraction history (History page)
--
--     file_url/file_key point at the org's own S3 prefix. Rows render and
--     list correctly; the presign download only resolves for keys that
--     actually exist in the bucket, so treat these as metadata-only.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _doc;
CREATE TEMP TABLE _doc (n int, nm text, dtype text, cat text, subcat text, vendor text);
INSERT INTO _doc VALUES
  ( 1,'ใบแจ้งหนี้ค่าไฟฟ้า-กรกฎาคม-2569.pdf','utility_bill','E','Purchased Electricity','การไฟฟ้าส่วนภูมิภาค'),
  ( 2,'ใบแจ้งหนี้ค่าไฟฟ้า-มิถุนายน-2569.pdf','utility_bill','E','Purchased Electricity','การไฟฟ้าส่วนภูมิภาค'),
  ( 3,'ใบเสร็จน้ำมันดีเซล-Q2-2569.pdf','fuel_receipt','E','Mobile Combustion','PTT Oil and Retail'),
  ( 4,'ใบกำกับภาษี-วัตถุดิบพลาสติก-2569.pdf','invoice','E','Purchased goods and services','สหวัฒน์ โพลิเมอร์ จำกัด'),
  ( 5,'Manifest-ของเสียอุตสาหกรรม-2569.pdf','waste_manifest','E','Waste generated in operations','Wongpanit Recycling'),
  ( 6,'ใบแจ้งหนี้ค่าน้ำประปา-Q2-2569.pdf','utility_bill','E','Water Withdrawal','การประปาส่วนภูมิภาค'),
  ( 7,'Air-Ticket-Invoice-2026-Q2.pdf','travel_invoice','E','Business travel','Thai Airways'),
  ( 8,'Freight-Invoice-Inbound-2026-06.pdf','logistics_invoice','E','Upstream transportation and distribution','Kerry Logistics (Thailand)'),
  ( 9,'รายงานตรวจวัดคุณภาพอากาศ-2569.pdf','lab_report','E','Air Emissions','ศูนย์ตรวจวัดสิ่งแวดล้อม'),
  (10,'ใบรับรองพลังงานหมุนเวียน-REC-2569.pdf','certificate','E','Renewable Energy','TGO'),
  (11,'รายงานอุบัติเหตุจากการทำงาน-2568.pdf','hr_report','S','Occupational Incidents','ฝ่ายความปลอดภัย'),
  (12,'สรุปชั่วโมงอบรมพนักงาน-2568.xlsx','hr_report','S','Employee Training','ฝ่ายทรัพยากรบุคคล'),
  (13,'รายงานความหลากหลายของพนักงาน-2568.xlsx','hr_report','S','Workforce Diversity','ฝ่ายทรัพยากรบุคคล'),
  (14,'ผลประเมินสิทธิมนุษยชน-2568.pdf','assessment','S','Human Rights Assessment','ที่ปรึกษาภายนอก'),
  (15,'สรุปโครงการชุมชน-2568.pdf','csr_report','S','Community Programs','ฝ่ายกิจการสังคม'),
  (16,'แบบประเมินคู่ค้าด้านสังคม-2568.xlsx','assessment','S','Supplier Social Assessment','ฝ่ายจัดซื้อ'),
  (17,'รายงานคณะกรรมการบริษัท-2568.pdf','governance_report','G','Board Composition','เลขานุการบริษัท'),
  (18,'สรุปอบรมต่อต้านการทุจริต-2568.pdf','governance_report','G','Anti-Corruption Measures','ฝ่ายกำกับดูแล'),
  (19,'ทะเบียนความเสี่ยงองค์กร-2568.xlsx','governance_report','G','Risk Assessment & Mitigation','ฝ่ายบริหารความเสี่ยง'),
  (20,'รายงานภาษีรายประเทศ-2568.pdf','tax_report','G','Country-by-Country Tax','ฝ่ายบัญชีและการเงิน'),
  (21,'56-1-One-Report-2568.pdf','annual_report','G','Ethics & Code of Conduct','เลขานุการบริษัท'),
  (22,'TGO-CFO-Verification-Statement-2568.pdf','verification','E','Carbon Emissions Scope 1','ผู้ทวนสอบขึ้นทะเบียน TGO'),
  (23,'GRI-Content-Index-2568.xlsx','disclosure_index','G','Ethics & Code of Conduct','ฝ่ายความยั่งยืน'),
  (24,'CDP-Response-Draft-2026.pdf','questionnaire','E','Carbon Emissions Scope 3','ฝ่ายความยั่งยืน'),
  (25,'Supplier-Emission-Data-2026-Q2.xlsx','supplier_data','E','Purchased goods and services','ฝ่ายจัดซื้อ'),
  (26,'ใบกำกับภาษี-เครื่องจักรใหม่-2569.pdf','invoice','E','Capital goods','Tokyo Instrument Co.'),
  (27,'สรุปการเดินทางพนักงาน-2569-H1.xlsx','hr_report','E','Employee commuting','ฝ่ายทรัพยากรบุคคล'),
  (28,'CBAM-Declaration-2026-Q1.pdf','regulatory','E','Carbon Emissions Scope 1','ฝ่ายส่งออก'),
  (29,'นโยบายความเป็นส่วนตัวข้อมูลลูกค้า-2569.pdf','policy','G','Data Protection','ฝ่ายกฎหมาย'),
  (30,'รายงานการใช้น้ำและน้ำทิ้ง-2569-H1.xlsx','lab_report','E','Water Discharge','ฝ่ายสิ่งแวดล้อม');

WITH ins AS (
  INSERT INTO esg_documents (
    organization_id, file_name, file_url, file_type, file_size_bytes,
    esg_category, esg_subcategory, document_type, document_date, reporting_year,
    source, uploaded_by_id, ai_classification_status, ai_confidence,
    ai_classified_at, vendor_name, summary, tags, is_active, created_date)
  SELECT c.org_id, d.nm,
         's3://gepp-esg-documents/org-' || c.org_id || '/' || d.n || '-' || d.nm,
         CASE WHEN d.nm LIKE '%.xlsx' THEN 'xlsx' ELSE 'pdf' END,
         (180000 + mod(d.n * 48271, 3400000))::bigint,
         d.cat, d.subcat, d.dtype,
         make_date(CASE WHEN d.nm LIKE '%2569%' OR d.nm LIKE '%2026%' THEN 2026 ELSE 2025 END,
                   1 + mod(d.n * 5, 12), 1 + mod(d.n * 7, 27)),
         CASE WHEN d.nm LIKE '%2569%' OR d.nm LIKE '%2026%' THEN 2026 ELSE 2025 END,
         CASE WHEN mod(d.n, 3) = 0 THEN 'line' ELSE 'upload' END,
         c.admin_id,
         CASE WHEN mod(d.n, 11) = 0 THEN 'failed' ELSE 'completed' END,
         ROUND(0.72 + _det(d.n) * 0.27, 3),
         make_date(2026, 1 + mod(d.n * 5, 8), 2 + mod(d.n * 7, 26))::timestamptz,
         d.vendor,
         d.subcat || ' — เอกสารประกอบการรายงาน ESG',
         jsonb_build_array(d.cat, d.dtype),
         TRUE,
         make_date(CASE WHEN d.nm LIKE '%2569%' OR d.nm LIKE '%2026%' THEN 2026 ELSE 2025 END,
                   1 + mod(d.n * 5, 12), 1 + mod(d.n * 7, 27))
  FROM _doc d CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_documents', id FROM ins;

WITH u AS (
  SELECT eu.platform_user_id, eu.display_name,
         (ROW_NUMBER() OVER (ORDER BY eu.id))::int AS n
  FROM esg_users eu
  WHERE eu.id IN (SELECT entity_id FROM esg_mock_seed_ids
                  WHERE organization_id=:target_org AND entity='esg_users')
), g AS (
  SELECT u.*, s.k, (ROW_NUMBER() OVER (ORDER BY u.n, s.k))::int AS rn
  FROM u CROSS JOIN generate_series(1, 10) s(k)
), ins AS (
  INSERT INTO esg_organization_data_extraction (
    organization_id, channel, type, source_user_id, source_message_id,
    source_group_name, processing_status, error_message, processed_at,
    extractions, datapoint_matches, structured_data, is_active, created_date)
  SELECT c.org_id, 'line',
         CASE WHEN mod(g.rn, 4) = 0 THEN 'text' ELSE 'image' END,
         g.platform_user_id,
         '5' || lpad((492000000000 + g.rn * 211)::text, 15, '0'),
         'GEPP ESG Demo — ฝ่ายเก็บข้อมูล',
         CASE WHEN mod(g.rn, 13) = 0 THEN 'failed' ELSE 'completed' END,
         CASE WHEN mod(g.rn, 13) = 0 THEN 'ไม่สามารถอ่านค่าจากรูปภาพได้ กรุณาถ่ายใหม่ให้ชัดเจน' END,
         make_date(2026, 1 + mod(g.rn, 8), 3 + mod(g.rn * 3, 24))::timestamptz,
         jsonb_build_array(jsonb_build_object(
           'category', CASE WHEN mod(g.rn, 3) = 0 THEN 'Purchased Electricity'
                            WHEN mod(g.rn, 3) = 1 THEN 'Purchased goods and services'
                            ELSE 'Waste generated in operations' END,
           'confidence', ROUND(0.71 + _det(g.rn) * 0.28, 3))),
         jsonb_build_array(jsonb_build_object(
           'datapoint_id', CASE WHEN mod(g.rn, 3) = 0 THEN 163
                                WHEN mod(g.rn, 3) = 1 THEN 1 ELSE 37 END,
           'value', ROUND(1200 + _det(g.rn) * 48000, 2))),
         jsonb_build_object('vendor', 'การไฟฟ้าส่วนภูมิภาค', 'currency', 'THB'),
         TRUE,
         make_date(2026, 1 + mod(g.rn, 8), 3 + mod(g.rn * 3, 24))
  FROM g CROSS JOIN _cfg c
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_organization_data_extraction', id FROM ins;

-- ------------------------------------------------------------
-- 14. XBRL values — one per existing global tag, FY2025
-- ------------------------------------------------------------
WITH ins AS (
  INSERT INTO esg_xbrl_report_values (organization_id, tag_id, reporting_year,
                                      value, unit, context_ref, is_active, created_date)
  SELECT c.org_id, t.id, 2025,
         CASE t.data_type
           WHEN 'monetary' THEN ROUND(1850000000 * (0.02 + _det(t.id) * 0.4), 0)::text
           WHEN 'boolean'  THEN CASE WHEN mod(t.id, 2) = 0 THEN 'true' ELSE 'false' END
           WHEN 'text'     THEN 'ดูรายละเอียดในรายงานความยั่งยืน 2568'
           ELSE ROUND((100 + _det(t.id) * 19000)::numeric, 2)::text
         END,
         COALESCE(t.unit, 'pure'),
         'FY2025_' || c.org_id::text, TRUE, '2026-03-20'
  FROM esg_xbrl_tags t CROSS JOIN _cfg c
  WHERE t.is_active = TRUE
  RETURNING id, organization_id)
INSERT INTO esg_mock_seed_ids (organization_id, entity, entity_id)
SELECT organization_id, 'esg_xbrl_report_values', id FROM ins;

-- ------------------------------------------------------------
-- 15. Report
-- ------------------------------------------------------------
\echo ''
\echo '── seeded row counts ──'
SELECT entity, count(*) AS rows
FROM esg_mock_seed_ids WHERE organization_id = :target_org
GROUP BY entity ORDER BY entity;

\echo ''
\echo '── emissions by year (tCO2e) — should match the plan ──'
SELECT EXTRACT(YEAR FROM entry_date)::int AS year,
       ROUND(SUM(CASE WHEN category_id = 1 THEN kgco2e END)/1000.0, 1) AS scope1,
       ROUND(SUM(CASE WHEN category_id = 2 THEN kgco2e END)/1000.0, 1) AS scope2,
       ROUND(SUM(CASE WHEN scope3_category_id IS NOT NULL THEN kgco2e END)/1000.0, 1) AS scope3,
       ROUND(SUM(kgco2e)/1000.0, 1) AS total
FROM esg_records
WHERE organization_id = :target_org AND is_active
GROUP BY 1 ORDER BY 1;

\echo ''
\echo '── Scope 3 donut coverage (must be 15 non-zero rows) ──'
SELECT count(*) FILTER (WHERE tco2e > 0) AS categories_with_data,
       count(*) AS categories_total
FROM (
  SELECT dc.scope3_category_id, COALESCE(SUM(r.kgco2e)/1000.0, 0) AS tco2e
  FROM esg_data_category dc
  LEFT JOIN esg_records r ON r.category_id = dc.id
       AND r.organization_id = :target_org AND r.is_active
  WHERE dc.is_scope3 AND dc.scope3_category_id IS NOT NULL
  GROUP BY dc.scope3_category_id
) x;

\echo ''
\echo '── pillar spread ──'
SELECT pillar, count(*) AS records FROM esg_records
WHERE organization_id = :target_org AND is_active GROUP BY pillar ORDER BY pillar;

DROP FUNCTION IF EXISTS _mseason(int);
DROP FUNCTION IF EXISTS _det(bigint);

COMMIT;
\echo ''
\echo 'DONE — GEPP-ESG demo seeded for org' :target_org
