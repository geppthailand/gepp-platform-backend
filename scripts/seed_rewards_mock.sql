-- ============================================================
-- Mock data seed v2 — Comprehensive UI coverage for Rewards admin
-- Org: 25 (TESETER)
-- Idempotent: re-running clears prior [MOCK] data first
--
-- Coverage (every visible UI section drives from real DB rows):
--   Overview:
--     5 KPIs · ImpactTranslator · BigTrendChart 6m · CampaignProgressList ·
--     DropPointBreakdown ×2 · StaffActivePanel · TopMembersTodayPanel
--   Campaigns:
--     list (4) · detail · targets · weekly trend · catalog · droppoints ·
--     transactions · members
--   Inventory:
--     3 KPIs · smart-row × 5 · drawer (receipts/avg cost/history) ·
--     CostReport (4 KPIs / monthly chart 6mo / vendor pie / top costly)
--   Members & Staff:
--     8 members + 2 staff · rank pill ★1-★5 distribution ·
--     invite preview strip · pending invites drawer (3 states)
--   Setup:
--     Checklist 100% · Drop Points grid · Program Settings
--
-- Out of scope (per user):
--   GHG = 0.0 (waiting on conversion factors)
--   Activity feed (no backend endpoint yet)
-- ============================================================

\set ON_ERROR_STOP on

BEGIN;

-- ------------------------------------------------------------
-- 0. Cleanup any prior mock data (idempotent re-runs)
-- ------------------------------------------------------------

DELETE FROM reward_redemptions
 WHERE note LIKE '[MOCK]%'
    OR reward_user_id IN (SELECT id FROM reward_users WHERE line_user_id LIKE 'MOCK\_%' ESCAPE '\')
    OR reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%');

-- Cleanup mock transactions only (NOT all claim/redeem rows!)
-- We identify mock data by FK to mock users or mock campaigns.
DELETE FROM reward_point_transactions
 WHERE reward_user_id IN (SELECT id FROM reward_users WHERE line_user_id LIKE 'MOCK\_%' ESCAPE '\')
    OR reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%');

DELETE FROM reward_stocks
 WHERE note LIKE '[MOCK]%'
    OR reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
    OR reward_catalog_id  IN (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%');

DELETE FROM reward_campaign_catalog
 WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
    OR catalog_id  IN (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%');

DELETE FROM reward_campaign_targets
 WHERE reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%');

DELETE FROM reward_campaign_droppoints
 WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
    OR droppoint_id IN (SELECT id FROM droppoints WHERE name LIKE '[MOCK]%');

DELETE FROM reward_campaign_claims
 WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%');

DELETE FROM reward_campaigns WHERE description LIKE '[MOCK]%';

DELETE FROM droppoints WHERE name LIKE '[MOCK]%';

DELETE FROM reward_staff_invites WHERE hash LIKE 'MOCK\_%' ESCAPE '\';

DELETE FROM organization_reward_users
 WHERE reward_user_id IN (SELECT id FROM reward_users WHERE line_user_id LIKE 'MOCK\_%' ESCAPE '\');

DELETE FROM reward_users WHERE line_user_id LIKE 'MOCK\_%' ESCAPE '\';

DELETE FROM reward_catalog WHERE description LIKE '[MOCK]%';

DELETE FROM reward_catalog_categories WHERE description LIKE '[MOCK]%';

-- ------------------------------------------------------------
-- 1. Reward setup — conversion rate + budget + program name
-- ------------------------------------------------------------

UPDATE reward_setup
   SET program_name        = COALESCE(NULLIF(program_name, ''), 'TESETER Rewards'),
       point_to_baht_rate  = COALESCE(point_to_baht_rate, 0.5000),
       reward_budget_total = COALESCE(reward_budget_total, 100000),
       low_stock_threshold = COALESCE(low_stock_threshold, 10)
 WHERE organization_id = 25;

-- ------------------------------------------------------------
-- 2. Catalog categories
-- ------------------------------------------------------------

INSERT INTO reward_catalog_categories (organization_id, name, description) VALUES
  (25, 'อาหาร & เครื่องดื่ม', '[MOCK] ของกินของใช้รายวัน'),
  (25, 'อิเล็กทรอนิกส์',     '[MOCK] อุปกรณ์อิเล็กทรอนิกส์'),
  (25, 'เพื่อสิ่งแวดล้อม',    '[MOCK] สินค้ารักษ์โลก');

-- ------------------------------------------------------------
-- 3. Catalog items — 5 items × 3 stock states (OK / LOW / OUT) + archived
-- ------------------------------------------------------------

WITH cats AS (
  SELECT id, name FROM reward_catalog_categories
   WHERE organization_id = 25 AND description LIKE '[MOCK]%'
)
INSERT INTO reward_catalog (
  organization_id, name, description, price, cost_baht, unit,
  status, min_threshold, limit_per_user_per_campaign, category_id
) VALUES
  (25, 'กระเป๋าผ้ารีไซเคิล GEPP', '[MOCK] กระเป๋าผ้าโลโก้ GEPP', 80, 35, 'ใบ',
    'active', 10, 2, (SELECT id FROM cats WHERE name = 'เพื่อสิ่งแวดล้อม')),
  (25, 'ขวดน้ำสแตนเลส 500ml', '[MOCK] ขวดน้ำสแตนเลสเก็บอุณหภูมิ', 250, 120, 'ใบ',
    'active', 15, 1, (SELECT id FROM cats WHERE name = 'อาหาร & เครื่องดื่ม')),
  (25, 'หลอดสแตนเลส', '[MOCK] หลอดสแตนเลสพกพา', 60, 25, 'อัน',
    'active', 5, 3, (SELECT id FROM cats WHERE name = 'อาหาร & เครื่องดื่ม')),
  (25, 'ลำโพง Bluetooth พกพา', '[MOCK] ลำโพงแบรนด์ JBL ขนาดเล็ก', 1200, 750, 'เครื่อง',
    'active', 3, 1, (SELECT id FROM cats WHERE name = 'อิเล็กทรอนิกส์')),
  (25, 'แก้ว Tumbler รุ่นเก่า', '[MOCK] รุ่นเลิกผลิต', 150, 80, 'ใบ',
    'archived', 5, 1, (SELECT id FROM cats WHERE name = 'อาหาร & เครื่องดื่ม'));

-- ------------------------------------------------------------
-- 4. Drop points — 3 named locations (reuse user_locations 3669-3671)
-- ------------------------------------------------------------

INSERT INTO droppoints (organization_id, name, hash, type, user_location_id) VALUES
  (25, '[MOCK] จุดรับ Lobby ตึก A',  md5('mock_dp_a_' || now()::text), 'reward_droppoint', 3669),
  (25, '[MOCK] จุดรับ Cafeteria',     md5('mock_dp_b_' || now()::text), 'reward_droppoint', 3670),
  (25, '[MOCK] จุดรับ Office ชั้น 5', md5('mock_dp_c_' || now()::text), 'reward_droppoint', 3671);

-- ------------------------------------------------------------
-- 5. Reward users (8 members + 2 staff)
-- ------------------------------------------------------------

INSERT INTO reward_users (line_user_id, line_display_name, display_name) VALUES
  ('MOCK_member_001', 'สมชาย รักษ์โลก',    'สมชาย'),
  ('MOCK_member_002', 'มาลี ใจดี',         'มาลี'),
  ('MOCK_member_003', 'ธนากร เพื่อโลก',    'ธนากร'),
  ('MOCK_member_004', 'ปาริชาต',           'ปาริชาต'),
  ('MOCK_member_005', 'ภูมิ',              'ภูมิ'),
  ('MOCK_member_006', 'พรทิพย์',           'พรทิพย์'),
  ('MOCK_member_007', 'นิรันดร์',           'นิรันดร์'),
  ('MOCK_member_008', 'อุไรวรรณ',          'อุไรวรรณ'),
  ('MOCK_staff_001',  'พนักงาน Lobby',     'พนักงาน Lobby'),
  ('MOCK_staff_002',  'พนักงาน Cafeteria', 'พนักงาน Cafeteria');

-- Org membership w/ created_date spread across 6 months for new_members trend
INSERT INTO organization_reward_users (reward_user_id, organization_id, role, created_date)
SELECT id, 25, 'user', created_date_offset
FROM reward_users
JOIN (VALUES
  ('MOCK_member_001', NOW() - INTERVAL '170 days'),
  ('MOCK_member_002', NOW() - INTERVAL '140 days'),
  ('MOCK_member_003', NOW() - INTERVAL '110 days'),
  ('MOCK_member_004', NOW() - INTERVAL '80 days'),
  ('MOCK_member_005', NOW() - INTERVAL '60 days'),
  ('MOCK_member_006', NOW() - INTERVAL '40 days'),
  ('MOCK_member_007', NOW() - INTERVAL '15 days'),
  ('MOCK_member_008', NOW() - INTERVAL '3 days')
) AS t(line_uid, created_date_offset)
  ON reward_users.line_user_id = t.line_uid;

INSERT INTO organization_reward_users (reward_user_id, organization_id, role, created_date)
SELECT id, 25, 'staff', NOW() - INTERVAL '150 days'
  FROM reward_users WHERE line_user_id = 'MOCK_staff_001'
UNION ALL
SELECT id, 25, 'staff', NOW() - INTERVAL '90 days'
  FROM reward_users WHERE line_user_id = 'MOCK_staff_002';

-- ------------------------------------------------------------
-- 6. Campaigns (4: active material / active activity / paused / draft)
-- ------------------------------------------------------------

INSERT INTO reward_campaigns (
  organization_id, name, description, start_date, end_date, status,
  target_participants, budget_baht
) VALUES
  (25, 'รักษ์โลก ฤดูร้อน 2026',
   '[MOCK] เก็บขยะรีไซเคิลตลอดฤดูร้อน รับแต้มแลกของรางวัล',
   NOW() - INTERVAL '170 days', NOW() + INTERVAL '60 days', 'active',
   200, 50000),
  (25, 'BYO Bag Challenge',
   '[MOCK] สะสมแต้มจากการพกถุงผ้าและแก้วน้ำส่วนตัว',
   NOW() - INTERVAL '90 days', NOW() + INTERVAL '30 days', 'active',
   100, 15000),
  (25, 'เก็บขยะชายหาด',
   '[MOCK] กิจกรรม Clean Beach หยุดชั่วคราวรอตรวจสอบงบประมาณ',
   NOW() - INTERVAL '60 days', NOW() + INTERVAL '15 days', 'paused',
   50, 8000),
  (25, 'แคมเปญถัดไป Q3 2026',
   '[MOCK] ตัวอย่าง draft ที่ยังไม่ publish',
   NOW() + INTERVAL '30 days', NOW() + INTERVAL '120 days', 'draft',
   150, 30000);

-- Convenience temp table for FK lookups
DROP TABLE IF EXISTS _mock_ids;
CREATE TEMP TABLE _mock_ids AS
SELECT
  (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%' AND name = 'รักษ์โลก ฤดูร้อน 2026')   AS camp_material_active,
  (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%' AND name = 'BYO Bag Challenge')         AS camp_activity_active,
  (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%' AND name = 'เก็บขยะชายหาด')            AS camp_activity_paused,
  (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%' AND name = 'แคมเปญถัดไป Q3 2026')      AS camp_material_draft,
  (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%' AND name = 'กระเป๋าผ้ารีไซเคิล GEPP')   AS cat_bag,
  (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%' AND name = 'ขวดน้ำสแตนเลส 500ml')        AS cat_bottle,
  (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%' AND name = 'หลอดสแตนเลส')                AS cat_straw,
  (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%' AND name = 'ลำโพง Bluetooth พกพา')      AS cat_speaker,
  (SELECT id FROM reward_catalog WHERE description LIKE '[MOCK]%' AND name = 'แก้ว Tumbler รุ่นเก่า')      AS cat_tumbler,
  (SELECT id FROM droppoints WHERE name = '[MOCK] จุดรับ Lobby ตึก A')        AS dp_lobby,
  (SELECT id FROM droppoints WHERE name = '[MOCK] จุดรับ Cafeteria')           AS dp_cafe,
  (SELECT id FROM droppoints WHERE name = '[MOCK] จุดรับ Office ชั้น 5')      AS dp_office,
  (SELECT oru.id FROM organization_reward_users oru
     JOIN reward_users ru ON ru.id = oru.reward_user_id
    WHERE ru.line_user_id = 'MOCK_staff_001' AND oru.role = 'staff' AND oru.organization_id = 25) AS oru_staff_lobby,
  (SELECT oru.id FROM organization_reward_users oru
     JOIN reward_users ru ON ru.id = oru.reward_user_id
    WHERE ru.line_user_id = 'MOCK_staff_002' AND oru.role = 'staff' AND oru.organization_id = 25) AS oru_staff_cafe;

-- ------------------------------------------------------------
-- 7. Campaign → drop-point assignments
-- ------------------------------------------------------------

INSERT INTO reward_campaign_droppoints (campaign_id, droppoint_id, hash)
SELECT camp_material_active, dp_lobby,  md5('mock_cdp_1_' || now()::text) FROM _mock_ids
UNION ALL SELECT camp_material_active, dp_cafe,   md5('mock_cdp_2_' || now()::text) FROM _mock_ids
UNION ALL SELECT camp_material_active, dp_office, md5('mock_cdp_3_' || now()::text) FROM _mock_ids
UNION ALL SELECT camp_activity_active, dp_lobby,  md5('mock_cdp_4_' || now()::text) FROM _mock_ids
UNION ALL SELECT camp_activity_active, dp_cafe,   md5('mock_cdp_5_' || now()::text) FROM _mock_ids
UNION ALL SELECT camp_activity_paused, dp_lobby,  md5('mock_cdp_6_' || now()::text) FROM _mock_ids;

-- ------------------------------------------------------------
-- 8. Campaign targets
-- ------------------------------------------------------------

-- Material campaign: Plastic 500 / Glass 200 / Paper 100 (kg)
-- (only main_materials w/ linked rams in org 25 — ram 4,5,10→Plastic, ram 7→Glass, ram 6→Paper)
INSERT INTO reward_campaign_targets (reward_campaign_id, target_level, main_material_id, target_amount, target_unit)
SELECT camp_material_active, 'main', 1, 500, 'kg' FROM _mock_ids
UNION ALL SELECT camp_material_active, 'main', 2, 200, 'kg' FROM _mock_ids
UNION ALL SELECT camp_material_active, 'main', 4, 100, 'kg' FROM _mock_ids;

-- Activity campaign: ใช้ถุงผ้า (ram 8) 200 + test Activity (ram 3) 50
INSERT INTO reward_campaign_targets (reward_campaign_id, target_level, activity_material_id, target_amount, target_unit)
SELECT camp_activity_active, 'activity_material', 8, 200, 'times' FROM _mock_ids
UNION ALL SELECT camp_activity_active, 'activity_material', 3, 50,  'times' FROM _mock_ids;

INSERT INTO reward_campaign_targets (reward_campaign_id, target_level, main_material_id, target_amount, target_unit)
SELECT camp_material_draft, 'main', 4, 1000, 'kg' FROM _mock_ids;

-- ------------------------------------------------------------
-- 9. Campaign claim rates (points per kg / per times)
-- ------------------------------------------------------------

-- Material rates: ram 4 (พลาสติกรวม) 4pt/kg, ram 5 (PET) 6pt/kg, ram 6 (Paper) 3pt/kg, ram 7 (Glass) 5pt/kg
INSERT INTO reward_campaign_claims (organization_id, campaign_id, activity_material_id, points)
SELECT 25, camp_material_active, 4, 4 FROM _mock_ids
UNION ALL SELECT 25, camp_material_active, 5, 6 FROM _mock_ids
UNION ALL SELECT 25, camp_material_active, 6, 3 FROM _mock_ids
UNION ALL SELECT 25, camp_material_active, 7, 5 FROM _mock_ids;

-- Activity rates: ram 8 (ถุงผ้า) 10pt/times, ram 3 (test) 5pt/times
INSERT INTO reward_campaign_claims (organization_id, campaign_id, activity_material_id, points, max_claims_per_user)
SELECT 25, camp_activity_active, 8, 10, 5 FROM _mock_ids
UNION ALL SELECT 25, camp_activity_active, 3, 5,  10 FROM _mock_ids;

INSERT INTO reward_campaign_claims (organization_id, campaign_id, activity_material_id, points)
SELECT 25, camp_activity_paused, 8, 8 FROM _mock_ids;

-- ------------------------------------------------------------
-- 9.5 Campaign → catalog items linkage (for "Catalog tab" in campaign detail)
-- ------------------------------------------------------------

INSERT INTO reward_campaign_catalog (campaign_id, catalog_id, points_cost, status)
SELECT camp_material_active, cat_bag,     80,   'active' FROM _mock_ids
UNION ALL SELECT camp_material_active, cat_bottle,  500,  'active' FROM _mock_ids
UNION ALL SELECT camp_material_active, cat_speaker, 1200, 'active' FROM _mock_ids
UNION ALL SELECT camp_activity_active, cat_bag,     80,   'active' FROM _mock_ids
UNION ALL SELECT camp_activity_active, cat_straw,   30,   'active' FROM _mock_ids;

-- ------------------------------------------------------------
-- 10. Inventory receipts (deposits) — spread across 6 months for Cost Report monthly chart
-- ------------------------------------------------------------

-- Bag (cat_bag): receipts each month, vendors rotating
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, note, created_date)
SELECT cat_bag, 30, 'deposit', 'Lazada',   35, 1050, '[MOCK] รับเข้า Dec', NOW() - INTERVAL '170 days' FROM _mock_ids
UNION ALL SELECT cat_bag, 25, 'deposit', 'Shopee',   38, 950,  '[MOCK] รับเข้า Jan', NOW() - INTERVAL '140 days' FROM _mock_ids
UNION ALL SELECT cat_bag, 40, 'deposit', 'แม็คโคร',  32, 1280, '[MOCK] รับเข้า Feb', NOW() - INTERVAL '110 days' FROM _mock_ids
UNION ALL SELECT cat_bag, 20, 'deposit', 'Lazada',   36, 720,  '[MOCK] รับเข้า Mar', NOW() - INTERVAL '80 days'  FROM _mock_ids
UNION ALL SELECT cat_bag, 30, 'deposit', 'Shopee',   38, 1140, '[MOCK] รับเข้า Apr', NOW() - INTERVAL '40 days'  FROM _mock_ids
UNION ALL SELECT cat_bag, 25, 'deposit', 'JIB',      40, 1000, '[MOCK] รับเข้า May', NOW() - INTERVAL '5 days'   FROM _mock_ids;

-- Bottle (low stock - small total)
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, note, created_date)
SELECT cat_bottle, 8, 'deposit', 'แม็คโคร', 120, 960, '[MOCK] รับเข้าเริ่มต้น', NOW() - INTERVAL '10 days' FROM _mock_ids;

-- Speaker (high value, multi-month receipts)
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, note, created_date)
SELECT cat_speaker, 3, 'deposit', 'PowerBuy', 750, 2250, '[MOCK] ล็อตแรก',   NOW() - INTERVAL '150 days' FROM _mock_ids
UNION ALL SELECT cat_speaker, 2, 'deposit', 'JIB',      780, 1560, '[MOCK] ล็อตสอง',   NOW() - INTERVAL '70 days' FROM _mock_ids
UNION ALL SELECT cat_speaker, 3, 'deposit', 'PowerBuy', 760, 2280, '[MOCK] ล็อตสาม',   NOW() - INTERVAL '20 days' FROM _mock_ids;

-- Tumbler archived (residual stock)
INSERT INTO reward_stocks (reward_catalog_id, values, ledger_type, vendor, unit_price, total_price, note, created_date)
SELECT cat_tumbler, 5,  'deposit',  'แม็คโคร', 80, 400, '[MOCK] เก่า',                 NOW() - INTERVAL '160 days' FROM _mock_ids
UNION ALL SELECT cat_tumbler, -2, 'withdraw', NULL,      NULL, NULL, '[MOCK] write-off ของชำรุด', NOW() - INTERVAL '120 days' FROM _mock_ids;

-- ------------------------------------------------------------
-- 11. Stock transfers (assigning Global → Campaign, paired rows)
-- ------------------------------------------------------------

WITH tg AS (SELECT gen_random_uuid() AS gid)
INSERT INTO reward_stocks (reward_catalog_id, values, reward_campaign_id, ledger_type, transfer_group_id, note, created_date)
SELECT cat_bag, -20, NULL,                    'transfer', tg.gid, '[MOCK] [assign out] กระเป๋า → รักษ์โลก',
       NOW() - INTERVAL '12 days' FROM _mock_ids, tg
UNION ALL
SELECT cat_bag,  20, m.camp_material_active, 'transfer', tg.gid, '[MOCK] [assign in] กระเป๋า ← Global',
       NOW() - INTERVAL '12 days' FROM _mock_ids m, tg;

WITH tg AS (SELECT gen_random_uuid() AS gid)
INSERT INTO reward_stocks (reward_catalog_id, values, reward_campaign_id, ledger_type, transfer_group_id, note, created_date)
SELECT cat_speaker, -2, NULL,                    'transfer', tg.gid, '[MOCK] [assign out] ลำโพง → รักษ์โลก', NOW() - INTERVAL '5 days' FROM _mock_ids, tg
UNION ALL
SELECT cat_speaker,  2, m.camp_material_active, 'transfer', tg.gid, '[MOCK] [assign in] ลำโพง ← Global',    NOW() - INTERVAL '5 days' FROM _mock_ids m, tg;

WITH tg AS (SELECT gen_random_uuid() AS gid)
INSERT INTO reward_stocks (reward_catalog_id, values, reward_campaign_id, ledger_type, transfer_group_id, note, created_date)
SELECT cat_bag, -5, NULL,                    'transfer', tg.gid, '[MOCK] [assign out] กระเป๋า → BYO',     NOW() - INTERVAL '4 days' FROM _mock_ids, tg
UNION ALL
SELECT cat_bag,  5, m.camp_activity_active, 'transfer', tg.gid, '[MOCK] [assign in] กระเป๋า ← Global',  NOW() - INTERVAL '4 days' FROM _mock_ids m, tg;

-- ------------------------------------------------------------
-- 12. Drop transactions — spread 6 months + staff_id wired + heavy drops for ranks
--     Material drops use ram 4/5/6/7 (linked to main_materials)
--     Activity drops use ram 8 / 3
-- ------------------------------------------------------------

-- Helper macro: insert a claim transaction
-- columns: org=25, reference_type='claim'
-- staff_id alternates between MOCK_staff_001 (lobby) and MOCK_staff_002 (cafe)

-- ===== TODAY (5 drops — Top Members Today + Staff online) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 4, 8.5, 'kg', 34,
       NOW() - INTERVAL '2 hours', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 5, 12.0, 'kg', 72,
       NOW() - INTERVAL '4 hours', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, dp_cafe, oru_staff_cafe, 7, 6.0, 'kg', 30,
       NOW() - INTERVAL '6 hours', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_005'),
       camp_activity_active, dp_lobby, oru_staff_lobby, 8, 1, 'times', 10,
       NOW() - INTERVAL '3 hours', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_007'),
       camp_activity_active, dp_cafe, oru_staff_cafe, 8, 1, 'times', 10,
       NOW() - INTERVAL '1 hour', 'claim' FROM _mock_ids;

-- ===== Last 7 days (10 drops — fills BigTrendChart 7d/14d range) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 4, 9.0, 'kg', 36,
       NOW() - INTERVAL '1 day', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, dp_cafe, oru_staff_cafe, 4, 5.5, 'kg', 22,
       NOW() - INTERVAL '2 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 5, 11.5, 'kg', 69,
       NOW() - INTERVAL '3 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_004'),
       camp_material_active, dp_lobby, oru_staff_lobby, 6, 4.0, 'kg', 12,
       NOW() - INTERVAL '4 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_006'),
       camp_material_active, dp_office, oru_staff_lobby, 7, 8.0, 'kg', 40,
       NOW() - INTERVAL '5 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_008'),
       camp_material_active, dp_cafe, oru_staff_cafe, 4, 3.0, 'kg', 12,
       NOW() - INTERVAL '6 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_activity_active, dp_lobby, oru_staff_lobby, 8, 1, 'times', 10,
       NOW() - INTERVAL '2 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_activity_active, dp_lobby, oru_staff_lobby, 8, 1, 'times', 10,
       NOW() - INTERVAL '4 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_006'),
       camp_activity_active, dp_cafe, oru_staff_cafe, 3, 1, 'times', 5,
       NOW() - INTERVAL '5 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_004'),
       camp_activity_active, dp_lobby, oru_staff_lobby, 8, 1, 'times', 10,
       NOW() - INTERVAL '6 days', 'claim' FROM _mock_ids;

-- ===== Last 30 days (5 drops — Apr month bucket) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 5, 25.0, 'kg', 150,
       NOW() - INTERVAL '12 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_cafe, oru_staff_cafe, 4, 30.0, 'kg', 120,
       NOW() - INTERVAL '18 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 5, 70.0, 'kg', 420,
       NOW() - INTERVAL '14 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, dp_lobby, oru_staff_lobby, 7, 12.0, 'kg', 60,
       NOW() - INTERVAL '20 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_005'),
       camp_material_active, dp_cafe, oru_staff_cafe, 6, 6.5, 'kg', 20,
       NOW() - INTERVAL '25 days', 'claim' FROM _mock_ids;

-- ===== ~60 days ago (Mar bucket) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 4, 28.0, 'kg', 112,
       NOW() - INTERVAL '50 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_office, oru_staff_lobby, 5, 35.0, 'kg', 210,
       NOW() - INTERVAL '55 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 7, 80.0, 'kg', 400,
       NOW() - INTERVAL '52 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, dp_cafe, oru_staff_cafe, 6, 8.0, 'kg', 24,
       NOW() - INTERVAL '60 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_004'),
       camp_material_active, dp_lobby, oru_staff_lobby, 4, 5.0, 'kg', 20,
       NOW() - INTERVAL '58 days', 'claim' FROM _mock_ids;

-- ===== ~90 days ago (Feb bucket) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 5, 32.0, 'kg', 192,
       NOW() - INTERVAL '85 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 5, 75.0, 'kg', 450,
       NOW() - INTERVAL '88 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_cafe, oru_staff_cafe, 4, 25.0, 'kg', 100,
       NOW() - INTERVAL '95 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, dp_lobby, oru_staff_lobby, 7, 10.0, 'kg', 50,
       NOW() - INTERVAL '92 days', 'claim' FROM _mock_ids;

-- ===== ~120 days ago (Jan bucket) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_office, oru_staff_lobby, 4, 40.0, 'kg', 160,
       NOW() - INTERVAL '115 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_lobby, oru_staff_lobby, 5, 95.0, 'kg', 570,
       NOW() - INTERVAL '120 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, dp_cafe, oru_staff_cafe, 6, 12.0, 'kg', 36,
       NOW() - INTERVAL '125 days', 'claim' FROM _mock_ids;

-- ===== ~150 days ago (Dec bucket) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 5, 50.0, 'kg', 300,
       NOW() - INTERVAL '155 days', 'claim' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 7, 90.0, 'kg', 450,
       NOW() - INTERVAL '160 days', 'claim' FROM _mock_ids;

-- ===== ~180 days ago (Nov bucket) =====
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, droppoint_id, staff_id,
  reward_activity_materials_id, value, unit, points, claimed_date, reference_type
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, dp_lobby, oru_staff_lobby, 4, 35.0, 'kg', 140,
       NOW() - INTERVAL '170 days', 'claim' FROM _mock_ids
-- Booster drops to ensure full ★1-★5 rank distribution
UNION ALL
-- member_003 → ★5 (≥500kg total)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, dp_office, oru_staff_lobby, 5, 70.0, 'kg', 420,
       NOW() - INTERVAL '175 days', 'claim' FROM _mock_ids
UNION ALL
-- member_006 → ★2 (~30kg)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_006'),
       camp_material_active, dp_cafe, oru_staff_cafe, 6, 22.0, 'kg', 66,
       NOW() - INTERVAL '40 days', 'claim' FROM _mock_ids
UNION ALL
-- member_007 → ★2 (~12kg via single drop)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_007'),
       camp_material_active, dp_lobby, oru_staff_lobby, 4, 12.0, 'kg', 48,
       NOW() - INTERVAL '10 days', 'claim' FROM _mock_ids;

-- ------------------------------------------------------------
-- 13. Redemptions (12 entries) + paired negative-points transactions
-- ------------------------------------------------------------

-- Completed redemptions
INSERT INTO reward_redemptions (
  organization_id, reward_user_id, reward_campaign_id, catalog_id,
  points_redeemed, quantity, status, hash, note, created_date
)
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, cat_bag, 80, 1, 'completed',
       md5('mock_red_001_' || now()::text), '[MOCK] redeemed at Lobby',
       NOW() - INTERVAL '5 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, cat_bag, 80, 1, 'completed',
       md5('mock_red_002_' || now()::text), '[MOCK] redeemed at Cafeteria',
       NOW() - INTERVAL '20 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, cat_speaker, 1200, 1, 'completed',
       md5('mock_red_003_' || now()::text), '[MOCK] ลำโพง',
       NOW() - INTERVAL '40 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_006'),
       camp_activity_active, cat_bag, 80, 1, 'completed',
       md5('mock_red_004_' || now()::text), '[MOCK] BYO Bag prize',
       NOW() - INTERVAL '15 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_001'),
       camp_material_active, cat_bottle, 500, 1, 'completed',
       md5('mock_red_005_' || now()::text), '[MOCK] ขวดน้ำ',
       NOW() - INTERVAL '60 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, cat_bag, 80, 2, 'completed',
       md5('mock_red_006_' || now()::text), '[MOCK] กระเป๋า x2',
       NOW() - INTERVAL '90 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_002'),
       camp_material_active, cat_speaker, 1200, 1, 'completed',
       md5('mock_red_007_' || now()::text), '[MOCK] ลำโพง',
       NOW() - INTERVAL '120 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_004'),
       camp_activity_active, cat_straw, 30, 1, 'completed',
       md5('mock_red_008_' || now()::text), '[MOCK] หลอด',
       NOW() - INTERVAL '8 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_005'),
       camp_material_active, cat_bag, 80, 1, 'completed',
       md5('mock_red_009_' || now()::text), '[MOCK] กระเป๋า',
       NOW() - INTERVAL '30 days' FROM _mock_ids
-- In-progress
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_003'),
       camp_material_active, cat_speaker, 1200, 1, 'inprogress',
       md5('mock_red_010_' || now()::text), '[MOCK] รอจัดส่ง',
       NOW() - INTERVAL '2 days' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_006'),
       camp_material_active, cat_bag, 80, 1, 'inprogress',
       md5('mock_red_011_' || now()::text), '[MOCK] รอจัดส่ง',
       NOW() - INTERVAL '1 day' FROM _mock_ids
UNION ALL
SELECT 25, (SELECT id FROM reward_users WHERE line_user_id = 'MOCK_member_007'),
       camp_activity_active, cat_bag, 80, 1, 'inprogress',
       md5('mock_red_012_' || now()::text), '[MOCK] รอจัดส่ง',
       NOW() - INTERVAL '4 hours' FROM _mock_ids;

-- Negative-points transactions paired w/ COMPLETED redemptions
-- (Drives "แต้มที่แลก" KPI sum points<0)
INSERT INTO reward_point_transactions (
  organization_id, reward_user_id, reward_campaign_id, points,
  reference_type, reference_id, claimed_date, image_ids
)
SELECT rr.organization_id, rr.reward_user_id, rr.reward_campaign_id,
       -rr.points_redeemed, 'redeem', rr.id, rr.created_date, NULL
FROM reward_redemptions rr
WHERE rr.note LIKE '[MOCK]%' AND rr.status = 'completed';

-- Stock deductions paired w/ completed redemptions (-1 each, ledger_type='redeem')
INSERT INTO reward_stocks (
  reward_catalog_id, values, reward_campaign_id, reward_user_id,
  ledger_type, note, created_date
)
SELECT rr.catalog_id, -rr.quantity, rr.reward_campaign_id, rr.reward_user_id,
       'redeem', '[MOCK] redeem stock-out', rr.created_date
FROM reward_redemptions rr
WHERE rr.note LIKE '[MOCK]%' AND rr.status = 'completed';

-- ------------------------------------------------------------
-- 14. Staff Invites (3 entries — pending / used / expired)
-- ------------------------------------------------------------

INSERT INTO reward_staff_invites (
  hash, organization_id, created_by_id, status, expires_date, created_date
)
VALUES
  -- Pending (active, expires future)
  ('MOCK_invite_pending_' || md5(random()::text)::varchar(40),
   25, 3667, 'pending', NOW() + INTERVAL '7 days', NOW() - INTERVAL '2 days');

INSERT INTO reward_staff_invites (
  hash, organization_id, created_by_id, status,
  used_by_id, used_date, expires_date, created_date
)
SELECT
  'MOCK_invite_used_' || md5(random()::text)::varchar(40),
  25, 3667, 'used',
  ru.id, NOW() - INTERVAL '60 days', NOW() - INTERVAL '53 days', NOW() - INTERVAL '67 days'
FROM reward_users ru
WHERE ru.line_user_id = 'MOCK_staff_002'
LIMIT 1;

INSERT INTO reward_staff_invites (
  hash, organization_id, created_by_id, status, expires_date, created_date
)
VALUES
  -- Expired (past expires_date, status still pending)
  ('MOCK_invite_expired_' || md5(random()::text)::varchar(40),
   25, 3667, 'pending', NOW() - INTERVAL '5 days', NOW() - INTERVAL '14 days');

-- ------------------------------------------------------------
-- 15. Summary report
-- ------------------------------------------------------------

\echo
\echo '======================================================'
\echo 'Mock seed v2 applied. Summary for org 25 (TESETER):'
\echo '======================================================'

SELECT 'campaigns'         AS resource, COUNT(*) FROM reward_campaigns         WHERE organization_id=25 AND description LIKE '[MOCK]%'
UNION ALL SELECT 'catalog',     COUNT(*) FROM reward_catalog                  WHERE organization_id=25 AND description LIKE '[MOCK]%'
UNION ALL SELECT 'categories',  COUNT(*) FROM reward_catalog_categories       WHERE organization_id=25 AND description LIKE '[MOCK]%'
UNION ALL SELECT 'campaign_catalog_links', COUNT(*) FROM reward_campaign_catalog WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
UNION ALL SELECT 'droppoints',  COUNT(*) FROM droppoints                      WHERE organization_id=25 AND name LIKE '[MOCK]%'
UNION ALL SELECT 'members',     COUNT(*) FROM reward_users                    WHERE line_user_id LIKE 'MOCK\_member\_%' ESCAPE '\'
UNION ALL SELECT 'staff',       COUNT(*) FROM reward_users                    WHERE line_user_id LIKE 'MOCK\_staff\_%'  ESCAPE '\'
UNION ALL SELECT 'targets',     COUNT(*) FROM reward_campaign_targets         WHERE reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
UNION ALL SELECT 'claims',      COUNT(*) FROM reward_campaign_claims          WHERE organization_id=25 AND campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
UNION ALL SELECT 'drops_total (mock)',   COUNT(*) FROM reward_point_transactions WHERE organization_id=25 AND reference_type='claim'  AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
UNION ALL SELECT 'drops_today (mock)',   COUNT(*) FROM reward_point_transactions WHERE organization_id=25 AND reference_type='claim'  AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%') AND claimed_date >= date_trunc('day', NOW())
UNION ALL SELECT 'drops_with_staff_id',  COUNT(*) FROM reward_point_transactions WHERE organization_id=25 AND reference_type='claim'  AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%') AND staff_id IS NOT NULL
UNION ALL SELECT 'months_spanned',       COUNT(DISTINCT date_trunc('month', claimed_date)) FROM reward_point_transactions WHERE organization_id=25 AND reference_type='claim' AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
UNION ALL SELECT 'redeem_tx (mock)',     COUNT(*) FROM reward_point_transactions WHERE organization_id=25 AND reference_type='redeem' AND reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE description LIKE '[MOCK]%')
UNION ALL SELECT 'redemptions', COUNT(*) FROM reward_redemptions              WHERE organization_id=25 AND note LIKE '[MOCK]%'
UNION ALL SELECT 'staff_invites', COUNT(*) FROM reward_staff_invites          WHERE organization_id=25 AND hash LIKE 'MOCK\_%' ESCAPE '\'
UNION ALL SELECT 'stock_rows',  COUNT(*) FROM reward_stocks                   WHERE note LIKE '[MOCK]%';

\echo
\echo 'Per-member kg totals (★rank thresholds: ≥10=★2, ≥50=★3, ≥200=★4, ≥500=★5):'
SELECT
  ru.line_user_id,
  COALESCE(SUM(rpt.value) FILTER (WHERE rpt.unit='kg'), 0)::numeric(10,1) AS total_kg,
  CASE
    WHEN COALESCE(SUM(rpt.value) FILTER (WHERE rpt.unit='kg'), 0) >= 500 THEN '★★★★★'
    WHEN COALESCE(SUM(rpt.value) FILTER (WHERE rpt.unit='kg'), 0) >= 200 THEN '★★★★'
    WHEN COALESCE(SUM(rpt.value) FILTER (WHERE rpt.unit='kg'), 0) >= 50  THEN '★★★'
    WHEN COALESCE(SUM(rpt.value) FILTER (WHERE rpt.unit='kg'), 0) >= 10  THEN '★★'
    ELSE '★'
  END AS rank
FROM reward_users ru
LEFT JOIN reward_point_transactions rpt
  ON rpt.reward_user_id = ru.id AND rpt.reference_type = 'claim'
WHERE ru.line_user_id LIKE 'MOCK\_member\_%' ESCAPE '\'
GROUP BY ru.id, ru.line_user_id
ORDER BY total_kg DESC;

COMMIT;
