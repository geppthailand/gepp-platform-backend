-- Migration: 20250922_110000_021_migrate_materials_data_from_csv.sql
-- Description: Migrate materials data from CSV to new three-tier structure
-- Source: data/New Mainmat_Submat.csv
-- Date: 2025-09-22
-- Author: Claude Code Assistant

-- ======================================
-- CSV DATA ANALYSIS
-- ======================================
-- CSV Structure:
-- ID,name_th,Category,Main material,unit_name_th,unit_name_en,unit_weight,color,calc_ghg,name_en
--
-- Mapping:
-- Category → material_categories (name_th)
-- Main material → main_materials (name_th)
-- Individual records → materials

-- ======================================
-- POPULATE MATERIAL CATEGORIES
-- ======================================

-- Extract unique categories from CSV data
INSERT INTO material_categories (name_th, name_en, code, is_active, created_date, updated_date)
VALUES
    ('ขยะรีไซเคิล', 'Recyclable Waste', 'RECYCLABLE', true, NOW(), NOW()),
    ('ขยะอิเล็กทรอนิกส์', 'Electronic Waste', 'ELECTRONIC', true, NOW(), NOW()),
    ('ขยะอินทรีย์', 'Organic Waste', 'ORGANIC', true, NOW(), NOW()),
    ('ขยะทั่วไป', 'General Waste', 'GENERAL', true, NOW(), NOW())
ON CONFLICT DO NOTHING;

-- ======================================
-- POPULATE MAIN MATERIALS
-- ======================================

-- Extract unique main materials from CSV data
INSERT INTO main_materials (name_th, name_en, code, is_active, created_date, updated_date)
VALUES
    ('พลาสติก', 'Plastic', 'PLASTIC', true, NOW(), NOW()),
    ('แก้ว', 'Glass', 'GLASS', true, NOW(), NOW()),
    ('อื่นๆ', 'Others', 'OTHERS', true, NOW(), NOW()),
    ('กระดาษ', 'Paper', 'PAPER', true, NOW(), NOW()),
    ('โลหะ', 'Metal', 'METAL', true, NOW(), NOW()),
    ('อุปกรณ์คอมพิวเตอร์', 'Computer Equipment', 'COMPUTER', true, NOW(), NOW()),
    ('โทรคมนาคม', 'Telecommunication', 'TELECOM', true, NOW(), NOW()),
    ('เครื่องใช้ไฟฟ้า', 'Electrical Appliances', 'ELECTRICAL', true, NOW(), NOW()),
    ('สายไฟ', 'Electrical Wire', 'WIRE', true, NOW(), NOW()),
    ('เศษอาหารและพืช', 'Food and Plant Waste', 'FOOD_PLANT', true, NOW(), NOW()),
    ('ขยะทั่วไป', 'General Waste', 'GENERAL_WASTE', true, NOW(), NOW())
ON CONFLICT DO NOTHING;

-- ======================================
-- POPULATE MATERIALS FROM CSV DATA
-- ======================================

-- Insert all materials data based on CSV content
-- Using CTEs to map categories and main materials

WITH category_mapping AS (
    SELECT
        id,
        CASE
            WHEN name_th = 'ขยะรีไซเคิล' THEN 'ขยะรีไซเคิล'
            WHEN name_th = 'ขยะอิเล็กทรอนิกส์' THEN 'ขยะอิเล็กทรอนิกส์'
            WHEN name_th = 'ขยะอินทรีย์' THEN 'ขยะอินทรีย์'
            WHEN name_th = 'ขยะทั่วไป' THEN 'ขยะทั่วไป'
        END as category_name_th
    FROM material_categories
),
main_material_mapping AS (
    SELECT
        id,
        name_th as main_material_name_th
    FROM main_materials
)

INSERT INTO materials (
    category_id, main_material_id, name_th, name_en,
    unit_name_th, unit_name_en, unit_weight, color, calc_ghg,
    tags, is_active, created_date, updated_date
)
SELECT
    cat.id as category_id,
    mm.id as main_material_id,
    mat_data.name_th,
    mat_data.name_en,
    mat_data.unit_name_th,
    mat_data.unit_name_en,
    mat_data.unit_weight,
    CASE
        WHEN mat_data.color IS NULL OR mat_data.color = '' OR mat_data.color = '0' THEN '#808080'
        WHEN LENGTH(mat_data.color) = 6 THEN '#' || mat_data.color
        WHEN LEFT(mat_data.color, 1) = '#' THEN mat_data.color
        ELSE '#' || mat_data.color
    END as color,
    mat_data.calc_ghg,
    COALESCE(mat_data.category_th || ', ' || mat_data.main_material_th, mat_data.category_th) as tags,
    true as is_active,
    NOW() as created_date,
    NOW() as updated_date
FROM (
    VALUES
        -- Row 1-10 (Plastic materials)
        ('ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกใส (PET)', 'Clear Plastic (PET)', 'กิโลกรัม', 'Kilogram', 1, '#336359', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'พลาสติก HDPE ขาวขุ่น', 'Opague Plastic (HDPE)', 'กิโลกรัม', 'Kilogram', 1, '#477269', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ถุงพลาสติก', 'Plastic Bag', 'กิโลกรัม', 'Kilogram', 1, '#8df79e', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีเขียว', 'PVC Pipes Green', 'กิโลกรัม', 'Kilogram', 1, '#2e8b57', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'โฟม', 'Foam', 'กิโลกรัม', 'Kilogram', 1, '#b6e077', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกรวม', 'Other plastic', 'กิโลกรัม', 'Kilogram', 1, '#93ad6e', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกกรอบ (PS)', 'Breakable Plastic (PS)', 'กิโลกรัม', 'Kilogram', 1, '#bfd575', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'วีดีโอ', 'VDO', 'กิโลกรัม', 'Kilogram', 1, '#4c552e', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ซีดี', 'CD DVD', 'กิโลกรัม', 'Kilogram', 1, '#626262', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'สายยาง', 'Hose', 'กิโลกรัม', 'Kilogram', 1, '#a5cca5', 1.031),
        -- Row 11-20
        ('ขยะรีไซเคิล', 'พลาสติก', 'รองเท้าบู้ท', 'Boots', 'กิโลกรัม', 'Kilogram', 1, '#4e7f52', 1.031),
        ('ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'ปลอกสายไฟ', 'Electric wire coating', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 1.031),
        ('ขยะรีไซเคิล', 'แก้ว', 'ลีโอ ขวด', 'LEO (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#8b4513', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'ช้าง ขวด', 'Chang (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#6a996d', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'สิงห์ ขวด', 'Singha (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#5b827a', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'ไฮเนเก้น ขวด', 'Heineken (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#94bd9c', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'อาซาฮี ขวด', 'Asahi (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#a3c7aa', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'เหล้าขาว ขวด', 'Rice Whiskey (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#b3d0b8', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วใส', 'White Clear (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#66CC99', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีชา', 'Red Glass (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#8df79e', 0.276),
        -- Row 21-30
        ('ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีเขียว', 'Green Glass (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#9edea8', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีรวมอื่น ๆ', 'Colored Glass (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#2E8B57', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'ลีโอ ลัง 12 ขวด', 'LEO (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#5c9166', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'ลีโอ ขวดเล็ก ลัง 24 ขวด', 'LEO 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#52815b', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'ช้าง ลัง 12 ขวด', 'Chang (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#48714f', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'ช้าง ขวดเล็ก ลัง 24 ขวด', 'Chang 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#3d6144', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'สิงห์ ลัง 12 ขวด', 'Singha (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#335139', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'สิงห์ ขวดเล็ก ลัง 24 ขวด', 'Singha 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#29402d', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'ไฮเนเก้น ลัง 12 ขวด', 'Heineken (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#1e3022', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'ไฮเนเก้น ขวดเล็ก ลัง 24 ขวด', 'Heineken 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#a7ccad', 0.276),
        -- Row 31-40
        ('ขยะรีไซเคิล', 'อื่นๆ', 'Asahi ลัง', 'Asahi (Carton)', 'ลัง', 'Carton', 4.2, '#0a100b', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'เหล้าขาว ลัง', 'Thai Rice Whiskey (Carton)', 'ลัง', 'Carton', 4.2, '#808080', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'เหล้าขาวเล็ก ลัง', 'Thai Rice Whiskey (small box)', 'ลัง', 'Carton', 4.2, '#808080', 0.276),
        ('ขยะรีไซเคิล', 'อื่นๆ', 'คิริน (ลัง)', 'Kirin (Carton)', 'ลัง', 'Carton', 4.2, '#808080', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วใส', 'White Cullet', 'กิโลกรัม', 'Kilogram', 1, '#1e7042', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วสีชา', 'Red Cullet', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วสีเขียว', 'Green Cullet', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.276),
        ('ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วสีรวมอื่น ๆ', 'Colored Cullet', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.276),
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษลังสีน้ำตาล', 'Brown Paper Box / Carton / Cardboard', 'กิโลกรัม', 'Kilogram', 1, '#b6e077', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษสีทั่วไป', 'Colored paper', 'กิโลกรัม', 'Kilogram', 1, '#86a35c', 5.674),
        -- Row 41-50
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษสีขาวดำ', 'Black and White paper', 'กิโลกรัม', 'Kilogram', 1, '#93ad6e', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'หนังสือพิมพ์', 'Newspaper', 'กิโลกรัม', 'Kilogram', 1, '#a1b780', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'นิตยสาร / หนังสือเล่มรวม', 'Magazines / Books', 'กิโลกรัม', 'Kilogram', 1, '#aec192', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษอื่น ๆ', 'Other paper', 'กิโลกรัม', 'Kilogram', 1, '#bccca4', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'เศษกระดาษฉีก ย่อยเส้น ไม่ฝอย', 'Shredded Paper', 'กิโลกรัม', 'Kilogram', 1, '#c9d6b6', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษรวม (จับจั๊ว)', 'Mixed Paper', 'กิโลกรัม', 'Kilogram', 1, '#92ba56', 5.674),
        ('ขยะรีไซเคิล', 'โลหะ', 'เหล็กเส้น', 'Steel bar', 'กิโลกรัม', 'Kilogram', 1, '#bfd575', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'เหล็กแผ่น', 'Steel plate', 'กิโลกรัม', 'Kilogram', 1, '#c5d982', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ท่อเหล็ก', 'Steel pipe', 'กิโลกรัม', 'Kilogram', 1, '#cbdd90', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ผลิตภัณฑ์เหล็กอื่น ๆ', 'Other steel', 'กิโลกรัม', 'Kilogram', 1, '#d2e19e', 1.832),
        -- Row 51-60
        ('ขยะรีไซเคิล', 'โลหะ', 'เหล็กหนา', 'Thick Steel', 'กิโลกรัม', 'Kilogram', 1, '#d8e5ac', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'เหล็กบาง', 'Thin Steel', 'กิโลกรัม', 'Kilogram', 1, '#CCCC99', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองแดงปอกสวย (1)', 'Copper 1 (pre treated)', 'กิโลกรัม', 'Kilogram', 1, '#a8a856', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองเหลืองบาง', 'Brass Thin', 'กิโลกรัม', 'Kilogram', 1, '#7d7d43', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'สแตนเลส', 'Stainless Steel', 'กิโลกรัม', 'Kilogram', 1, '#9e9e75', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ตะกั่ว', 'Lead', 'กิโลกรัม', 'Kilogram', 1, '#c6db7b', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'สังกะสี', 'Zinc', 'กิโลกรัม', 'Kilogram', 1, '#abbf69', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองแดงปอกดำ ช๊อต (2)', 'Copper Short Circuit 2 (thick)', 'กิโลกรัม', 'Kilogram', 1, '#98aa5d', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองแดงเส้นใหญ่ เผา (3)', 'Copper Burn 3 (thick)', 'กิโลกรัม', 'Kilogram', 1, '#859551', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองแดงเส้นเล็ก เผา (4)', 'Copper Burn 4 (thin small)', 'กิโลกรัม', 'Kilogram', 1, '#727f46', 1.832),
        -- Row 61-70
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองแดงเส้นเล็ก (เครือบขาว)', 'Copper (mixed aluminum)', 'กิโลกรัม', 'Kilogram', 1, '#5f6a3a', 1.832),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองแดง', 'Copper', 'กิโลกรัม', 'Kilogram', 1, '#4c552e', 1.832),
        ('ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'บัลลาสไฟ', 'Ballast', 'ตามราคาประเมินหน้างาน', 'Estimate price on site', 1, '#393f23', 1.832),
        ('ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'อุปกรณ์คอมพิวเตอร์', 'Computer accessories', 'เครื่อง', 'Price per unit', 1, '#626262', 0),
        ('ขยะอิเล็กทรอนิกส์', 'โทรคมนาคม', 'โทรศัพท์มือถือ', 'Mobile Phone', 'เครื่อง', 'Price per unit', 1, '#717171', 0),
        ('ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'ทีวี', 'TV', 'เครื่อง', 'Price per unit', 1, '#818181', 0),
        ('ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'เครื่องถ่ายเอกสาร แฟ๊กซ์ ปริ๊นเตอร์', 'Fax Printer Xerox', 'เครื่อง', 'Price per unit', 1, '#919191', 0),
        ('ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'เครื่องเล่นเสียง วิทยุ สเตอริโอ', 'Radio Stereo', 'เครื่อง', 'Price per unit', 1, '#a0a0a0', 0),
        ('ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'พัดลมตั้งโต๊ะ พัดลมเพดาน', 'Fan', 'เครื่อง', 'Price per unit', 1, '#b0b0b0', 0),
        ('ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'เครื่องครัวทำอาหาร หม้อหุงข้าว เตาอบ', 'Rice Cooker Oven', 'เครื่อง', 'Price per unit', 1, '#c0c0c0', 0),
        -- Row 71-80
        ('ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'อุปกรณ์ทำความสะอาด เครื่องดูดฝุ่น', 'Vacuum Cleaner', 'เครื่อง', 'Price per unit', 1, '#cfcfcf', 0),
        ('ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'เครื่องซักผ้า เครื่องอบผ้า', 'Washing Machine Dryer', 'เครื่อง', 'Price per unit', 1, '#dfdfdf', 0),
        ('ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'อิเล็กทรอนิกส์อื่น ๆ', 'Other electronic appliances', 'เครื่อง', 'Price per unit', 1, '#BEBEBE', 0),
        ('ขยะรีไซเคิล', 'โลหะ', 'อลูมิเนียม หนา', 'Aluminum Thick', 'กิโลกรัม', 'Kilogram', 1, '#a5cca5', 9.127),
        ('ขยะรีไซเคิล', 'โลหะ', 'กระป๋องอลูมิเนียม (ขายตามน้ำหนักกิโลกรัม)', 'Aluminum Can (Kg)', 'กิโลกรัม', 'Kilogram', 1, '#88B288', 9.127),
        ('ขยะรีไซเคิล', 'โลหะ', 'กระป๋องอลูมิเนียม (ขายนับกระป๋อง)', 'Aluminum Can (by can)', 'ตามราคาประเมินต่อกระป๋อง', 'Price per can', 0.015, '#9fc19f', 9.127),
        ('ขยะอินทรีย์', 'เศษอาหารและพืช', 'เศษอาหาร', 'Foodwaste', 'กิโลกรัม', 'Kilogram', 1, '#4e7f52', 0.465),
        ('ขยะอินทรีย์', 'เศษอาหารและพืช', 'ใบไม้ ต้นไม้', 'Leaves Trees', 'กิโลกรัม', 'Kilogram', 1, '#628d65', 0.854),
        ('ขยะอินทรีย์', 'เศษอาหารและพืช', 'ขยะย่อยสลายได้อื่น ๆ', 'Other organic waste', 'กิโลกรัม', 'Kilogram', 1, '#759b78', 0.465),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีขาว', 'PVC Pipes White', 'กิโลกรัม', 'Kilogram', 1, '#23453e', 1.031),
        -- Row 81-90
        ('ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกนิ่ม', 'Soft Plastic Cup', 'กิโลกรัม', 'Kilogram', 1, '#1e3b35', 1.031),
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษย่อยเส้น ขาวดำ', 'Shredded Paper (White and Black)', 'กิโลกรัม', 'Kilogram', 1, '#669933', 5.674),
        ('ขยะรีไซเคิล', 'กระดาษ', 'กระดาษย่อยเส้น สี รวมสี', 'Shredded Paper (Mixed Color)', 'กิโลกรัม', 'Kilogram', 1, '#99CC33', 5.674),
        ('ขยะรีไซเคิล', 'โลหะ', 'อลูนิเนียม บาง', 'Aluminum Thin', 'กิโลกรัม', 'Kilogram', 1, '#bccfbc', 9.127),
        ('ขยะรีไซเคิล', 'โลหะ', 'ทองเหลืองหนา', 'Brass thick', 'กิโลกรัม', 'Kilogram', 1, '#5f7025', 1.832),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ฟิวเจอร์บอร์ด', 'Coroplast Sign Board', 'กิโลกรัม', 'Kilogram', 1, '#19312c', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ถุงปุ๋ย', 'Fertilizer Plastic Sack', 'กิโลกรัม', 'Kilogram', 1, '#142723', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'แฟ้มพลาสติก', 'Plastic Folder / Binder', 'กิโลกรัม', 'Kilogram', 1, '#0f1d1a', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีเทา เหลือง', 'PVC Pipes Grey Yellow', 'กิโลกรัม', 'Kilogram', 1, '#02382c', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีฟ้า', 'PVC Pipes Cyan', 'กิโลกรัม', 'Kilogram', 1, '#6c8278', 1.031),
        -- Row 91-99
        ('ขยะรีไซเคิล', 'พลาสติก', 'แผงไข่', 'Egg Packaging', 'กิโลกรัม', 'Kilogram', 1, '#6c8942', 5.674),
        ('ขยะรีไซเคิล', 'พลาสติก', 'หลอดพลาสติก', 'Plastic Straw', 'กิโลกรัม', 'Kilogram', 1, '#486b64', 1.031),
        ('ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายไฟบ้าน', 'Electrical Wire', 'กิโลกรัม', 'Kilogram', 1, '#13150b', 1.832),
        ('ขยะทั่วไป', 'ขยะทั่วไป', 'ขยะทั่วไป', 'General Waste', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0),
        ('ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายไฟในอาคาร', 'Building Electrical Wire', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.832),
        ('ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายยูเอสบี', 'USB Cord', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.832),
        ('ขยะรีไซเคิล', 'พลาสติก', 'กระสอบข้าว', 'Rice Plastic Sack', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        ('ขยะรีไซเคิล', 'พลาสติก', 'กระสอบน้ำตาล', 'Sugar Plastic Sack', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031)
) AS mat_data(category_th, main_material_th, name_th, name_en, unit_name_th, unit_name_en, unit_weight, color, calc_ghg)
LEFT JOIN category_mapping cat ON cat.category_name_th = mat_data.category_th
LEFT JOIN main_material_mapping mm ON mm.main_material_name_th = mat_data.main_material_th;

-- ======================================
-- DATA VERIFICATION
-- ======================================

-- Verify the migration results
DO $$
DECLARE
    category_count INTEGER;
    main_material_count INTEGER;
    material_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO category_count FROM material_categories WHERE is_active = true;
    SELECT COUNT(*) INTO main_material_count FROM main_materials WHERE is_active = true;
    SELECT COUNT(*) INTO material_count FROM materials WHERE is_active = true;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'DATA MIGRATION COMPLETED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Material Categories: % records', category_count;
    RAISE NOTICE 'Main Materials: % records', main_material_count;
    RAISE NOTICE 'Materials: % records', material_count;
    RAISE NOTICE '============================================';

    -- Verify all materials have proper relationships
    PERFORM 1 FROM materials WHERE category_id IS NULL OR main_material_id IS NULL;
    IF FOUND THEN
        RAISE WARNING 'Some materials have missing category or main material relationships!';
    ELSE
        RAISE NOTICE 'All materials have proper relationships ✓';
    END IF;
END $$;

-- ======================================
-- CREATE SAMPLE QUERIES
-- ======================================

-- Sample query to verify the data structure
/*
-- Get materials by category
SELECT
    cat.name_th as category,
    mm.name_th as main_material,
    m.name_th as material_name,
    m.unit_name_th,
    m.calc_ghg,
    m.color
FROM materials m
JOIN material_categories cat ON m.category_id = cat.id
JOIN main_materials mm ON m.main_material_id = mm.id
WHERE cat.name_th = 'ขยะรีไซเคิล'
ORDER BY mm.name_th, m.name_th;
*/

-- Migration completed - no logging table available in this system