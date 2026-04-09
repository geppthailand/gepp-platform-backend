-- ============================================================
-- Research-Based ESG Category Expansion
-- New categories: Materials & Circular Economy, Product Responsibility,
--   Customer Privacy, Economic Performance, Tax Transparency
-- Expanded datapoints: Scope 1 (Process, EF source, GHG breakdown),
--   Scope 2 (market-based), Water (stress area), OHS (GRI 403-9/10),
--   Biodiversity (IUCN), Air (ODS), Diversity (pay gap), Board (TCFD/CDP)
-- ============================================================

-- ==========================================
-- NEW E CATEGORY: Materials & Circular Economy (GRI 301)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order)
SELECT 'E', 'Materials & Circular Economy', 'วัสดุและเศรษฐกิจหมุนเวียน',
       'Materials consumption, recycled inputs, and product circularity (GRI 301)', 9
WHERE NOT EXISTS (SELECT 1 FROM esg_data_category WHERE name = 'Materials & Circular Economy');

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Materials Used', 'วัสดุที่ใช้', 'Total materials consumed by type and source (GRI 301-1, 301-2)', 1),
    ('Products Reclaimed', 'ผลิตภัณฑ์ที่เรียกคืน', 'Products and packaging reclaimed at end of life (GRI 301-3)', 2)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Materials & Circular Economy'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name);

-- Materials Used datapoints
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Material name', 'ชื่อวัสดุ', 'Name of material used', NULL, 'text', 1),
    ('Material weight', 'น้ำหนักวัสดุ', 'Total weight or volume used', 'kg', 'numeric', 2),
    ('Renewable/non-renewable', 'หมุนเวียน/ไม่หมุนเวียน', 'Classification of material source', NULL, 'text', 3),
    ('Recycled input %', 'สัดส่วนวัสดุรีไซเคิล', 'Percentage of recycled materials used', '%', 'numeric', 4),
    ('Supplier/source', 'ผู้จัดจำหน่าย/แหล่ง', 'Material supplier', NULL, 'text', 5),
    ('Certification', 'การรับรอง', 'Sustainability certification (FSC, RSPO, etc.)', NULL, 'text', 6),
    ('Forest-risk commodity', 'สินค้าเสี่ยงต่อป่าไม้', 'Whether forest-risk commodity (timber, palm oil, soy, cattle)', NULL, 'text', 7),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total material cost', NULL, 'numeric', 8),
    ('Record date', 'วันที่บันทึก', 'Date of record', NULL, 'date', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Materials Used'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- Products Reclaimed datapoints
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Product/packaging type', 'ประเภทผลิตภัณฑ์/บรรจุภัณฑ์', 'Type of product or packaging reclaimed', NULL, 'text', 1),
    ('Weight reclaimed', 'น้ำหนักที่เรียกคืน', 'Total weight reclaimed', 'kg', 'numeric', 2),
    ('Reclaim rate', 'อัตราการเรียกคืน', 'Percentage of products sold that are reclaimed', '%', 'numeric', 3),
    ('Reclaim method', 'วิธีการเรียกคืน', 'Take-back program, deposit-refund, etc.', NULL, 'text', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Products Reclaimed'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- SCOPE 1: Add Process Emissions subcategory
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Process Emissions', 'การปล่อยจากกระบวนการ', 'Non-combustion industrial process emissions (GHG Protocol Ch.4)', 4
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 1'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Carbon Emissions Scope 1') AND es.name = 'Process Emissions');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Process description', 'รายละเอียดกระบวนการ', 'Industrial process producing emissions', NULL, 'text', 1),
    ('Production volume', 'ปริมาณการผลิต', 'Volume of product produced', 'tonnes', 'numeric', 2),
    ('Emission factor', 'ค่าสัมประสิทธิ์การปล่อย', 'Process-specific EF', 'tCO2e/tonne', 'numeric', 3),
    ('Total emissions', 'การปล่อยก๊าซรวม', 'Total process emissions', 'tCO2e', 'numeric', 4),
    ('Record date', 'วันที่บันทึก', 'Production period', NULL, 'date', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Process Emissions'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- SCOPE 1: Add GHG breakdown + EF source to existing subcategories
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Emission factor source', 'แหล่งค่า EF', 'Source of emission factor (DEFRA, EPA, IEA, IPCC, TGO)', NULL, 'text', 13),
    ('GWP source', 'แหล่งค่า GWP', 'IPCC Assessment Report version (AR4/AR5/AR6)', NULL, 'text', 14),
    ('CO2 emissions', 'การปล่อย CO2', 'Carbon dioxide component', 'tCO2', 'numeric', 15),
    ('CH4 emissions', 'การปล่อย CH4', 'Methane component', 'tCO2e', 'numeric', 16),
    ('N2O emissions', 'การปล่อย N2O', 'Nitrous oxide component', 'tCO2e', 'numeric', 17),
    ('Facility/location', 'สถานที่/สาขา', 'Facility where combustion occurred', NULL, 'text', 18)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Stationary Combustion'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- SCOPE 2: Add market-based fields to Purchased Electricity
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Market-based emission factor', 'ค่าสัมประสิทธิ์ตามตลาด', 'EF from contractual instruments (REC, PPA, green tariff)', 'kgCO2e/kWh', 'numeric', 12),
    ('Location-based emissions', 'การปล่อยตามสถานที่', 'Scope 2 using grid-average EF', 'tCO2e', 'numeric', 13),
    ('Market-based emissions', 'การปล่อยตามตลาด', 'Scope 2 using contractual instruments', 'tCO2e', 'numeric', 14)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Purchased Electricity'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- WATER: Add water stress fields
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Water stress area', 'พื้นที่ขาดแคลนน้ำ', 'Whether from water-stressed area (WRI Aqueduct)', NULL, 'text', 10),
    ('Water stress assessment tool', 'เครื่องมือประเมิน', 'WRI Aqueduct / WWF Water Risk Filter', NULL, 'text', 11)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Water Withdrawal'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- WASTE: Add Plastics subcategory (CDP 2025 Module 10)
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Plastics', 'พลาสติก', 'Plastic usage, recycled content, and circular economy (CDP Module 10)', 4
FROM esg_data_category WHERE name = 'Waste Management'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Waste Management') AND es.name = 'Plastics');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Total plastic weight', 'น้ำหนักพลาสติกรวม', 'Total weight of plastic polymers used', 'tonnes', 'numeric', 1),
    ('Virgin plastic %', 'สัดส่วนพลาสติกบริสุทธิ์', 'Percentage virgin (non-recycled) content', '%', 'numeric', 2),
    ('Recycled plastic %', 'สัดส่วนพลาสติกรีไซเคิล', 'Percentage recycled content', '%', 'numeric', 3),
    ('Plastic type', 'ประเภทพลาสติก', 'PET, HDPE, LDPE, PP, PS, PVC, Other', NULL, 'text', 4),
    ('Circular economy strategy', 'กลยุทธ์เศรษฐกิจหมุนเวียน', 'Description of circular approach', NULL, 'text', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Plastics'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- ENERGY: Add Energy Sold subcategory (GRI 302-1)
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Energy Sold', 'พลังงานที่ขาย', 'Energy sold to external parties (GRI 302-1)', 4
FROM esg_data_category WHERE name = 'Energy Management'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Energy Management') AND es.name = 'Energy Sold');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Energy type sold', 'ประเภทพลังงานที่ขาย', 'Electricity, heating, cooling, steam sold', NULL, 'text', 1),
    ('Energy volume sold', 'ปริมาณพลังงานที่ขาย', 'Total energy sold', 'kWh', 'numeric', 2),
    ('Revenue from energy sold', 'รายได้จากขายพลังงาน', 'Revenue earned', NULL, 'numeric', 3),
    ('Buyer name', 'ชื่อผู้ซื้อ', 'Entity purchasing the energy', NULL, 'text', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Energy Sold'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- AIR: Add ODS Emissions subcategory (GRI 305-6)
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'ODS Emissions', 'การปล่อยสารทำลายชั้นโอโซน', 'Ozone-depleting substance emissions (GRI 305-6)', 3
FROM esg_data_category WHERE name = 'Air Quality & Pollution'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Air Quality & Pollution') AND es.name = 'ODS Emissions');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('ODS substance', 'สารทำลายชั้นโอโซน', 'Type of ODS (CFC, HCFC, Halon, etc.)', NULL, 'text', 1),
    ('ODS production', 'ปริมาณ ODS ที่ผลิต', 'Production quantity', 'kg CFC-11 eq', 'numeric', 2),
    ('ODS imports/exports', 'การนำเข้า/ส่งออก ODS', 'Net imports minus exports', 'kg CFC-11 eq', 'numeric', 3),
    ('ODS emissions', 'การปล่อย ODS', 'Total ODS emissions', 'kg CFC-11 eq', 'numeric', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'ODS Emissions'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- BIODIVERSITY: Add IUCN species fields
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('IUCN Red List species (CR)', 'สายพันธุ์ CR', 'Critically Endangered species in operational areas', 'species', 'numeric', 5),
    ('IUCN Red List species (EN)', 'สายพันธุ์ EN', 'Endangered species', 'species', 'numeric', 6),
    ('IUCN Red List species (VU)', 'สายพันธุ์ VU', 'Vulnerable species', 'species', 'numeric', 7),
    ('Biodiversity Action Plan', 'แผนปฏิบัติการ', 'Whether a BAP is in place', NULL, 'text', 8),
    ('Deforestation-free commitment', 'พันธสัญญาไม่ตัดไม้ทำลายป่า', 'Whether committed to zero deforestation', NULL, 'text', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Species & Habitat Protection'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- NEW S CATEGORY: Product Responsibility (GRI 416, 417)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order)
SELECT 'S', 'Product Responsibility', 'ความรับผิดชอบต่อผลิตภัณฑ์',
       'Customer health & safety, marketing & labeling (GRI 416, 417)', 8
WHERE NOT EXISTS (SELECT 1 FROM esg_data_category WHERE name = 'Product Responsibility');

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Customer Health & Safety', 'สุขภาพและความปลอดภัยลูกค้า', 'Product H&S assessment and compliance (GRI 416)', 1),
    ('Marketing & Labeling', 'การตลาดและการติดฉลาก', 'Product information and marketing compliance (GRI 417)', 2)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Product Responsibility'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name);

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Products assessed for H&S', 'ผลิตภัณฑ์ที่ประเมินด้าน H&S', 'Percentage of significant product categories assessed', '%', 'numeric', 1),
    ('H&S non-compliance incidents', 'เหตุการณ์ไม่ปฏิบัติตาม H&S', 'Incidents of non-compliance', 'cases', 'numeric', 2),
    ('Product recalls', 'การเรียกคืนสินค้า', 'Number of product recalls', 'cases', 'numeric', 3),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Customer Health & Safety'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Labeling non-compliance', 'การไม่ปฏิบัติตามการติดฉลาก', 'Incidents of labeling regulation non-compliance', 'cases', 'numeric', 1),
    ('Marketing non-compliance', 'การไม่ปฏิบัติตามการตลาด', 'Incidents of marketing communications non-compliance', 'cases', 'numeric', 2),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 3)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Marketing & Labeling'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- NEW S CATEGORY: Customer Privacy (GRI 418)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order)
SELECT 'S', 'Customer Privacy', 'ความเป็นส่วนตัวของลูกค้า',
       'Customer privacy complaints and data breaches (GRI 418)', 9
WHERE NOT EXISTS (SELECT 1 FROM esg_data_category WHERE name = 'Customer Privacy');

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Customer Privacy Incidents', 'เหตุการณ์ด้านความเป็นส่วนตัว', 'Privacy complaints and data breaches (GRI 418-1)', 1
FROM esg_data_category WHERE name = 'Customer Privacy'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Customer Privacy') AND es.name = 'Customer Privacy Incidents');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Privacy complaints (external)', 'ข้อร้องเรียนความเป็นส่วนตัว (ภายนอก)', 'Substantiated complaints from outside parties', 'cases', 'numeric', 1),
    ('Privacy complaints (regulatory)', 'ข้อร้องเรียนจากหน่วยงานกำกับ', 'Complaints from regulatory bodies', 'cases', 'numeric', 2),
    ('Data leaks/thefts/losses', 'การรั่วไหล/ขโมย/สูญหายของข้อมูล', 'Total identified data breach incidents', 'incidents', 'numeric', 3),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Customer Privacy Incidents'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- OHS: Add Work-Related Ill Health subcategory (GRI 403-10)
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Work-Related Ill Health', 'โรคจากการทำงาน', 'Work-related illness fatalities and cases (GRI 403-10)', 3
FROM esg_data_category WHERE name = 'Health & Safety'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Health & Safety') AND es.name = 'Work-Related Ill Health');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Fatalities from ill health', 'ผู้เสียชีวิตจากโรคจากงาน', 'Deaths from work-related ill health', 'persons', 'numeric', 1),
    ('Recordable ill health cases', 'กรณีโรคจากงานที่บันทึกได้', 'Total recordable cases', 'cases', 'numeric', 2),
    ('Main types of ill health', 'ประเภทโรคจากงานหลัก', 'Description of main types', NULL, 'text', 3),
    ('Hazards causing ill health', 'อันตรายที่ทำให้เกิดโรค', 'Work-related hazards identified', NULL, 'text', 4),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Work-Related Ill Health'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- OHS: Expand Occupational Incidents with GRI 403-9 fields
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('LTIFR', 'อัตราการบาดเจ็บจากการหยุดงาน', 'Lost-time injuries per 1M hours worked', 'rate', 'numeric', 7),
    ('TRIFR', 'อัตราการบาดเจ็บที่บันทึกได้', 'Total recordable injuries per 1M hours', 'rate', 'numeric', 8),
    ('Hours worked (total)', 'ชั่วโมงทำงานรวม', 'Total hours worked (rate denominator)', 'hours', 'numeric', 9),
    ('Main injury types', 'ประเภทการบาดเจ็บหลัก', 'Most common injury types', NULL, 'text', 10),
    ('Rate calculation basis', 'ฐานคำนวณอัตรา', '200,000 or 1,000,000 hours', NULL, 'text', 11)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Occupational Incidents'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- DIVERSITY: Add gender pay gap fields (GRI 405-2)
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Female in board %', 'ผู้หญิงในคณะกรรมการ %', 'Percentage of women on board', '%', 'numeric', 7),
    ('Gender pay gap (basic salary)', 'ช่องว่างค่าจ้างเพศ (เงินเดือน)', 'Female:Male ratio by category', NULL, 'numeric', 8),
    ('Gender pay gap (total remuneration)', 'ช่องว่างค่าจ้างเพศ (ค่าตอบแทนรวม)', 'Female:Male ratio by category', NULL, 'numeric', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Workforce Diversity'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- NEW G CATEGORY: Economic Performance (GRI 201-204)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order)
SELECT 'G', 'Economic Performance', 'ผลการดำเนินงานทางเศรษฐกิจ',
       'Direct economic value generated and distributed (GRI 201-204)', 7
WHERE NOT EXISTS (SELECT 1 FROM esg_data_category WHERE name = 'Economic Performance');

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Direct Economic Value', 'มูลค่าเศรษฐกิจโดยตรง', 'Economic value generated and distributed (GRI 201-1)', 1
FROM esg_data_category WHERE name = 'Economic Performance'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Economic Performance') AND es.name = 'Direct Economic Value');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Revenue', 'รายได้', 'Total revenue generated', NULL, 'numeric', 1),
    ('Operating costs', 'ค่าใช้จ่ายดำเนินงาน', 'Total operating costs', NULL, 'numeric', 2),
    ('Employee wages & benefits', 'ค่าจ้างและสวัสดิการ', 'Total employee compensation', NULL, 'numeric', 3),
    ('Payments to providers of capital', 'การจ่ายให้ผู้ให้เงินทุน', 'Dividends, interest payments', NULL, 'numeric', 4),
    ('Payments to government', 'การจ่ายให้รัฐ', 'Taxes paid', NULL, 'numeric', 5),
    ('Community investments', 'การลงทุนชุมชน', 'Total community investment', NULL, 'numeric', 6),
    ('Local procurement %', 'สัดส่วนจัดซื้อท้องถิ่น', 'Percentage of local procurement', '%', 'numeric', 7),
    ('Government financial assistance', 'ความช่วยเหลือจากรัฐ', 'Grants, tax credits, subsidies received', NULL, 'numeric', 8),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Direct Economic Value'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- NEW G CATEGORY: Tax Transparency (GRI 207)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order)
SELECT 'G', 'Tax Transparency', 'ความโปร่งใสด้านภาษี',
       'Tax strategy, governance, and country-by-country reporting (GRI 207)', 8
WHERE NOT EXISTS (SELECT 1 FROM esg_data_category WHERE name = 'Tax Transparency');

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Country-by-Country Tax', 'ภาษีรายประเทศ', 'Country-by-country tax reporting (GRI 207-4)', 1
FROM esg_data_category WHERE name = 'Tax Transparency'
  AND NOT EXISTS (SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = (SELECT id FROM esg_data_category WHERE name = 'Tax Transparency') AND es.name = 'Country-by-Country Tax');

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Jurisdiction', 'เขตอำนาจศาล', 'Country/tax jurisdiction', NULL, 'text', 1),
    ('Revenue (third-party)', 'รายได้ (บุคคลที่สาม)', 'Revenue from third-party sales', NULL, 'numeric', 2),
    ('Revenue (intra-group)', 'รายได้ (ภายในกลุ่ม)', 'Intra-group transactions', NULL, 'numeric', 3),
    ('Profit/loss before tax', 'กำไร/ขาดทุนก่อนภาษี', 'Pre-tax profit or loss', NULL, 'numeric', 4),
    ('Income tax paid (cash)', 'ภาษีเงินได้ที่จ่าย', 'Corporate income tax paid', NULL, 'numeric', 5),
    ('Income tax accrued', 'ภาษีเงินได้ค้างจ่าย', 'Tax accrued on current year', NULL, 'numeric', 6),
    ('Number of employees', 'จำนวนพนักงาน', 'FTE in jurisdiction', 'persons', 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Country-by-Country Tax'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- BOARD: Add TCFD/CDP governance fields
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Chair independence', 'ความเป็นอิสระของประธาน', 'Whether chair is independent/non-executive', NULL, 'text', 7),
    ('Board tenure (average)', 'ระยะเวลาดำรงตำแหน่งเฉลี่ย', 'Average years of board service', 'years', 'numeric', 8),
    ('ESG committee exists', 'คณะกรรมการ ESG มีหรือไม่', 'Whether a dedicated ESG/sustainability committee exists', NULL, 'text', 9),
    ('CEO-to-median pay ratio', 'อัตราส่วนเงินเดือน CEO', 'CEO total compensation vs median employee', NULL, 'numeric', 10),
    ('Executive ESG-linked compensation %', 'ค่าตอบแทนเชื่อมโยง ESG %', 'Percentage of executive pay linked to ESG targets', '%', 'numeric', 11)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Board Composition'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);

-- ==========================================
-- RISK: Add TCFD/CDP climate risk fields
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Climate risk type', 'ประเภทความเสี่ยงสภาพภูมิอากาศ', 'Physical (acute/chronic) or Transition (policy, technology, market)', NULL, 'text', 5),
    ('Time horizon', 'ขอบเขตเวลา', 'Short (<3yr), Medium (3-10yr), Long (>10yr)', NULL, 'text', 6),
    ('Financial impact (estimated)', 'ผลกระทบทางการเงิน', 'Estimated financial impact', NULL, 'numeric', 7),
    ('Likelihood', 'โอกาสเกิด', 'Likelihood of occurrence', NULL, 'text', 8),
    ('Scenario analysis conducted', 'การวิเคราะห์สถานการณ์', 'Whether 1.5C/2C/4C scenario analysis was conducted', NULL, 'text', 9),
    ('Internal carbon price', 'ราคาคาร์บอนภายใน', 'Shadow carbon price for investment decisions', 'USD/tCO2e', 'numeric', 10)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Risk Assessment & Mitigation'
  AND NOT EXISTS (SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name);
