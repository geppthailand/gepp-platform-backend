-- Migration 057 — Seed/flag the 15 GHG Protocol Scope 3 categories
-- Date: 2026-05-06
--
-- Idempotent: re-running is safe. Inserts any of the 15 Scope 3 categories
-- that don't yet exist (matched by exact `name`), and flips
-- is_scope3 = TRUE + scope3_category_id on every Scope 3 row regardless of
-- whether it was inserted now or was already present.
--
-- Names match the GHG Protocol Scope 3 Standard categories 1–15 verbatim
-- (see docs/Services/GEPP-ESG/mvp1.1/scope3_deep_dive.html#L340-L484).
--
-- Non-Scope-3 environmental categories (energy, water, biodiversity, etc.),
-- Social, and Governance rows are left untouched and keep is_scope3 = FALSE.

-- Insert any missing Scope 3 categories.
WITH seeds(scope3_id, name, name_th, sort_order) AS (
    VALUES
        (1,  'Purchased goods and services',                       'สินค้าและบริการที่ซื้อ',                              101),
        (2,  'Capital goods',                                       'สินค้าทุน',                                            102),
        (3,  'Fuel- and energy-related activities',                 'กิจกรรมที่เกี่ยวข้องกับเชื้อเพลิงและพลังงาน',           103),
        (4,  'Upstream transportation and distribution',            'การขนส่งและกระจายสินค้าต้นน้ำ',                       104),
        (5,  'Waste generated in operations',                       'ของเสียที่เกิดจากการดำเนินงาน',                       105),
        (6,  'Business travel',                                     'การเดินทางเพื่อธุรกิจ',                                106),
        (7,  'Employee commuting',                                  'การเดินทางมาทำงานของพนักงาน',                          107),
        (8,  'Upstream leased assets',                              'สินทรัพย์เช่าต้นน้ำ',                                  108),
        (9,  'Downstream transportation and distribution',          'การขนส่งและกระจายสินค้าปลายน้ำ',                       109),
        (10, 'Processing of sold products',                         'การแปรรูปสินค้าที่ขาย',                                110),
        (11, 'Use of sold products',                                'การใช้งานสินค้าที่ขาย',                                111),
        (12, 'End-of-life treatment of sold products',              'การจัดการสินค้าที่ขายเมื่อหมดอายุ',                    112),
        (13, 'Downstream leased assets',                            'สินทรัพย์เช่าปลายน้ำ',                                 113),
        (14, 'Franchises',                                          'แฟรนไชส์',                                              114),
        (15, 'Investments',                                         'การลงทุน',                                              115)
)
INSERT INTO esg_data_category (pillar, name, name_th, sort_order, is_scope3, scope3_category_id, is_active, created_date, updated_date)
SELECT 'E', s.name, s.name_th, s.sort_order, TRUE, s.scope3_id, TRUE, NOW(), NOW()
FROM seeds s
WHERE NOT EXISTS (
    SELECT 1 FROM esg_data_category c
    WHERE c.name = s.name
      AND c.deleted_date IS NULL
);

-- Flip is_scope3 + scope3_category_id on every existing Scope 3 row,
-- regardless of whether it was just inserted or pre-existed.
UPDATE esg_data_category c
SET is_scope3 = TRUE,
    scope3_category_id = s.scope3_id,
    updated_date = NOW()
FROM (VALUES
    (1,  'Purchased goods and services'),
    (2,  'Capital goods'),
    (3,  'Fuel- and energy-related activities'),
    (4,  'Upstream transportation and distribution'),
    (5,  'Waste generated in operations'),
    (6,  'Business travel'),
    (7,  'Employee commuting'),
    (8,  'Upstream leased assets'),
    (9,  'Downstream transportation and distribution'),
    (10, 'Processing of sold products'),
    (11, 'Use of sold products'),
    (12, 'End-of-life treatment of sold products'),
    (13, 'Downstream leased assets'),
    (14, 'Franchises'),
    (15, 'Investments')
) AS s(scope3_id, name)
WHERE c.name = s.name
  AND c.deleted_date IS NULL
  AND (c.is_scope3 IS DISTINCT FROM TRUE OR c.scope3_category_id IS DISTINCT FROM s.scope3_id);
