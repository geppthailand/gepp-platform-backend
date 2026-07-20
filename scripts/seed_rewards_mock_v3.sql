-- ============================================================
-- Rewards mock seed v3 — LARGE, portable, self-resolving
-- Target org via :target_org (default 2783 "Demo" / watth.test@geppdata.com)
--
-- Run:  psql "$DATABASE_URL" -v target_org=2783 -f scripts/seed_rewards_mock_v3.sql
--   or: psql ... -f scripts/seed_rewards_mock_v3.sql   (defaults to 2783)
--
-- Portable: resolves admin user_location + calc_ghg materials dynamically for
-- the target org. Creates its own [MOCK] activity-materials / catalog / droppoints
-- so it does NOT touch the org's real Business catalog.
--
-- Idempotent: re-running clears prior [MOCK] rows for this org first.
-- Markers: reward_users.line_status_message = '[MOCK]<org>' ; org-scoped rows tagged
--          '[MOCK]%' in description/note/name ; invites hash 'MOCK<org>%'.
--
-- Coverage (drives every visible UI section from real rows):
--   Overview : 5 KPIs (incl. GHG + baht) · trends 12mo · campaign progress ·
--              staff-today · top-members · alerts (low/out stock) · onboarding = 100%
--   Campaigns: 8 (4 active / 2 paused / 1 draft / 1 archived) · claims · targets ·
--              catalog links · droppoints · ~800 transactions · members
--   Inventory: 8 items × 3 categories · OK/LOW/OUT/archived · receipts (vendors,
--              12mo) · transfers · CostReport (monthly, vendor mix, ROI)
--   Members  : ~40 LINE + 6 staff + 5 walk-in · rank ★1-5 (pareto) · invites (3 states)
--   Setup    : cost_management ON · droppoints grid · program settings
-- ============================================================

\set ON_ERROR_STOP on
-- Default target org if -v target_org=... not passed
\if :{?target_org}
\else
  \set target_org 2783
\endif

\echo 'Seeding rewards mock v3 for org' :target_org

BEGIN;

-- ------------------------------------------------------------
-- 0. Cleanup prior [MOCK] data for this org (children → parents)
-- ------------------------------------------------------------
DELETE FROM reward_campaign_expenses
 WHERE organization_id = :target_org AND note LIKE '[MOCK]%';
DELETE FROM reward_expense_categories
 WHERE organization_id = :target_org AND name LIKE '[MOCK]%';
DELETE FROM reward_redemptions
 WHERE organization_id = :target_org AND note LIKE '[MOCK]%';
DELETE FROM reward_point_transactions
 WHERE organization_id = :target_org
   AND ( reward_user_id IN (SELECT id FROM reward_users
                             WHERE line_status_message = '[MOCK]' || :target_org)
      OR reward_campaign_id IN (SELECT id FROM reward_campaigns
                             WHERE organization_id = :target_org AND description LIKE '[MOCK]%') );
DELETE FROM reward_stocks
 WHERE note LIKE '[MOCK]%'
   AND reward_catalog_id IN (SELECT id FROM reward_catalog WHERE organization_id = :target_org);
DELETE FROM reward_campaign_catalog
 WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id = :target_org AND description LIKE '[MOCK]%')
    OR catalog_id  IN (SELECT id FROM reward_catalog   WHERE organization_id = :target_org AND description LIKE '[MOCK]%');
DELETE FROM reward_campaign_targets
 WHERE reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id = :target_org AND description LIKE '[MOCK]%');
DELETE FROM reward_campaign_droppoints
 WHERE campaign_id  IN (SELECT id FROM reward_campaigns WHERE organization_id = :target_org AND description LIKE '[MOCK]%')
    OR droppoint_id IN (SELECT id FROM droppoints       WHERE organization_id = :target_org AND name LIKE '[MOCK]%');
DELETE FROM reward_campaign_claims
 WHERE organization_id = :target_org
   AND campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id = :target_org AND description LIKE '[MOCK]%');
DELETE FROM reward_campaigns WHERE organization_id = :target_org AND description LIKE '[MOCK]%';
DELETE FROM droppoints       WHERE organization_id = :target_org AND name LIKE '[MOCK]%';
DELETE FROM reward_staff_invites WHERE organization_id = :target_org AND hash LIKE 'MOCK' || :target_org || '%';
DELETE FROM reward_catalog            WHERE organization_id = :target_org AND description LIKE '[MOCK]%';
DELETE FROM reward_catalog_categories WHERE organization_id = :target_org AND description LIKE '[MOCK]%';
DELETE FROM reward_activity_materials WHERE organization_id = :target_org AND description LIKE '[MOCK]%';
DELETE FROM organization_reward_users
 WHERE organization_id = :target_org
   AND reward_user_id IN (SELECT id FROM reward_users WHERE line_status_message = '[MOCK]' || :target_org);
DELETE FROM reward_users WHERE line_status_message = '[MOCK]' || :target_org;

-- ------------------------------------------------------------
-- 1. Resolve per-org config (admin user + calc_ghg materials)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _cfg;
CREATE TEMP TABLE _cfg AS
SELECT
  (:target_org)::bigint AS org_id,
  (SELECT id FROM user_locations
    WHERE organization_id = :target_org AND is_user = TRUE AND deleted_date IS NULL
    ORDER BY id LIMIT 1) AS admin_id,
  (SELECT id FROM materials WHERE main_material_id = 1 AND calc_ghg > 0 AND is_global AND deleted_date IS NULL ORDER BY id LIMIT 1) AS mat_plastic,
  (SELECT id FROM materials WHERE main_material_id = 2 AND calc_ghg > 0 AND is_global AND deleted_date IS NULL ORDER BY id LIMIT 1) AS mat_glass,
  (SELECT id FROM materials WHERE main_material_id = 4 AND calc_ghg > 0 AND is_global AND deleted_date IS NULL ORDER BY id LIMIT 1) AS mat_paper,
  (SELECT id FROM materials WHERE main_material_id = 5 AND calc_ghg > 0 AND is_global AND deleted_date IS NULL ORDER BY id LIMIT 1) AS mat_metal;

-- Fallback: any calc_ghg material if a specific main type is missing
UPDATE _cfg SET
  mat_glass = COALESCE(mat_glass, mat_plastic),
  mat_paper = COALESCE(mat_paper, mat_plastic),
  mat_metal = COALESCE(mat_metal, mat_plastic);

-- Guard: org + admin must resolve
DO $$
DECLARE a bigint; p bigint;
BEGIN
  SELECT admin_id, mat_plastic INTO a, p FROM _cfg;
  IF NOT EXISTS (SELECT 1 FROM organizations WHERE id = (SELECT org_id FROM _cfg) AND deleted_date IS NULL) THEN
    RAISE EXCEPTION 'Target org does not exist / is deleted';
  END IF;
  IF a IS NULL THEN RAISE EXCEPTION 'No admin user_location (is_user=TRUE) for target org'; END IF;
  IF p IS NULL THEN RAISE EXCEPTION 'No global material with calc_ghg>0 found (needed for GHG)'; END IF;
END $$;

-- ------------------------------------------------------------
-- 2. Reward setup — enable cost management + rate + budget
-- ------------------------------------------------------------
UPDATE reward_setup SET
  program_name            = COALESCE(NULLIF(program_name,''), 'Demo Rewards'),
  cost_management_enabled = TRUE,
  point_to_baht_rate      = 0.5000,
  reward_budget_total     = 300000,
  low_stock_threshold     = 10,
  updated_date            = NOW()
WHERE organization_id = :target_org;

-- ------------------------------------------------------------
-- 3. Activity materials ([MOCK]) — 4 material (GHG+revenue) + 2 activity
-- ------------------------------------------------------------
INSERT INTO reward_activity_materials
  (organization_id, name, description, type, material_id, selling_price_per_kg, ghg_factor, is_active)
SELECT :target_org, x.nm, '[MOCK] ' || x.nm, x.tp, x.matid, x.sell, x.ghgf, TRUE
FROM (
  SELECT 'ขวด PET รีไซเคิล'::text AS nm, 'material'::text AS tp, (SELECT mat_plastic FROM _cfg) AS matid, 8.0 AS sell, 1.031 AS ghgf
  UNION ALL SELECT 'ขวดแก้ว',        'material', (SELECT mat_glass FROM _cfg), 3.0, 0.276
  UNION ALL SELECT 'กระดาษ/ลัง',      'material', (SELECT mat_paper FROM _cfg), 5.0, 5.674
  UNION ALL SELECT 'โลหะรวม',         'material', (SELECT mat_metal FROM _cfg), 15.0, 1.832
  UNION ALL SELECT 'พกถุงผ้า',        'activity', NULL, NULL, NULL
  UNION ALL SELECT 'เข้าร่วม Workshop','activity', NULL, NULL, NULL
) x;

DROP TABLE IF EXISTS _ram;
CREATE TEMP TABLE _ram AS
SELECT id,
  CASE
    WHEN name LIKE '%PET%'      THEN 'pet'
    WHEN name LIKE '%แก้ว%'     THEN 'glass'
    WHEN name LIKE '%กระดาษ%'   THEN 'paper'
    WHEN name LIKE '%โลหะ%'     THEN 'metal'
    WHEN name LIKE '%ถุงผ้า%'    THEN 'bag'
    WHEN name LIKE '%Workshop%' THEN 'workshop'
  END AS code,
  CASE WHEN type = 'material' THEN 'kg' ELSE 'times' END AS kind
FROM reward_activity_materials
WHERE organization_id = :target_org AND description LIKE '[MOCK]%';

-- ------------------------------------------------------------
-- 4. Catalog categories ([MOCK]) + 8 catalog items
-- ------------------------------------------------------------
INSERT INTO reward_catalog_categories (organization_id, name, description) VALUES
  (:target_org, 'ของใช้รักษ์โลก',    '[MOCK] สินค้ารักษ์โลก'),
  (:target_org, 'อาหาร & เครื่องดื่ม', '[MOCK] ของกินของใช้'),
  (:target_org, 'อิเล็กทรอนิกส์',      '[MOCK] อุปกรณ์ไฟฟ้า');

INSERT INTO reward_catalog
  (organization_id, name, description, price, cost_baht, unit, status, min_threshold, limit_per_user_per_campaign, category_id)
SELECT :target_org, x.nm, '[MOCK] ' || x.nm, x.price, x.cost, x.unit, x.status, x.minth, x.lim,
  (SELECT id FROM reward_catalog_categories
    WHERE organization_id = :target_org AND description LIKE '[MOCK]%' AND name = x.cat LIMIT 1)
FROM (VALUES
  ('กระเป๋าผ้ารีไซเคิล GEPP', 80,   35, 'ใบ',    'active',   10, 2, 'ของใช้รักษ์โลก'),
  ('ขวดน้ำสแตนเลส 500ml',    500,  120,'ใบ',    'active',   15, 1, 'ของใช้รักษ์โลก'),
  ('หลอดสแตนเลสพกพา',        30,   25, 'ชุด',   'active',   10, 3, 'ของใช้รักษ์โลก'),
  ('ร่มพับ GEPP',            150,  90, 'คัน',   'active',   5,  1, 'ของใช้รักษ์โลก'),
  ('ชุดกล่องข้าวรักษ์โลก',    250,  140,'ชุด',   'active',   8,  1, 'อาหาร & เครื่องดื่ม'),
  ('ลำโพง Bluetooth',        1200, 750,'เครื่อง','active',   3,  1, 'อิเล็กทรอนิกส์'),
  ('Power Bank 10000mAh',    900,  500,'เครื่อง','active',   3,  1, 'อิเล็กทรอนิกส์'),
  ('แก้ว Tumbler รุ่นเก่า',   150,  80, 'ใบ',    'archived', 5,  1, 'อาหาร & เครื่องดื่ม')
) AS x(nm, price, cost, unit, status, minth, lim, cat);

DROP TABLE IF EXISTS _cat;
CREATE TEMP TABLE _cat AS
SELECT rc.id, rc.name, rc.cost_baht, rc.status,
       m.points, m.stockmode,
       row_number() OVER (ORDER BY rc.id) AS rn
FROM reward_catalog rc
JOIN (VALUES
  ('กระเป๋าผ้ารีไซเคิล GEPP', 80,   'ok'),
  ('ขวดน้ำสแตนเลส 500ml',    500,  'low'),
  ('หลอดสแตนเลสพกพา',        30,   'ok'),
  ('ร่มพับ GEPP',            150,  'ok'),
  ('ชุดกล่องข้าวรักษ์โลก',    250,  'ok'),
  ('ลำโพง Bluetooth',        1200, 'ok'),
  ('Power Bank 10000mAh',    900,  'out'),
  ('แก้ว Tumbler รุ่นเก่า',   150,  'archived')
) AS m(nm, points, stockmode) ON m.nm = rc.name
WHERE rc.organization_id = :target_org AND rc.description LIKE '[MOCK]%';

-- ------------------------------------------------------------
-- 5. Drop points ([MOCK]) — 5 locations, no user_location dependency
-- ------------------------------------------------------------
INSERT INTO droppoints (organization_id, name, hash, type, user_location_id)
SELECT :target_org, x.nm, md5('mdp' || :target_org || x.nm || random()::text), 'reward_droppoint', NULL
FROM (VALUES
  ('[MOCK] จุดรับ Lobby ตึก A'),
  ('[MOCK] จุดรับ Cafeteria'),
  ('[MOCK] จุดรับ Office ชั้น 5'),
  ('[MOCK] จุดรับ Parking'),
  ('[MOCK] จุดรับ MRT สถานี')
) AS x(nm);

DROP TABLE IF EXISTS _dp;
CREATE TEMP TABLE _dp AS
SELECT id, row_number() OVER (ORDER BY id) AS rn
FROM droppoints WHERE organization_id = :target_org AND name LIKE '[MOCK]%';

-- ------------------------------------------------------------
-- 6. Members (40 LINE) + Staff (6) + Walk-in (5)
-- ------------------------------------------------------------
-- 6a. LINE members
INSERT INTO reward_users
  (line_user_id, line_display_name, display_name, line_picture_url, line_status_message, created_via, is_active, created_date)
SELECT
  'MOCK' || :target_org || '_m_' || g,
  a[1 + ((g - 1) % array_length(a, 1))],
  a[1 + ((g - 1) % array_length(a, 1))],
  'https://i.pravatar.cc/150?img=' || (1 + (g % 70)),
  '[MOCK]' || :target_org,
  'line',
  (g NOT IN (13, 26)),
  CASE WHEN g >= 38 THEN NOW() - ((40 - g) || ' days')::interval
       ELSE NOW() - ((385 - g * 9) || ' days')::interval END
FROM generate_series(1, 40) g,
     (SELECT ARRAY[
        'สมชาย','มาลี','ธนากร','ปาริชาต','ภูมิพัฒน์','พรทิพย์','นิรันดร์','อุไรวรรณ','ณัฐพงษ์','กมลชนก',
        'ศิริพร','วีรภัทร','จิราภา','ชลธิชา','ธีรเดช','พิมพ์ชนก','อนุชา','เบญจวรรณ','กฤษณะ','สุนิสา',
        'ปิยะ','รัตนา','วิชัย','อรทัย','ธนพล','กันยา','ณัฐวุฒิ','สุดารัตน์','พงศกร','มณีรัตน์',
        'อภิสิทธิ์','จันทิมา','ศักดิ์ชัย','นภาพร','ธัญญา','เอกชัย','วรรณิศา','ประเสริฐ','สุกัญญา','ชัยวัฒน์'
      ]::text[] AS a) names;

INSERT INTO organization_reward_users (reward_user_id, organization_id, role, is_active, created_date)
SELECT ru.id, :target_org, 'user', ru.is_active, ru.created_date
FROM reward_users ru
WHERE ru.line_user_id LIKE 'MOCK' || :target_org || '_m\_%' ESCAPE '\';

-- 6b. Staff (joined early)
INSERT INTO reward_users
  (line_user_id, line_display_name, display_name, line_picture_url, line_status_message, created_via, is_active, created_date)
SELECT
  'MOCK' || :target_org || '_s_' || g,
  a[g], a[g],
  'https://i.pravatar.cc/150?img=' || (50 + g),
  '[MOCK]' || :target_org, 'line', TRUE,
  NOW() - ((360 - g * 10) || ' days')::interval
FROM generate_series(1, 6) g,
     (SELECT ARRAY[
        'หัวหน้ากะ ก้อง','พนง. Lobby แนน','พนง. Cafe โอ๋','พนง. Office ปูน','พนง. MRT ตาล','พนง. Parking บอย'
      ]::text[] AS a) sn;

INSERT INTO organization_reward_users (reward_user_id, organization_id, role, is_active, created_date)
SELECT ru.id, :target_org, 'staff', TRUE, ru.created_date
FROM reward_users ru
WHERE ru.line_user_id LIKE 'MOCK' || :target_org || '_s\_%' ESCAPE '\';

DROP TABLE IF EXISTS _staff;
CREATE TEMP TABLE _staff AS
SELECT oru.id AS staff_id, oru.reward_user_id
FROM organization_reward_users oru
JOIN reward_users ru ON ru.id = oru.reward_user_id
WHERE oru.organization_id = :target_org AND oru.role = 'staff'
  AND ru.line_status_message = '[MOCK]' || :target_org;

-- 6c. Walk-in members (no LINE; phone identity)
INSERT INTO reward_users
  (display_name, phone_number, line_status_message, created_via, created_by_staff_id, pdpa_consent_at, is_active, created_date)
SELECT
  a[g],
  '08' || lpad(((:target_org * 100 + g) % 100000000)::text, 8, '0'),
  '[MOCK]' || :target_org,
  'staff_walkin',
  (SELECT staff_id FROM _staff ORDER BY random() LIMIT 1),
  NOW() - ((g * 12) || ' days')::interval,
  TRUE,
  NOW() - ((g * 12) || ' days')::interval
FROM generate_series(1, 5) g,
     (SELECT ARRAY['ลุงสมศักดิ์ (walk-in)','ป้าลำดวน (walk-in)','คุณบุญมี (walk-in)','คุณประยูร (walk-in)','คุณสมหญิง (walk-in)']::text[] AS a) wn;

INSERT INTO organization_reward_users (reward_user_id, organization_id, role, is_active, created_date)
SELECT ru.id, :target_org, 'user', TRUE, ru.created_date
FROM reward_users ru
WHERE ru.created_via = 'staff_walkin'
  AND ru.line_status_message = '[MOCK]' || :target_org
  AND NOT EXISTS (SELECT 1 FROM organization_reward_users o WHERE o.reward_user_id = ru.id AND o.organization_id = :target_org);

-- Member pool for drops (LINE + walk-in), weighted for a pareto rank ★ curve
DROP TABLE IF EXISTS _mem;
CREATE TEMP TABLE _mem AS
SELECT oru.reward_user_id AS uid,
       COALESCE(NULLIF(split_part(ru.line_user_id, '_', 3), '')::int, 100) AS g
FROM organization_reward_users oru
JOIN reward_users ru ON ru.id = oru.reward_user_id
WHERE oru.organization_id = :target_org AND oru.role = 'user'
  AND ru.line_status_message = '[MOCK]' || :target_org;
ALTER TABLE _mem ADD COLUMN weight numeric;
UPDATE _mem SET weight = CASE g
  WHEN 1 THEN 24 WHEN 2 THEN 16 WHEN 3 THEN 11 WHEN 4 THEN 8 WHEN 5 THEN 6
  WHEN 6 THEN 4.5 WHEN 7 THEN 4 WHEN 8 THEN 3.5 WHEN 9 THEN 3 WHEN 10 THEN 3
  ELSE 1.4 END;

-- ------------------------------------------------------------
-- 7. Campaigns (8) — 4 active / 2 paused / 1 draft / 1 archived
-- ------------------------------------------------------------
INSERT INTO reward_campaigns
  (organization_id, name, description, start_date, end_date, status, target_participants, budget_baht, point_to_baht_rate, is_active, created_date)
VALUES
  (:target_org,'♻️ รักษ์โลกทุกวัน 2026','[MOCK] แคมเปญหลัก เก็บรีไซเคิลรับแต้ม', NOW()-INTERVAL '330 days', NOW()+INTERVAL '90 days','active',300,80000,0.5,TRUE, NOW()-INTERVAL '330 days'),
  (:target_org,'🥤 BYO Bag & Cup Challenge','[MOCK] พกถุงผ้า/แก้วส่วนตัวรับแต้ม', NOW()-INTERVAL '200 days', NOW()+INTERVAL '40 days','active',150,25000,0.5,TRUE, NOW()-INTERVAL '200 days'),
  (:target_org,'📦 กระดาษแลกแต้ม','[MOCK] รวมกระดาษและกล่องลัง', NOW()-INTERVAL '150 days', NOW()+INTERVAL '60 days','active',120,20000,0.6,TRUE, NOW()-INTERVAL '150 days'),
  (:target_org,'🔩 โลหะรีไซเคิล','[MOCK] เก็บโลหะรับแต้มพิเศษ', NOW()-INTERVAL '120 days', NOW()+INTERVAL '80 days','active',80,15000,0.7,TRUE, NOW()-INTERVAL '120 days'),
  (:target_org,'🏖️ เก็บขยะชายหาด CSR','[MOCK] กิจกรรม CSR หยุดชั่วคราว', NOW()-INTERVAL '90 days', NOW()+INTERVAL '20 days','paused',60,10000,0.5,TRUE, NOW()-INTERVAL '90 days'),
  (:target_org,'🎪 Eco Fair Q1 (จบแล้ว)','[MOCK] อีเวนต์ปิดแล้ว', NOW()-INTERVAL '300 days', NOW()-INTERVAL '210 days','paused',100,12000,0.5,TRUE, NOW()-INTERVAL '300 days'),
  (:target_org,'🚀 แคมเปญถัดไป Q4 2026','[MOCK] ร่างรอเผยแพร่', NOW()+INTERVAL '30 days', NOW()+INTERVAL '150 days','draft',200,40000,0.5,TRUE, NOW()+INTERVAL '30 days'),
  (:target_org,'🌱 โครงการนำร่อง (เก่า)','[MOCK] archived', NOW()-INTERVAL '400 days', NOW()-INTERVAL '320 days','archived',50,8000,0.5,FALSE, NOW()-INTERVAL '400 days');

DROP TABLE IF EXISTS _camp;
CREATE TEMP TABLE _camp AS
SELECT id AS campaign_id, name, status,
  CASE WHEN name LIKE '♻️%' THEN 12 WHEN name LIKE '🥤%' THEN 6 WHEN name LIKE '📦%' THEN 5
       WHEN name LIKE '🔩%' THEN 4 WHEN name LIKE '🏖️%' THEN 2 ELSE 1 END::numeric AS weight,
  (status = 'active' OR name LIKE '🏖️%') AS gen
FROM reward_campaigns
WHERE organization_id = :target_org AND description LIKE '[MOCK]%';

-- ------------------------------------------------------------
-- 8. Campaign claim rates (points per kg / per time)
-- ------------------------------------------------------------
INSERT INTO reward_campaign_claims (organization_id, campaign_id, activity_material_id, points, max_claims_per_user)
  SELECT :target_org, c.campaign_id, r.id,
         CASE r.code WHEN 'pet' THEN 6 WHEN 'glass' THEN 5 WHEN 'paper' THEN 4 WHEN 'metal' THEN 8 END, NULL
  FROM _camp c JOIN _ram r ON r.code IN ('pet','glass','paper','metal')
  WHERE c.name LIKE '♻️%'
UNION ALL
  SELECT :target_org, c.campaign_id, r.id, CASE r.code WHEN 'bag' THEN 10 WHEN 'glass' THEN 5 END, 5
  FROM _camp c JOIN _ram r ON r.code IN ('bag','glass') WHERE c.name LIKE '🥤%'
UNION ALL
  SELECT :target_org, c.campaign_id, r.id, 4, NULL FROM _camp c JOIN _ram r ON r.code = 'paper' WHERE c.name LIKE '📦%'
UNION ALL
  SELECT :target_org, c.campaign_id, r.id, 8, NULL FROM _camp c JOIN _ram r ON r.code = 'metal' WHERE c.name LIKE '🔩%'
UNION ALL
  SELECT :target_org, c.campaign_id, r.id, CASE r.code WHEN 'workshop' THEN 50 WHEN 'pet' THEN 6 END, NULL
  FROM _camp c JOIN _ram r ON r.code IN ('workshop','pet') WHERE c.name LIKE '🏖️%';

-- ------------------------------------------------------------
-- 9. Campaign → droppoints
-- ------------------------------------------------------------
INSERT INTO reward_campaign_droppoints (campaign_id, droppoint_id, hash)
SELECT c.campaign_id, d.id, md5('mcdp' || c.campaign_id || d.id || random()::text)
FROM _camp c CROSS JOIN _dp d
WHERE c.gen AND (c.name LIKE '♻️%' OR d.rn <= 3);

-- ------------------------------------------------------------
-- 10. Campaign → catalog links
-- ------------------------------------------------------------
-- Only in-stock ('ok') items are redeemable, so redemptions never drive
-- low/out/archived items to negative net stock (they still show in Inventory).
INSERT INTO reward_campaign_catalog (campaign_id, catalog_id, points_cost, status)
SELECT c.campaign_id, ct.id, ct.points, 'active'
FROM _camp c CROSS JOIN _cat ct
WHERE c.gen AND ct.stockmode = 'ok' AND (c.name LIKE '♻️%' OR ct.rn <= 5);

DROP TABLE IF EXISTS _campcat;
CREATE TEMP TABLE _campcat AS
SELECT row_number() OVER () AS sid, rcc.campaign_id, rcc.catalog_id, rcc.points_cost
FROM reward_campaign_catalog rcc
JOIN _camp c ON c.campaign_id = rcc.campaign_id AND c.gen;

-- ------------------------------------------------------------
-- 11. Campaign targets (main-material kg + activity times)
-- ------------------------------------------------------------
INSERT INTO reward_campaign_targets (reward_campaign_id, target_level, main_material_id, target_amount, target_unit, is_active)
  SELECT c.campaign_id, 'main', mm.mid, mm.amt, 'kg', TRUE
  FROM _camp c JOIN (VALUES (1,3000),(2,800),(4,1500),(5,600)) AS mm(mid,amt) ON TRUE
  WHERE c.name LIKE '♻️%'
UNION ALL
  SELECT c.campaign_id, 'main', 4, 1200, 'kg', TRUE FROM _camp c WHERE c.name LIKE '📦%'
UNION ALL
  SELECT c.campaign_id, 'main', 5, 500,  'kg', TRUE FROM _camp c WHERE c.name LIKE '🔩%';

INSERT INTO reward_campaign_targets (reward_campaign_id, target_level, activity_material_id, target_amount, target_unit, is_active)
SELECT c.campaign_id, 'activity_material', r.id, 500, 'times', TRUE
FROM _camp c JOIN _ram r ON r.code = 'bag' WHERE c.name LIKE '🥤%';

-- ------------------------------------------------------------
-- 12. Inventory receipts (deposits) — vendors × 6 months
-- ------------------------------------------------------------
-- OK items: 6 monthly receipts, rotating vendors (per-row via MATERIALIZED CTE)
WITH dep AS MATERIALIZED (
  SELECT c.id AS cid, c.cost_baht,
         (12 + (random()*30)::int) AS qty,
         (ARRAY['Lazada','Shopee','แม็คโคร','JIB','PowerBuy','Makro Pro'])[1 + floor(random()*6)] AS vendor,
         (mo*30 + (random()*18)::int) AS days_ago
  FROM _cat c CROSS JOIN generate_series(0,5) AS mo
  WHERE c.stockmode = 'ok'
)
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, admin_user_id, note, created_date)
SELECT cid, qty, 'deposit', vendor, cost_baht, qty * cost_baht, (SELECT admin_id FROM _cfg),
       '[MOCK] รับเข้าสต็อก', NOW() - (days_ago || ' days')::interval
FROM dep;

-- LOW item: single small receipt (below min_threshold → low-stock alert)
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, admin_user_id, note, created_date)
SELECT c.id, 6, 'deposit', 'แม็คโคร', c.cost_baht, 6*c.cost_baht, (SELECT admin_id FROM _cfg),
       '[MOCK] รับเข้าล็อตเล็ก', NOW() - INTERVAL '25 days'
FROM _cat c WHERE c.stockmode = 'low';

-- OUT item: deposit then full write-out (net 0 → out of stock)
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, admin_user_id, note, created_date)
SELECT c.id, 4, 'deposit', 'PowerBuy', c.cost_baht, 4*c.cost_baht, (SELECT admin_id FROM _cfg), '[MOCK] รับเข้า', NOW() - INTERVAL '80 days'
FROM _cat c WHERE c.stockmode = 'out'
UNION ALL
SELECT c.id, -4, 'withdraw', NULL, NULL, NULL, (SELECT admin_id FROM _cfg), '[MOCK] เบิกออกหมด', NOW() - INTERVAL '20 days'
FROM _cat c WHERE c.stockmode = 'out';

-- Archived item: residual
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, admin_user_id, note, created_date)
SELECT c.id, 3, 'deposit', 'แม็คโคร', c.cost_baht, 3*c.cost_baht, (SELECT admin_id FROM _cfg), '[MOCK] ของเก่า', NOW() - INTERVAL '150 days'
FROM _cat c WHERE c.stockmode = 'archived';

-- Stock transfers Global → Campaign (paired rows, transfer_group_id)
WITH tg AS (SELECT gen_random_uuid() AS gid, (SELECT campaign_id FROM _camp WHERE name LIKE '♻️%') AS camp,
                   (SELECT id FROM _cat WHERE name LIKE 'กระเป๋า%') AS cat)
INSERT INTO reward_stocks (reward_catalog_id, values, reward_campaign_id, ledger_type, transfer_group_id, admin_user_id, note, created_date)
SELECT cat, -20, NULL, 'transfer', gid, (SELECT admin_id FROM _cfg), '[MOCK] [assign out] กระเป๋า → รักษ์โลก', NOW()-INTERVAL '30 days' FROM tg
UNION ALL
SELECT cat,  20, camp, 'transfer', gid, (SELECT admin_id FROM _cfg), '[MOCK] [assign in] กระเป๋า ← Global',   NOW()-INTERVAL '30 days' FROM tg;

-- ------------------------------------------------------------
-- 13. Claim transactions — ~12 months, growth trend, weighted
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _slots;
CREATE TEMP TABLE _slots AS
SELECT row_number() OVER () AS sid,
       cc.campaign_id, cc.activity_material_id AS ram_id, r.kind, cc.points AS rate,
       cdp.droppoint_id, c.weight AS cweight
FROM reward_campaign_claims cc
JOIN _ram r  ON r.id = cc.activity_material_id
JOIN reward_campaign_droppoints cdp ON cdp.campaign_id = cc.campaign_id
JOIN _camp c ON c.campaign_id = cc.campaign_id AND c.gen;

-- Weighted pick arrays. We index these with a random() drawn per-row in a
-- MATERIALIZED CTE below — an uncorrelated "LATERAL (... ORDER BY random() LIMIT 1)"
-- gets evaluated ONCE and cached, which would clone every row.
DROP TABLE IF EXISTS _arr;
CREATE TEMP TABLE _arr AS
SELECT
  (SELECT array_agg(uid)     FROM (SELECT m.uid FROM _mem m   CROSS JOIN generate_series(1, GREATEST(1, round(m.weight*3))::int)) z) AS mem_w,
  (SELECT array_agg(staff_id) FROM _staff) AS staff_a,
  (SELECT array_agg(sid)     FROM (SELECT s.sid FROM _slots s CROSS JOIN generate_series(1, GREATEST(1, round(s.cweight))::int)) z) AS slot_w,
  (SELECT array_agg(sid)     FROM _campcat) AS cc_a;

-- Historical drops: variable count per day, denser toward present
WITH base AS MATERIALIZED (
  SELECT
    date_trunc('day', NOW()) - (gs.d || ' days')::interval
      + ((random()*10)::int || ' hours')::interval
      + ((random()*59)::int || ' minutes')::interval AS ts,
    random() AS r_mem, random() AS r_slot, random() AS r_staff,
    round((0.5 + random()*14)::numeric, 1) AS val
  FROM generate_series(0, 364) AS gs(d)
       CROSS JOIN LATERAL generate_series(1, (1 + floor(random() * (1 + (365 - gs.d) / 90.0)))::int) AS rep
)
INSERT INTO reward_point_transactions
  (organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
   reward_activity_materials_id, value, unit, points, claimed_date, reference_type, created_date)
SELECT :target_org,
       a.mem_w[1 + floor(b.r_mem * array_length(a.mem_w,1))::int],
       s.campaign_id, s.droppoint_id,
       a.staff_a[1 + floor(b.r_staff * array_length(a.staff_a,1))::int],
       s.ram_id,
       CASE WHEN s.kind = 'kg' THEN b.val ELSE 1 END,
       s.kind,
       CASE WHEN s.kind = 'kg' THEN GREATEST(1, round(b.val * s.rate)) ELSE s.rate END,
       b.ts, 'claim', b.ts
FROM base b
CROSS JOIN _arr a
JOIN _slots s ON s.sid = a.slot_w[1 + floor(b.r_slot * array_length(a.slot_w,1))::int];

-- Guarantee "today" activity (staff online panel + top members today)
WITH base AS MATERIALIZED (
  SELECT random() AS r_mem, random() AS r_slot, random() AS r_staff,
         round((1 + random()*10)::numeric, 1) AS val,
         (random()*90)::int AS mins
  FROM generate_series(1, 12) gg
)
INSERT INTO reward_point_transactions
  (organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
   reward_activity_materials_id, value, unit, points, claimed_date, reference_type, created_date)
SELECT :target_org,
       a.mem_w[1 + floor(b.r_mem * array_length(a.mem_w,1))::int],
       s.campaign_id, s.droppoint_id,
       a.staff_a[1 + floor(b.r_staff * array_length(a.staff_a,1))::int],
       s.ram_id,
       CASE WHEN s.kind = 'kg' THEN b.val ELSE 1 END, s.kind,
       CASE WHEN s.kind = 'kg' THEN GREATEST(1, round(b.val * s.rate)) ELSE s.rate END,
       NOW() - (b.mins || ' minutes')::interval, 'claim', NOW()
FROM base b
CROSS JOIN _arr a
JOIN _slots s ON s.sid = a.slot_w[1 + floor(b.r_slot * array_length(a.slot_w,1))::int];

-- ------------------------------------------------------------
-- 14. Redemptions (~80) + paired negative points + stock-out
-- ------------------------------------------------------------
WITH base AS MATERIALIZED (
  SELECT gs AS n, random() AS r_mem, random() AS r_cc, random() AS r_staff,
         (1 + (random() < 0.2)::int) AS qty,
         CASE WHEN random() < 0.82 THEN 'completed' ELSE 'inprogress' END AS stt,
         (random()*300)::int AS days_ago, (random()*12)::int AS hrs, random() AS h
  FROM generate_series(1, 80) gs
)
INSERT INTO reward_redemptions
  (organization_id, reward_user_id, reward_campaign_id, catalog_id, points_redeemed, quantity, status, hash, staff_id, note, created_date)
SELECT :target_org,
       a.mem_w[1 + floor(b.r_mem * array_length(a.mem_w,1))::int],
       cc.campaign_id, cc.catalog_id, cc.points_cost * b.qty, b.qty,
       b.stt,
       md5('mockred' || :target_org || '_' || b.n || '_' || b.h::text),
       CASE WHEN b.stt = 'completed' THEN a.staff_a[1 + floor(b.r_staff * array_length(a.staff_a,1))::int] ELSE NULL END,
       '[MOCK] redemption',
       NOW() - (b.days_ago || ' days')::interval - (b.hrs || ' hours')::interval
FROM base b
CROSS JOIN _arr a
JOIN _campcat cc ON cc.sid = a.cc_a[1 + floor(b.r_cc * array_length(a.cc_a,1))::int];

-- Negative point transactions for completed redemptions (drives "แต้มที่แลก")
INSERT INTO reward_point_transactions
  (organization_id, reward_user_id, reward_campaign_id, points, reference_type, reference_id, claimed_date, created_date)
SELECT organization_id, reward_user_id, reward_campaign_id, -points_redeemed, 'redeem', id, created_date, created_date
FROM reward_redemptions
WHERE organization_id = :target_org AND note LIKE '[MOCK]%' AND status = 'completed';

-- Stock deductions for completed redemptions
INSERT INTO reward_stocks
  (reward_catalog_id, values, reward_campaign_id, reward_user_id, ledger_type, note, created_date)
SELECT catalog_id, -quantity, reward_campaign_id, reward_user_id, 'redeem', '[MOCK] redeem stock-out', created_date
FROM reward_redemptions
WHERE organization_id = :target_org AND note LIKE '[MOCK]%' AND status = 'completed';

-- ------------------------------------------------------------
-- 15. Campaign expense ledger (cost report)
-- ------------------------------------------------------------
INSERT INTO reward_expense_categories (organization_id, name, is_inventory, is_system, sort_order, is_active) VALUES
  (:target_org, '[MOCK] ค่าแรงงาน',  FALSE, FALSE, 1, TRUE),
  (:target_org, '[MOCK] ค่าขนส่ง',   FALSE, FALSE, 2, TRUE),
  (:target_org, '[MOCK] ค่าการตลาด', FALSE, FALSE, 3, TRUE),
  (:target_org, '[MOCK] อื่นๆ',      FALSE, FALSE, 4, TRUE);

INSERT INTO reward_campaign_expenses
  (organization_id, reward_campaign_id, expense_category_id, amount_baht, expense_date, vendor, note, is_active, created_date)
SELECT :target_org, c.campaign_id, ec.id,
       (500 + (random()*8000)::int)::numeric(12,2),
       (CURRENT_DATE - (mo*30 + (random()*15)::int)),
       (ARRAY['บริษัท เอ จำกัด','ร้าน บี','เอเจนซี่ ซี','ผู้รับเหมา ดี'])[1 + floor(random()*4)],
       '[MOCK] ค่าใช้จ่ายแคมเปญ', TRUE, NOW() - ((mo*30) || ' days')::interval
FROM _camp c
CROSS JOIN (SELECT id FROM reward_expense_categories WHERE organization_id = :target_org AND name LIKE '[MOCK]%') ec
CROSS JOIN generate_series(0,5) mo
WHERE c.gen;

-- ------------------------------------------------------------
-- 16. Staff invites (pending × 2 / used / expired)
-- ------------------------------------------------------------
INSERT INTO reward_staff_invites (hash, organization_id, created_by_id, status, invitee_name, expires_date, created_date)
SELECT 'MOCK' || :target_org || '_inv_p1', :target_org, admin_id, 'pending', 'คุณเอ — front desk',  NOW()+INTERVAL '7 days', NOW()-INTERVAL '2 days' FROM _cfg
UNION ALL
SELECT 'MOCK' || :target_org || '_inv_p2', :target_org, admin_id, 'pending', 'คุณบี — คลังสินค้า',   NOW()+INTERVAL '3 days', NOW()-INTERVAL '1 day'  FROM _cfg
UNION ALL
SELECT 'MOCK' || :target_org || '_inv_ex', :target_org, admin_id, 'pending', 'คุณซี — (หมดอายุ)',   NOW()-INTERVAL '3 days', NOW()-INTERVAL '12 days' FROM _cfg;

INSERT INTO reward_staff_invites (hash, organization_id, created_by_id, status, used_by_id, used_date, expires_date, invitee_name, created_date)
SELECT 'MOCK' || :target_org || '_inv_used', :target_org, cfg.admin_id, 'used', st.reward_user_id,
       NOW()-INTERVAL '30 days', NOW()-INTERVAL '23 days', 'คุณดี — (ใช้แล้ว)', NOW()-INTERVAL '37 days'
FROM _cfg cfg CROSS JOIN LATERAL (SELECT reward_user_id FROM _staff ORDER BY staff_id LIMIT 1) st;

-- ------------------------------------------------------------
-- 17. Summary
-- ------------------------------------------------------------
\echo ''
\echo '=================================================================='
\echo 'Mock seed v3 applied. Summary for target org:'
\echo '=================================================================='

SELECT 'campaigns'      AS resource, COUNT(*) FROM reward_campaigns      WHERE organization_id=:target_org AND description LIKE '[MOCK]%'
UNION ALL SELECT 'catalog',         COUNT(*) FROM reward_catalog         WHERE organization_id=:target_org AND description LIKE '[MOCK]%'
UNION ALL SELECT 'categories',      COUNT(*) FROM reward_catalog_categories WHERE organization_id=:target_org AND description LIKE '[MOCK]%'
UNION ALL SELECT 'activity_materials', COUNT(*) FROM reward_activity_materials WHERE organization_id=:target_org AND description LIKE '[MOCK]%'
UNION ALL SELECT 'droppoints',      COUNT(*) FROM droppoints             WHERE organization_id=:target_org AND name LIKE '[MOCK]%'
UNION ALL SELECT 'members(line)',   COUNT(*) FROM reward_users           WHERE line_user_id LIKE 'MOCK'||:target_org||'_m\_%' ESCAPE '\'
UNION ALL SELECT 'staff',           COUNT(*) FROM reward_users           WHERE line_user_id LIKE 'MOCK'||:target_org||'_s\_%' ESCAPE '\'
UNION ALL SELECT 'walkin',          COUNT(*) FROM reward_users           WHERE created_via='staff_walkin' AND line_status_message='[MOCK]'||:target_org
UNION ALL SELECT 'claims_rules',    COUNT(*) FROM reward_campaign_claims WHERE organization_id=:target_org AND campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%')
UNION ALL SELECT 'targets',         COUNT(*) FROM reward_campaign_targets WHERE reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%')
UNION ALL SELECT 'drops_total',     COUNT(*) FROM reward_point_transactions WHERE organization_id=:target_org AND reference_type='claim' AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%')
UNION ALL SELECT 'drops_today',     COUNT(*) FROM reward_point_transactions WHERE organization_id=:target_org AND reference_type='claim' AND claimed_date >= date_trunc('day', NOW()) AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%')
UNION ALL SELECT 'months_spanned',  COUNT(DISTINCT date_trunc('month', claimed_date)) FROM reward_point_transactions WHERE organization_id=:target_org AND reference_type='claim' AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%')
UNION ALL SELECT 'redemptions',     COUNT(*) FROM reward_redemptions     WHERE organization_id=:target_org AND note LIKE '[MOCK]%'
UNION ALL SELECT 'expenses',        COUNT(*) FROM reward_campaign_expenses WHERE organization_id=:target_org AND note LIKE '[MOCK]%'
UNION ALL SELECT 'invites',         COUNT(*) FROM reward_staff_invites   WHERE organization_id=:target_org AND hash LIKE 'MOCK'||:target_org||'%'
UNION ALL SELECT 'stock_rows',      COUNT(*) FROM reward_stocks          WHERE note LIKE '[MOCK]%' AND reward_catalog_id IN (SELECT id FROM reward_catalog WHERE organization_id=:target_org)
ORDER BY resource;

\echo ''
\echo 'KPI preview (weight kg / GHG kgCO2e / revenue baht):'
SELECT
  round(SUM(rpt.value) FILTER (WHERE rpt.unit='kg')::numeric,1)                     AS total_kg,
  round(SUM(rpt.value * m.calc_ghg) FILTER (WHERE ram.type='material')::numeric,1)  AS ghg_kgco2e,
  round(SUM(rpt.value * ram.selling_price_per_kg) FILTER (WHERE ram.type='material')::numeric,0) AS revenue_baht,
  SUM(rpt.points) FILTER (WHERE rpt.reference_type='claim')::int                    AS points_issued,
  -SUM(rpt.points) FILTER (WHERE rpt.reference_type='redeem')::int                  AS points_redeemed
FROM reward_point_transactions rpt
JOIN reward_activity_materials ram ON ram.id = rpt.reward_activity_materials_id
LEFT JOIN materials m ON m.id = ram.material_id
WHERE rpt.organization_id=:target_org
  AND rpt.reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%');

\echo ''
\echo 'Rank ★ distribution (by cumulative kg):'
SELECT
  CASE
    WHEN kg >= 500 THEN '5 ★★★★★'
    WHEN kg >= 200 THEN '4 ★★★★'
    WHEN kg >= 50  THEN '3 ★★★'
    WHEN kg >= 10  THEN '2 ★★'
    ELSE '1 ★' END AS rank, COUNT(*) AS members
FROM (
  SELECT rpt.reward_user_id, COALESCE(SUM(rpt.value) FILTER (WHERE rpt.unit='kg'),0) AS kg
  FROM reward_users ru
  JOIN reward_point_transactions rpt ON rpt.reward_user_id = ru.id AND rpt.reference_type='claim'
  WHERE ru.line_status_message = '[MOCK]'||:target_org
  GROUP BY rpt.reward_user_id
) t
GROUP BY 1 ORDER BY 1 DESC;

COMMIT;
