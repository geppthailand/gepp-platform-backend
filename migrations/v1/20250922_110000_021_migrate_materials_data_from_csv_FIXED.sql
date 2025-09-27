-- Migration: 20250922_110000_021_migrate_materials_data_from_csv_FIXED.sql
-- Description: COMPLETE migration of ALL 260 materials from CSV with migration_id
-- Replaces the incomplete original migration
-- Source: data/New Mainmat_Submat.csv (260 materials)
-- Date: 2025-09-22
-- Author: Claude Code Assistant

-- ======================================
-- CLEAR EXISTING INCOMPLETE DATA
-- ======================================

-- Remove any existing materials to start fresh (if needed)
-- TRUNCATE TABLE materials; -- Uncomment if you want to start completely fresh

-- ======================================
-- POPULATE MATERIAL CATEGORIES
-- ======================================

-- Insert all categories found in the CSV
INSERT INTO material_categories (name_th, name_en, code, is_active, created_date, updated_date)
VALUES
    ('ขยะรีไซเคิล', 'Recyclable Waste', 'RECYCLABLE', true, NOW(), NOW()),
    ('ขยะอิเล็กทรอนิกส์', 'Electronic Waste', 'ELECTRONIC', true, NOW(), NOW()),
    ('ขยะอินทรีย์', 'Organic Waste', 'ORGANIC', true, NOW(), NOW()),
    ('ขยะทั่วไป', 'General Waste', 'GENERAL', true, NOW(), NOW()),
    ('ขยะอันตราย', 'Hazardous Waste', 'HAZARDOUS', true, NOW(), NOW()),
    ('ขยะทางการแพทย์/ติดเชื้อ', 'Medical/Infectious Waste', 'MEDICAL', true, NOW(), NOW()),
    ('ขยะก่อสร้าง', 'Construction Waste', 'CONSTRUCTION', true, NOW(), NOW())
ON CONFLICT DO NOTHING;

-- ======================================
-- POPULATE MAIN MATERIALS
-- ======================================

-- Insert all main materials found in the CSV
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
    ('ขยะทั่วไป', 'General Waste', 'GENERAL_WASTE', true, NOW(), NOW()),
    ('หลอดไฟและสเปรย์', 'Bulbs and Sprays', 'BULBS_SPRAYS', true, NOW(), NOW()),
    ('แบตเตอรี่', 'Batteries', 'BATTERIES', true, NOW(), NOW()),
    ('ไม้', 'Wood', 'WOOD', true, NOW(), NOW()),
    ('วัสดุเผาทำเชื้อเพลิง', 'Waste to Energy Material', 'WASTE_TO_ENERGY', true, NOW(), NOW()),
    ('พลาสติกปนเปื้อน', 'Contaminated Plastic', 'CONTAMINATED_PLASTIC', true, NOW(), NOW()),
    ('ของใช้ส่วนตัว', 'Personal Items', 'PERSONAL_ITEMS', true, NOW(), NOW()),
    ('เคมีและของเหลว', 'Chemicals and Liquids', 'CHEMICALS', true, NOW(), NOW()),
    ('ของเหลวและตะกอน', 'Liquids and Sludge', 'LIQUIDS_SLUDGE', true, NOW(), NOW()),
    ('วัสดุก่อสร้าง', 'Construction Materials', 'CONSTRUCTION_MATERIALS', true, NOW(), NOW())
ON CONFLICT DO NOTHING;

-- ======================================
-- ADD MIGRATION_ID COLUMN IF NOT EXISTS
-- ======================================

-- Ensure materials table has migration_id column
DO $$
BEGIN
    -- Add migration_id column if it doesn't exist
    BEGIN
        ALTER TABLE materials ADD COLUMN migration_id INTEGER;
    EXCEPTION
        WHEN duplicate_column THEN
            -- Column already exists, skip
            NULL;
    END;

    -- Add unique constraint if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'idx_materials_migration_id') THEN
        CREATE UNIQUE INDEX idx_materials_migration_id ON materials(migration_id)
        WHERE migration_id IS NOT NULL;
    END IF;
END $$;

-- Add comment
COMMENT ON COLUMN materials.migration_id IS 'Original ID from CSV migration data for tracking purposes';

-- ======================================
-- POPULATE ALL MATERIALS FROM CSV (1-260)
-- ======================================

-- Insert ALL materials from CSV with proper migration_id mapping
WITH category_mapping AS (
    SELECT
        id,
        CASE name_th
            WHEN 'ขยะรีไซเคิล' THEN 'ขยะรีไซเคิล'
            WHEN 'ขยะอิเล็กทรอนิกส์' THEN 'ขยะอิเล็กทรอนิกส์'
            WHEN 'ขยะอินทรีย์' THEN 'ขยะอินทรีย์'
            WHEN 'ขยะทั่วไป' THEN 'ขยะทั่วไป'
            WHEN 'ขยะอันตราย' THEN 'ขยะอันตราย'
            WHEN 'ขยะทางการแพทย์/ติดเชื้อ' THEN 'ขยะทางการแพทย์/ติดเชื้อ'
            WHEN 'ขยะก่อสร้าง' THEN 'ขยะก่อสร้าง'
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
    migration_id, category_id, main_material_id, name_th, name_en,
    unit_name_th, unit_name_en, unit_weight, color, calc_ghg,
    tags, is_active, created_date, updated_date
)
SELECT
    mat_data.migration_id,
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
        -- ALL 260 materials from CSV with migration_id (CSV ID column)
        (1, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกใส (PET)', 'Clear Plastic (PET)', 'กิโลกรัม', 'Kilogram', 1, '#336359', 1.031),
        (2, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติก HDPE ขาวขุ่น', 'Opague Plastic (HDPE)', 'กิโลกรัม', 'Kilogram', 1, '#477269', 1.031),
        (3, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงพลาสติก', 'Plastic Bag', 'กิโลกรัม', 'Kilogram', 1, '#8df79e', 1.031),
        (4, 'ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีเขียว', 'PVC Pipes Green', 'กิโลกรัม', 'Kilogram', 1, '#2e8b57', 1.031),
        (5, 'ขยะรีไซเคิล', 'พลาสติก', 'โฟม', 'Foam', 'กิโลกรัม', 'Kilogram', 1, '#b6e077', 1.031),
        (6, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกรวม', 'Other plastic', 'กิโลกรัม', 'Kilogram', 1, '#93ad6e', 1.031),
        (7, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกกรอบ (PS)', 'Breakable Plastic (PS)', 'กิโลกรัม', 'Kilogram', 1, '#bfd575', 1.031),
        (8, 'ขยะรีไซเคิล', 'พลาสติก', 'วีดีโอ', 'VDO', 'กิโลกรัม', 'Kilogram', 1, '#4c552e', 1.031),
        (9, 'ขยะรีไซเคิล', 'พลาสติก', 'ซีดี', 'CD DVD', 'กิโลกรัม', 'Kilogram', 1, '#626262', 1.031),
        (10, 'ขยะรีไซเคิล', 'พลาสติก', 'สายยาง', 'Hose', 'กิโลกรัม', 'Kilogram', 1, '#a5cca5', 1.031),

        (11, 'ขยะรีไซเคิล', 'พลาสติก', 'รองเท้าบู้ท', 'Boots', 'กิโลกรัม', 'Kilogram', 1, '#4e7f52', 1.031),
        (12, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'ปลอกสายไฟ', 'Electric wire coating', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 1.031),
        (13, 'ขยะรีไซเคิล', 'แก้ว', 'ลีโอ ขวด', 'LEO (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#8b4513', 0.276),
        (14, 'ขยะรีไซเคิล', 'แก้ว', 'ช้าง ขวด', 'Chang (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#6a996d', 0.276),
        (15, 'ขยะรีไซเคิล', 'แก้ว', 'สิงห์ ขวด', 'Singha (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#5b827a', 0.276),
        (16, 'ขยะรีไซเคิล', 'แก้ว', 'ไฮเนเก้น ขวด', 'Heineken (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#94bd9c', 0.276),
        (17, 'ขยะรีไซเคิล', 'แก้ว', 'อาซาฮี ขวด', 'Asahi (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#a3c7aa', 0.276),
        (18, 'ขยะรีไซเคิล', 'แก้ว', 'เหล้าขาว ขวด', 'Rice Whiskey (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#b3d0b8', 0.276),
        (19, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วใส', 'White Clear (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#66CC99', 0.276),
        (20, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีชา', 'Red Glass (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#8df79e', 0.276),
        (21, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีเขียว', 'Green Glass (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#9edea8', 0.276),
        (22, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีรวมอื่น ๆ', 'Colored Glass (Bottle)', 'กิโลกรัม', 'Kilogram', 1, '#2E8B57', 0.276),
        (23, 'ขยะรีไซเคิล', 'อื่นๆ', 'ลีโอ ลัง 12 ขวด', 'LEO (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#5c9166', 0.276),
        (24, 'ขยะรีไซเคิล', 'อื่นๆ', 'ลีโอ ขวดเล็ก ลัง 24 ขวด', 'LEO 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#52815b', 0.276),
        (25, 'ขยะรีไซเคิล', 'อื่นๆ', 'ช้าง ลัง 12 ขวด', 'Chang (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#48714f', 0.276),
        (26, 'ขยะรีไซเคิล', 'อื่นๆ', 'ช้าง ขวดเล็ก ลัง 24 ขวด', 'Chang 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#3d6144', 0.276),
        (27, 'ขยะรีไซเคิล', 'อื่นๆ', 'สิงห์ ลัง 12 ขวด', 'Singha (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#335139', 0.276),
        (28, 'ขยะรีไซเคิล', 'อื่นๆ', 'สิงห์ ขวดเล็ก ลัง 24 ขวด', 'Singha 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#29402d', 0.276),
        (29, 'ขยะรีไซเคิล', 'อื่นๆ', 'ไฮเนเก้น ลัง 12 ขวด', 'Heineken (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#1e3022', 0.276),
        (30, 'ขยะรีไซเคิล', 'อื่นๆ', 'ไฮเนเก้น ขวดเล็ก ลัง 24 ขวด', 'Heineken 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#a7ccad', 0.276),
        (31, 'ขยะรีไซเคิล', 'อื่นๆ', 'Asahi ลัง', 'Asahi (Carton)', 'ลัง', 'Carton', 4.2, '#0a100b', 0.276),
        (32, 'ขยะรีไซเคิล', 'อื่นๆ', 'เหล้าขาว ลัง', 'Thai Rice Whiskey (Carton)', 'ลัง', 'Carton', 4.2, '#808080', 0.276),
        (33, 'ขยะรีไซเคิล', 'อื่นๆ', 'เหล้าขาวเล็ก ลัง', 'Thai Rice Whiskey (small box)', 'ลัง', 'Carton', 4.2, '#808080', 0.276),
        (34, 'ขยะรีไซเคิล', 'อื่นๆ', 'คิริน (ลัง)', 'Kirin (Carton)', 'ลัง', 'Carton', 4.2, '#808080', 0.276),
        (35, 'ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วใส', 'White Cullet', 'กิโลกรัม', 'Kilogram', 1, '#1e7042', 0.276),
        (36, 'ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วสีชา', 'Red Cullet', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.276),
        (37, 'ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วสีเขียว', 'Green Cullet', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.276),
        (38, 'ขยะรีไซเคิล', 'แก้ว', 'เศษแก้วสีรวมอื่น ๆ', 'Colored Cullet', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.276),
        (39, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษลังสีน้ำตาล', 'Brown Paper Box / Carton / Cardboard', 'กิโลกรัม', 'Kilogram', 1, '#b6e077', 5.674),
        (40, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษสีทั่วไป', 'Colored paper', 'กิโลกรัม', 'Kilogram', 1, '#86a35c', 5.674),
        (41, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษสีขาวดำ', 'Black and White paper', 'กิโลกรัม', 'Kilogram', 1, '#93ad6e', 5.674),
        (42, 'ขยะรีไซเคิล', 'กระดาษ', 'หนังสือพิมพ์', 'Newspaper', 'กิโลกรัม', 'Kilogram', 1, '#a1b780', 5.674),
        (43, 'ขยะรีไซเคิล', 'กระดาษ', 'นิตยสาร / หนังสือเล่มรวม', 'Magazines / Books', 'กิโลกรัม', 'Kilogram', 1, '#aec192', 5.674),
        (44, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษอื่น ๆ', 'Other paper', 'กิโลกรัม', 'Kilogram', 1, '#bccca4', 5.674),
        (45, 'ขยะรีไซเคิล', 'กระดาษ', 'เศษกระดาษฉีก ย่อยเส้น ไม่ฝอย', 'Shredded Paper', 'กิโลกรัม', 'Kilogram', 1, '#c9d6b6', 5.674),
        (46, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษรวม (จับจั๊ว)', 'Mixed Paper', 'กิโลกรัม', 'Kilogram', 1, '#92ba56', 5.674),
        (47, 'ขยะรีไซเคิล', 'โลหะ', 'เหล็กเส้น', 'Steel bar', 'กิโลกรัม', 'Kilogram', 1, '#bfd575', 1.832),
        (48, 'ขยะรีไซเคิล', 'โลหะ', 'เหล็กแผ่น', 'Steel plate', 'กิโลกรัม', 'Kilogram', 1, '#c5d982', 1.832),
        (49, 'ขยะรีไซเคิล', 'โลหะ', 'ท่อเหล็ก', 'Steel pipe', 'กิโลกรัม', 'Kilogram', 1, '#cbdd90', 1.832),
        (50, 'ขยะรีไซเคิล', 'โลหะ', 'ผลิตภัณฑ์เหล็กอื่น ๆ', 'Other steel', 'กิโลกรัม', 'Kilogram', 1, '#d2e19e', 1.832),
        (51, 'ขยะรีไซเคิล', 'โลหะ', 'เหล็กหนา', 'Thick Steel', 'กิโลกรัม', 'Kilogram', 1, '#d8e5ac', 1.832),
        (52, 'ขยะรีไซเคิล', 'โลหะ', 'เหล็กบาง', 'Thin Steel', 'กิโลกรัม', 'Kilogram', 1, '#CCCC99', 1.832),
        (53, 'ขยะรีไซเคิล', 'โลหะ', 'ทองแดงปอกสวย (1)', 'Copper 1 (pre treated)', 'กิโลกรัม', 'Kilogram', 1, '#a8a856', 1.832),
        (54, 'ขยะรีไซเคิล', 'โลหะ', 'ทองเหลืองบาง', 'Brass Thin', 'กิโลกรัม', 'Kilogram', 1, '#7d7d43', 1.832),
        (55, 'ขยะรีไซเคิล', 'โลหะ', 'สแตนเลส', 'Stainless Steel', 'กิโลกรัม', 'Kilogram', 1, '#9e9e75', 1.832),
        (56, 'ขยะรีไซเคิล', 'โลหะ', 'ตะกั่ว', 'Lead', 'กิโลกรัม', 'Kilogram', 1, '#c6db7b', 1.832),
        (57, 'ขยะรีไซเคิล', 'โลหะ', 'สังกะสี', 'Zinc', 'กิโลกรัม', 'Kilogram', 1, '#abbf69', 1.832),
        (58, 'ขยะรีไซเคิล', 'โลหะ', 'ทองแดงปอกดำ ช๊อต (2)', 'Copper Short Circuit 2 (thick)', 'กิโลกรัม', 'Kilogram', 1, '#98aa5d', 1.832),
        (59, 'ขยะรีไซเคิล', 'โลหะ', 'ทองแดงเส้นใหญ่ เผา (3)', 'Copper Burn 3 (thick)', 'กิโลกรัม', 'Kilogram', 1, '#859551', 1.832),
        (60, 'ขยะรีไซเคิล', 'โลหะ', 'ทองแดงเส้นเล็ก เผา (4)', 'Copper Burn 4 (thin small)', 'กิโลกรัม', 'Kilogram', 1, '#727f46', 1.832),
        (61, 'ขยะรีไซเคิล', 'โลหะ', 'ทองแดงเส้นเล็ก (เครือบขาว)', 'Copper (mixed aluminum)', 'กิโลกรัม', 'Kilogram', 1, '#5f6a3a', 1.832),
        (62, 'ขยะรีไซเคิล', 'โลหะ', 'ทองแดง', 'Copper', 'กิโลกรัม', 'Kilogram', 1, '#4c552e', 1.832),
        (63, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'บัลลาสไฟ', 'Ballast', 'ตามราคาประเมินหน้างาน', 'Estimate price on site', 1, '#393f23', 1.832),
        (64, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'อุปกรณ์คอมพิวเตอร์', 'Computer accessories', 'เครื่อง', 'Price per unit', 1, '#626262', 0),
        (65, 'ขยะอิเล็กทรอนิกส์', 'โทรคมนาคม', 'โทรศัพท์มือถือ', 'Mobile Phone', 'เครื่อง', 'Price per unit', 1, '#717171', 0),
        (66, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'ทีวี', 'TV', 'เครื่อง', 'Price per unit', 1, '#818181', 0),
        (67, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'เครื่องถ่ายเอกสาร แฟ๊กซ์ ปริ๊นเตอร์', 'Fax Printer Xerox', 'เครื่อง', 'Price per unit', 1, '#919191', 0),
        (68, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'เครื่องเล่นเสียง วิทยุ สเตอริโอ', 'Radio Stereo', 'เครื่อง', 'Price per unit', 1, '#a0a0a0', 0),
        (69, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'พัดลมตั้งโต๊ะ พัดลมเพดาน', 'Fan', 'เครื่อง', 'Price per unit', 1, '#b0b0b0', 0),
        (70, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'เครื่องครัวทำอาหาร หม้อหุงข้าว เตาอบ', 'Rice Cooker Oven', 'เครื่อง', 'Price per unit', 1, '#c0c0c0', 0),
        (71, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'อุปกรณ์ทำความสะอาด เครื่องดูดฝุ่น', 'Vacuum Cleaner', 'เครื่อง', 'Price per unit', 1, '#cfcfcf', 0),
        (72, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'เครื่องซักผ้า เครื่องอบผ้า', 'Washing Machine Dryer', 'เครื่อง', 'Price per unit', 1, '#dfdfdf', 0),
        (73, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'อิเล็กทรอนิกส์อื่น ๆ', 'Other electronic appliances', 'เครื่อง', 'Price per unit', 1, '#BEBEBE', 0),
        (74, 'ขยะรีไซเคิล', 'โลหะ', 'อลูมิเนียม หนา', 'Aluminum Thick', 'กิโลกรัม', 'Kilogram', 1, '#a5cca5', 9.127),
        (75, 'ขยะรีไซเคิล', 'โลหะ', 'กระป๋องอลูมิเนียม (ขายตามน้ำหนักกิโลกรัม)', 'Aluminum Can (Kg)', 'กิโลกรัม', 'Kilogram', 1, '#88B288', 9.127),
        (76, 'ขยะรีไซเคิล', 'โลหะ', 'กระป๋องอลูมิเนียม (ขายนับกระป๋อง)', 'Aluminum Can (by can)', 'ตามราคาประเมินต่อกระป๋อง', 'Price per can', 0.015, '#9fc19f', 9.127),
        (77, 'ขยะอินทรีย์', 'เศษอาหารและพืช', 'เศษอาหาร', 'Foodwaste', 'กิโลกรัม', 'Kilogram', 1, '#4e7f52', 0.465),
        (78, 'ขยะอินทรีย์', 'เศษอาหารและพืช', 'ใบไม้ ต้นไม้', 'Leaves Trees', 'กิโลกรัม', 'Kilogram', 1, '#628d65', 0.854),
        (79, 'ขยะอินทรีย์', 'เศษอาหารและพืช', 'ขยะย่อยสลายได้อื่น ๆ', 'Other organic waste', 'กิโลกรัม', 'Kilogram', 1, '#759b78', 0.465),
        (80, 'ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีขาว', 'PVC Pipes White', 'กิโลกรัม', 'Kilogram', 1, '#23453e', 1.031),
        (81, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกนิ่ม', 'Soft Plastic Cup', 'กิโลกรัม', 'Kilogram', 1, '#1e3b35', 1.031),
        (82, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษย่อยเส้น ขาวดำ', 'Shredded Paper (White and Black)', 'กิโลกรัม', 'Kilogram', 1, '#669933', 5.674),
        (83, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษย่อยเส้น สี รวมสี', 'Shredded Paper (Mixed Color)', 'กิโลกรัม', 'Kilogram', 1, '#99CC33', 5.674),
        (84, 'ขยะรีไซเคิล', 'โลหะ', 'อลูนิเนียม บาง', 'Aluminum Thin', 'กิโลกรัม', 'Kilogram', 1, '#bccfbc', 9.127),
        (85, 'ขยะรีไซเคิล', 'โลหะ', 'ทองเหลืองหนา', 'Brass thick', 'กิโลกรัม', 'Kilogram', 1, '#5f7025', 1.832),
        (86, 'ขยะรีไซเคิล', 'พลาสติก', 'ฟิวเจอร์บอร์ด', 'Coroplast Sign Board', 'กิโลกรัม', 'Kilogram', 1, '#19312c', 1.031),
        (87, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงปุ๋ย', 'Fertilizer Plastic Sack', 'กิโลกรัม', 'Kilogram', 1, '#142723', 1.031),
        (88, 'ขยะรีไซเคิล', 'พลาสติก', 'แฟ้มพลาสติก', 'Plastic Folder / Binder', 'กิโลกรัม', 'Kilogram', 1, '#0f1d1a', 1.031),
        (89, 'ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีเทา เหลือง', 'PVC Pipes Grey Yellow', 'กิโลกรัม', 'Kilogram', 1, '#02382c', 1.031),
        (90, 'ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีสีฟ้า', 'PVC Pipes Cyan', 'กิโลกรัม', 'Kilogram', 1, '#6c8278', 1.031),
        (91, 'ขยะรีไซเคิล', 'พลาสติก', 'แผงไข่', 'Egg Packaging', 'กิโลกรัม', 'Kilogram', 1, '#6c8942', 5.674),
        (92, 'ขยะรีไซเคิล', 'พลาสติก', 'หลอดพลาสติก', 'Plastic Straw', 'กิโลกรัม', 'Kilogram', 1, '#486b64', 1.031),
        (93, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายไฟบ้าน', 'Electrical Wire', 'กิโลกรัม', 'Kilogram', 1, '#13150b', 1.832),
        (94, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ขยะทั่วไป', 'General Waste', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0),
        (95, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายไฟในอาคาร', 'Building Electrical Wire', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.832),
        (96, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายยูเอสบี', 'USB Cord', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.832),
        (97, 'ขยะรีไซเคิล', 'พลาสติก', 'กระสอบข้าว', 'Rice Plastic Sack', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (98, 'ขยะรีไซเคิล', 'พลาสติก', 'กระสอบน้ำตาล', 'Sugar Plastic Sack', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (99, 'ขยะรีไซเคิล', 'พลาสติก', 'กล่องนม กล่องน้ำผลไม้', 'UHT Carton', 'กิโลกรัม', 'Kilogram', 1, '#607a3b', 4.255),
        (100, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติก HDPE สี', 'Colored Plastic (HDPE)', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (101, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกรวมสี PP', 'Other Color Plastic PP', 'กิโลกรัม', 'Kilogram', 1, '#84a19b', 1.031),
        (102, 'ขยะรีไซเคิล', 'พลาสติก', 'อะคริลิค', 'Acrylic', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (103, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'เครื่องปรับอากาศและคอมเพรสเซอร์แอร์ 1 คู่', 'Fancoil Unit FCU and Condensing Unit CDU', 'เครื่อง', 'Price per unit', 1, '#585858', 0),
        (104, 'ขยะรีไซเคิล', 'พลาสติก', 'ซองอ่อนหลายชั้น', 'Multilayer flexible packaging', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (105, 'ขยะอันตราย', 'หลอดไฟและสเปรย์', 'หลอดไฟที่ชำรุด', 'Damaged bulb', 'กิโลกรัม', 'Kilogram', 1, '#db3831', 0),
        (106, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'แมคเนติก และ แผงวงจรที่ชำรุด', 'Magnetic and Damaged circuit board', 'กิโลกรัม', 'Kilogram', 1, '#de4b45', 0),
        (107, 'ขยะรีไซเคิล', 'ไม้', 'ไม้', 'Wood', 'กิโลกรัม', 'Kilogram', 1, '#89a98b', 0.854),
        (109, 'ขยะอันตราย', 'แบตเตอรี่', 'ถ่านไฟฉายเก่า', 'Old batteries', 'กิโลกรัม', 'Kilogram', 1, '#e25f5a', 0),
        (110, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ขยะทำเชื้อเพลิง', 'Waste to Energy Material', 'กิโลกรัม', 'Kilogram', 1, '#e7853a', 0),
        (111, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'พลาสติกรวม ทำพลังงาน', 'Waste to energy', 'กิโลกรัม', 'Kilogram', 1, '#3662a6', 0),
        (113, 'ขยะอันตราย', 'อื่นๆ', 'ขยะอันตรายรวม', 'Mix Hazardous Waste', 'กิโลกรัม', 'Kilogram', 1, '#e5736e', 0),
        (114, 'ขยะอันตราย', 'เคมีและของเหลว', 'น้ำมันพืช', 'Vegetable Cooking Oil', 'กิโลกรัม', 'Kilogram', 1, '#9db89f', 0.465),
        (115, 'ขยะทางการแพทย์/ติดเชื้อ', 'อื่นๆ', 'ขยะติดเชื้อ', 'Bio Hazardous', 'กิโลกรัม', 'Kilogram', 1, '#e98783', 0),
        (116, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้ว PLA', 'PLA Cup', 'กิโลกรัม', 'Kilogram', 1, '#4c73b0', 0),
        (117, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกพีวีซี รวม', 'Other PVC', 'กิโลกรัม', 'Kilogram', 1, '#669999', 1.031),
        (118, 'ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีรวม', 'Other PVC Pipes', 'กิโลกรัม', 'Kilogram', 1, '#1d8079', 1.031),
        (119, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกนิ่ม (PP)', 'PP Soft Plastic Cup', 'กิโลกรัม', 'Kilogram', 1, '#2fa38b', 1.031),
        (120, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกรวม (PP PS BIO)', 'Other Plastic Cup', 'กิโลกรัม', 'Kilogram', 1, '#35b89d', 1.031),
        (121, 'ขยะทั่วไป', 'พลาสติกปนเปื้อน', 'เม็ดพลาสติกปนเปื้อน (PS)', 'PS Pellets Contaminate', 'กิโลกรัม', 'Kilogram', 1, '#38c9ac', 1.031),
        (122, 'ขยะทั่วไป', 'พลาสติกปนเปื้อน', 'เม็ดพลาสติกปนเปื้อน (PP)', 'PP Pellets Contaminate', 'กิโลกรัม', 'Kilogram', 1, '#3bdbbb', 1.031),
        (123, 'ขยะรีไซเคิล', 'พลาสติก', 'เกล็ดโม่ (PP)', 'PP Flakes', 'กิโลกรัม', 'Kilogram', 1, '#3febc8', 1.031),
        (124, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังน้ำมันพลาสติกเปล่า 20 ลิตร (HDPE)', 'HDPE Oil container', 'ถัง', 'Price per gallon', 1.5, '#42fcd6', 1.031),
        (125, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงบิ๊กแบ็ก (ตัดปาก)', 'Big Bags Wide', 'ใบ', 'Price per bag', 3, '#08997b', 1.031),
        (126, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงบิ๊กแบ็ก (ไม่ตัดปาก)', 'Big Bags Narrow', 'ใบ', 'Price per bag', 3, '#0bbf9b', 1.031),
        (127, 'ขยะรีไซเคิล', 'พลาสติก', 'เศษก้อน (PS)', 'PS Lumps', 'กิโลกรัม', 'Kilogram', 1, '#0ccfa8', 1.031),
        (128, 'ขยะรีไซเคิล', 'พลาสติก', 'เศษก้อน (PP)', 'PP Lumps', 'กิโลกรัม', 'Kilogram', 1, '#0bdeb4', 1.031),
        (129, 'ขยะรีไซเคิล', 'กระดาษ', 'แกนกระดาษ', 'Paper Cores', 'กิโลกรัม', 'Kilogram', 1, '#4c9404', 5.674),
        (130, 'ขยะรีไซเคิล', 'กระดาษ', 'ถุงกระสอบเคลือบกระดาษ', 'Multiwall Paper Sacks', 'กิโลกรัม', 'Kilogram', 1, '#5cb504', 5.674),
        (131, 'ขยะรีไซเคิล', 'โลหะ', 'กระป๋องเหล็ก', 'Metal Cans', 'กิโลกรัม', 'Kilogram', 1, '#a89676', 1.832),
        (132, 'ขยะรีไซเคิล', 'โลหะ', 'เศษขี้กลึงเหล็ก', 'Steel Turning Scrap', 'กิโลกรัม', 'Kilogram', 1, '#b2cc5c', 1.832),
        (133, 'ขยะรีไซเคิล', 'โลหะ', 'เศษเหล็กรวม', 'Steel Scrap', 'กิโลกรัม', 'Kilogram', 1, '#bfdb63', 1.832),
        (134, 'ขยะก่อสร้าง', 'โลหะ', 'ถังน้ำมันเหล็กเปล่า 200 ลิตร ถังใหม่', 'Metal Oil Container 200 liter (New Bucket)', 'ถัง', 'Bucket', 18, '#9ab837', 1.832),
        (135, 'ขยะก่อสร้าง', 'โลหะ', 'ถังน้ำมันเหล็กเปล่า 200 ลิตร ถังเก่า', 'Metal Oil Container 200 liter (Old Bucket)', 'ถัง', 'Bucket', 18, '#afd13f', 1.832),
        (136, 'ขยะรีไซเคิล', 'โลหะ', 'เศษอลูมิเนียม', 'Aluminium Scrap', 'กิโลกรัม', 'Kilogram', 1, '#77b577', 9.127),
        (137, 'ขยะรีไซเคิล', 'ไม้', 'เศษไม้พาเลท', 'Pallet wood chips', 'กิโลกรัม', 'Kilogram', 1, '#6a996d', 0.854),
        (138, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ยางรถ 6 ล้อ', 'Six wheel car tires', 'เส้น', 'Price per line', 40, '#ad4db8', 0),
        (139, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ยางรถยนต์', 'Car tires', 'เส้น', 'Price per line', 15, '#c747d6', 0),
        (140, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ยางรถโฟล์คลิฟท์', 'Forklift car tires', 'เส้น', 'Price per line', 17, '#ea3bff', 0),
        (141, 'ขยะรีไซเคิล', 'อื่นๆ', 'หงส์ทอง ลัง 12 ขวด', 'Hong Thong (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#b3e3bc', 0.276),
        (142, 'ขยะรีไซเคิล', 'ไม้', 'ไม้พาเลท', 'Pallet wood', 'กิโลกรัม', 'Kilogram', 1, '#cc9266', 0),
        (143, 'ขยะอันตราย', 'หลอดไฟและสเปรย์', 'กระป๋องสเปรย์', 'Aerosol cans', 'กิโลกรัม', 'Kilogram', 1, '#8c0500', 0),
        (144, 'ขยะอันตราย', 'เคมีและของเหลว', 'ภาชนะปนเปื้อน', 'Contaminated containers', 'กิโลกรัม', 'Kilogram', 1, '#b30802', 0),
        (145, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายโฮส', 'Hose line', 'กิโลกรัม', 'Kilogram', 1, '#d10902', 0),
        (146, 'ขยะรีไซเคิล', 'อื่นๆ', 'อุปกรณ์สำนักงาน', 'Office supplies', 'กิโลกรัม', 'Kilogram', 1, '#ed0a02', 0),
        (147, 'ขยะอันตราย', 'เคมีและของเหลว', 'วัสดุปนเปื้อน', 'Contaminated fabric', 'กิโลกรัม', 'Kilogram', 1, '#800703', 0),
        (148, 'ขยะอันตราย', 'เคมีและของเหลว', 'ขี้เลื่อยปนเปื้อนน้ำมัน', 'Sawdust contaminated with oil', 'กิโลกรัม', 'Kilogram', 1, '#660300', 0),
        (149, 'ขยะรีไซเคิล', 'อื่นๆ', 'แสงโสม ลัง 12 ขวด', 'Sang Som (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#84ab8b', 0.276),
        (150, 'ขยะรีไซเคิล', 'พลาสติก', 'ฟิล์มยืด', 'Stretch Film', 'กิโลกรัม', 'Kilogram', 1, '#49786d', 1.031),
        (151, 'ขยะรีไซเคิล', 'พลาสติก', 'สายรัดพลาสติก (PET)', 'Plastic Strap (PET)', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (152, 'ขยะรีไซเคิล', 'พลาสติก', 'สายรัดพลาสติก (PP)', 'Plastic Strap (PP)', 'กิโลกรัม', 'Kilogram', 1, '#69857e', 1.031),
        (153, 'ขยะรีไซเคิล', 'โลหะ', 'ปี๊บ', 'Bucket Steel', 'กิโลกรัม', 'Kilogram', 1, '#ccccab', 1.832),
        (154, 'ขยะรีไซเคิล', 'โลหะ', 'กระป๋องสเปรย์ (รีไซเคิล)', 'Aerosol Cans (Recycle)', 'กิโลกรัม', 'Kilogram', 1, '#828267', 1.832),
        (155, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'โฟม (เผากำจัด)', 'Foam (Inceneration)', 'กิโลกรัม', 'Kilogram', 1, '#6d90c7', 0),
        (156, 'ขยะรีไซเคิล', 'พลาสติก', 'โฟม', 'Foam (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, '#f09a59', 0),
        (157, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ถุงพลาสติก (เผากำจัด)', 'Plastic Bag (Inceneration)', 'กิโลกรัม', 'Kilogram', 1, '#728581', 0),
        (158, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงพลาสติก', 'Plastic Bag (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, '#95a8c4', 0),
        (159, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงขนม / ซองอ่อนหลายชั้น', 'Multilayer packaging (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, '#d9baa3', 0),
        (160, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ถุงขนม / ซองอ่อนหลายชั้น (เผากำจัด)', 'Multilayer packaging (Inceneration)', 'กิโลกรัม', 'Kilogram', 1, '#98a3a1', 0),
        (186, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ขยะฝังกลบ', 'Waste to Landfill', 'กิโลกรัม', 'Kilogram', 1, '#3269bf', 0),
        (187, 'ขยะทางการแพทย์/ติดเชื้อ', 'ของใช้ส่วนตัว', 'ผ้าอนามัย', 'Sanitary napkin', 'กิโลกรัม', 'Kilogram', 1, '#bd6073', 0),
        (188, 'ขยะทางการแพทย์/ติดเชื้อ', 'ของใช้ส่วนตัว', 'หน้ากากอนามัย', 'Face mask', 'กิโลกรัม', 'Kilogram', 1, '#e899a9', 0),
        (189, 'ขยะรีไซเคิล', 'พลาสติก', 'เชือก PP/PE', 'PP/PE Rope', 'กิโลกรัม', 'Kilogram', 1, '#7dd1bf', 1.031),
        (190, 'ขยะรีไซเคิล', 'พลาสติก', 'ตาข่าย HDPE', 'HDPE Net', 'กิโลกรัม', 'Kilogram', 1, '#9dc7be', 1.031),
        (191, 'ขยะรีไซเคิล', 'พลาสติก', 'ตาข่าย Nylon', 'Nylon Net', 'กิโลกรัม', 'Kilogram', 1, '#a2bdb7', 1.031),
        (192, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีรวม (รีไซเคิลทางเลือก)', 'Mixed Glass (Recycling Alternative)', 'กิโลกรัม', 'Kilogram', 1, '#3a6642', 0.276),
        (193, 'ขยะอันตราย', 'แบตเตอรี่', 'แบตเตอรี่ วิทยุสื่อสาร', 'Walkie Talkie Battery', 'กิโลกรัม', 'Kilogram', 1, '#b37244', 0),
        (194, 'ขยะก่อสร้าง', 'โลหะ', 'ล้อแม็กซ์', 'Max Wheel (Aluminium Alloy)', 'กิโลกรัม', 'Kilogram', 1, '#8da18d', 9.127),
        (195, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกดำ', 'Black Plastic', 'กิโลกรัม', 'Kilogram', 1, '#7bedd3', 1.031),
        (196, 'ขยะอันตราย', 'แบตเตอรี่', 'แบตเตอรี่รถยนต์และมอเตอร์ไซค์', 'Automotive Battery', 'กิโลกรัม', 'Kilogram', 1, '#825738', 0),
        (197, 'ขยะรีไซเคิล', 'พลาสติก', 'เศษผงพลาสติก (PP)', 'PP Plastic Powder', 'กิโลกรัม', 'Kilogram', 1, '#b6ccc7', 1.031),
        (198, 'ขยะรีไซเคิล', 'โลหะ', 'หม้อน้ำอลูมิเนียม', 'Aluminium Radiator', 'กิโลกรัม', 'Kilogram', 1, '#6a8a6a', 9.127),
        (199, 'ขยะรีไซเคิล', 'โลหะ', 'หม้อน้ำทองแดง', 'Copper Radiator', 'กิโลกรัม', 'Kilogram', 1, '#9cbf1d', 1.832),
        (200, 'ขยะรีไซเคิล', 'โลหะ', 'อลูมิเนียมฉาก', 'Aluminum Angle', 'กิโลกรัม', 'Kilogram', 1, '#4b7d4b', 9.127),
        (201, 'ขยะรีไซเคิล', 'พลาสติก', 'ตาข่ายรวม (PE PP Nylon)', 'Fishing Net', 'กิโลกรัม', 'Kilogram', 1, '#5bc7b1', 1.031),
        (202, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วรวม ลัง 12 ขวด', 'Colored Glass (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '#4bad5e', 0.276),
        (203, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วรวม ขวดเล็ก ลัง 24 ขวด', 'Colored Glass 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '#5cc470', 0.276),
        (204, 'ขยะรีไซเคิล', 'อื่นๆ', 'เศษผ้า', 'Contaminated Fabric', 'กิโลกรัม', 'Kilogram', 1, '#a88f7d', 0),
        (205, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกรวม', 'Other plastic (Waste to Energy)', 'กิโลกรัม', 'Kilogram', 1, '#ebd8ca', 0),
        (206, 'ขยะอันตราย', 'เคมีและของเหลว', 'สารเคมีอันตราย', 'Hazardous Chemicals', 'กิโลกรัม', 'Kilogram', 1, '#66391a', 0),
        (207, 'ขยะอันตราย', 'เคมีและของเหลว', 'น้ำมันหล่อลื่น', 'Lubricant Oil', 'กิโลกรัม', 'Kilogram', 1, '#b0896f', 0),
        (208, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'ตลับหมึกจากเครื่องปริ้นท์', 'Ink cartridges from printers', 'กิโลกรัม', 'Kilogram', 1, '#dec3b1', 0),
        (209, 'ขยะอันตราย', 'เคมีและของเหลว', 'น้ำจากแอร์คอมเพลสเซอร์ปนเปื้อนน้ำมัน', 'Waste water from compressor', 'กิโลกรัม', 'Kilogram', 1, '#f7b68b', 0),
        (210, 'ขยะรีไซเคิล', 'พลาสติก', 'สายรัดพลาสติกรวม (PET PP HDPE)', 'Plastic Strap (PET PP HDPE)', 'กิโลกรัม', 'Kilogram', 1, '#486660', 1.031),
        (211, 'ขยะรีไซเคิล', 'โลหะ', 'ถังโลหะ', 'Metal Bucket', 'กิโลกรัม', 'Kilogram', 1, '#c5f522', 1.832),
        (212, 'ขยะรีไซเคิล', 'โลหะ', 'ถังเหล็กเปล่า 210 ลิตร', 'Steel Container 210 liter', 'กิโลกรัม', 'Kilogram', 1, '#749406', 1.832),
        (213, 'ขยะรีไซเคิล', 'ไม้', 'ไม้พาเลท', 'Wood Pallet', 'กิโลกรัม', 'Kilogram', 1, '#5bb07c', 0.854),
        (214, 'ขยะรีไซเคิล', 'พลาสติก', 'พาเลทพลาสติกรวม (HDPE PP)', 'Other Plastic Pallet (HDPE PP)', 'กิโลกรัม', 'Kilogram', 1, '#73807d', 1.031),
        (215, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'เนยและชีสเสื่อมสภาพ น้ำมันพืช น้ำมัน Stearin', 'Decay Butter and Cheese, Vegetable Cooking Oil, Stearin Oil', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0.465),
        (216, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'แป้งเสื่อมสภาพ', 'Starch is not of good quality', 'กิโลกรัม', 'Kilogram', 1, '#29d936', 0.465),
        (217, 'ขยะรีไซเคิล', 'อื่นๆ', 'เรซิ่น กรองน้ำ', 'Resin filter', 'กิโลกรัม', 'Kilogram', 1, '#9abef5', 0),
        (218, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'กากตะกอนไขมัน', 'Fat Sludge', 'กิโลกรัม', 'Kilogram', 1, '#b1fab7', 0.465),
        (219, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'กากตะกอนจากระบบบำบัดน้ำเสีย', 'Sludge from the wastewater treatment system', 'กิโลกรัม', 'Kilogram', 1, '#073d0c', 0.465),
        (220, 'ขยะก่อสร้าง', 'วัสดุก่อสร้าง', 'วัสดุกรองน้ำ (หินกรวด)', 'Water filter material (Gravel Stones)', 'กิโลกรัม', 'Kilogram', 1, '#7d92b3', 0),
        (221, 'ขยะรีไซเคิล', 'พลาสติก', 'โพลีคาร์บอเนต', 'Polycarbonate', 'กิโลกรัม', 'Kilogram', 1, '#12c48f', 1.031),
        (222, 'ขยะรีไซเคิล', 'พลาสติก', 'เชือกโพลีเอสเตอร์', 'Polyester Rope', 'กิโลกรัม', 'Kilogram', 1, '#00ffb3', 1.031),
        (223, 'ขยะรีไซเคิล', 'พลาสติก', 'แฟ้ม', 'Document Folder', 'กิโลกรัม', 'Kilogram', 1, '#b2f551', 5.674),
        (224, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษเคลือบมัน', 'Coated Paper', 'กิโลกรัม', 'Kilogram', 1, '#caff7d', 5.674),
        (225, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงกระสอบ', 'Paper Sack Bag', 'กิโลกรัม', 'Kilogram', 1, '#9cab85', 5.674),
        (226, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'กากตะกอน (กาวน้ำ)', 'Sludge (Water Glue)', 'ตัน', 'Tonne', 1000, '#667894', 0),
        (227, 'ขยะก่อสร้าง', 'วัสดุก่อสร้าง', 'ฝุ่นปูน', 'Mortar Powder', 'กิโลกรัม', 'Kilogram', 1, '#f0ac78', 0),
        (228, 'ขยะก่อสร้าง', 'วัสดุก่อสร้าง', 'ฝุ่นปูน (ฝังกลบ)', 'Mortar Powder (Landfill)', 'ตัน', 'Tonne', 1000, '#aecaf5', 0),
        (229, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังพลาสติก 1000 ลิตร', 'Plastic Bucket 1000 liter', 'ถัง', 'Bucket', 20, '#638a82', 1.031),
        (230, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังพลาสติก 150 ลิตร', 'Plastic Bucket 150 liter', 'ถัง', 'Bucket', 7, '#9dc4bd', 1.031),
        (231, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังพลาสติก 200 ลิตร', 'Plastic Bucket 200 liter', 'ถัง', 'Bucket', 9, '#53827a', 1.031),
        (232, 'ขยะรีไซเคิล', 'โลหะ', 'ถังเหล็ก 200 ลิตร', 'Steel Bucket 200 liter', 'ถัง', 'Bucket', 15, '#b1c961', 1.832),
        (233, 'ขยะอันตราย', 'หลอดไฟและสเปรย์', 'ไส้กรองน้ำมัน', 'Oil Filter', 'กิโลกรัม', 'Kilogram', 1, '#e36e1b', 0),
        (234, 'ขยะก่อสร้าง', 'โลหะ', 'ขาเหล็ก (ถังพลาสติก 1000 ลิตร)', 'Steel legs of plastic bucket (Plastic Bucket 1000 liter)', 'กิโลกรัม', 'Kilogram', 1, '#586628', 1.832),
        (235, 'ขยะรีไซเคิล', 'ไม้', 'ขาไม้ (ถังพลาสติก 1000 ลิตร)', 'Wooden legs of plastic bucket (Plastic Bucket 1000 liter)', 'กิโลกรัม', 'Kilogram', 1, '#086910', 0.854),
        (236, 'ขยะรีไซเคิล', 'โลหะ', 'อลูมิเนียมสายไฟปอกสวย', 'Aluminum Wire (Unwrap)', 'กิโลกรัม', 'Kilogram', 1, '#596659', 9.127),
        (237, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'จอคอมพิวเตอร์', 'Computer Monitor', 'เครื่อง', 'Price per unit', 1, '#918686', 0),
        (238, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'ตู้เย็น', 'Refrigerator', 'เครื่อง', 'Price per unit', 1, '#decaca', 0),
        (239, 'ขยะรีไซเคิล', 'ไม้', 'ไม้พาเลท (นับเป็นชิ้น)', 'Wood Pallet (counted as a piece)', 'ชิ้น', 'Piece', 15, '#1d4220', 0.854),
        (240, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังพลาสติก 1000 ลิตร (ขาเหล็ก)', 'Plastic Bucket 1000 liter (Steel stand)', 'ถัง', 'Bucket', 20, '#1bcc91', 1.031),
        (241, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังพลาสติก 1000 ลิตร (ขาไม้)', 'Plastic Bucket 1000 liter (Wood stand)', 'ถัง', 'Bucket', 20, '#1c8562', 1.031),
        (242, 'ขยะรีไซเคิล', 'โลหะ', 'หม้อน้ำทองเหลือง', 'Brass Radiator', 'กิโลกรัม', 'Kilogram', 1, '#87a35d', 1.832),
        (243, 'ขยะรีไซเคิล', 'พลาสติก', 'เชือกฟาง', 'Plastic Rope (PP)', 'กิโลกรัม', 'Kilogram', 1, '#7ac2bc', 1.031),
        (244, 'ขยะก่อสร้าง', 'โลหะ', 'หัวเสาเข็ม', 'Pile Head', 'กิโลกรัม', 'Kilogram', 1, '#3de0f5', 0),
        (245, 'ขยะก่อสร้าง', 'วัสดุก่อสร้าง', 'คอนกรีต', 'Concrete', 'กิโลกรัม', 'Kilogram', 1, '#116773', 0),
        (246, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกใส PP', 'Clear Plastic PP', 'กิโลกรัม', 'Kilogram', 1, '#d1e6e1', 1.031),
        (247, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกใส สกรีน PP', 'Clear Plastic Screen PP', 'กิโลกรัม', 'Kilogram', 1, '#b0bfbc', 1.031),
        (248, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ไส้กรองน้ำมัน (ขยะทำเชื้อเพลิง)', 'Oil Filter (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, '#F5CB06', 0),
        (249, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ฟิวเจอร์บอร์ด (ขยะทำเชื้อเพลิง)', 'Corrugated plastic board', 'กิโลกรัม', 'Kilogram', 1, '#f0c84f', 0),
        (250, 'ขยะรีไซเคิล', 'พลาสติก', 'ไวนิล', 'Vinyl', 'กิโลกรัม', 'Kilogram', 1, '#ccba6c', 0),
        (251, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกรวม (PET PP PS BIO)', 'Other Plastic Cup (PET PP PS BIO)', 'กิโลกรัม', 'Kilogram', 1, '#004f3f', 1.031),
        (252, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'เครื่องคอมพิวเตอร์', 'Desktop PC', 'กิโลกรัม', 'Kilogram', 1, '#b5b5b5', 0),
        (253, 'ขยะอันตราย', 'แบตเตอรี่', 'แบตเตอรี่คอมพิวเตอร์', 'Computer Battery', 'กิโลกรัม', 'Kilogram', 1, '#c9c9c9', 0),
        (254, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายชาร์จ', 'Charging Cable', 'กิโลกรัม', 'Kilogram', 1, '#ad9393', 0),
        (255, 'ขยะทางการแพทย์/ติดเชื้อ', 'อื่นๆ', 'ชุดตรวจ ATK', 'Antigen Test Kit (ATK)', 'กิโลกรัม', 'Kilogram', 1, '#8a6a70', 0),
        (256, 'ขยะทั่วไป', 'กระดาษและวัสดุผสม', 'กระดาษชำระ', 'Toilet Paper', 'กิโลกรัม', 'Kilogram', 1, '#bd959d', 0),
        (257, 'ขยะรีไซเคิล', 'พลาสติก', 'ขวดและแกลลอน HDPE โปร่งแสง', 'Transparent HDPE bottle/gallon', 'กิโลกรัม', 'Kilogram', 1, '#0b8a83', 1.031),
        (258, 'ขยะรีไซเคิล', 'พลาสติก', 'ขวดและแกลลอน HDPE สีขาวทึบ', 'White opaque HDPE bottle/gallon', 'กิโลกรัม', 'Kilogram', 1, '#09b5ac', 1.031),
        (259, 'ขยะรีไซเคิล', 'พลาสติก', 'ขวดและแกลลอน HDPE หลากสีทึบ', 'Colored and opaque HDPE bottle/gallon', 'กิโลกรัม', 'Kilogram', 1, '#3cd6ce', 1.031),
        (260, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติก LDPE รวม', 'Other Plastic LDPE', 'กิโลกรัม', 'Kilogram', 1, '#02362b', 1.031),
        (261, 'ขยะรีไซเคิล', 'พลาสติก', 'ไบโอพลาสติก', 'Bio Plastic', 'กิโลกรัม', 'Kilogram', 1, '#0c7871', 1.031),
        (262, 'ขยะอันตราย', 'แบตเตอรี่', 'แบตเตอรี่รวม', 'Other Battery', 'กิโลกรัม', 'Kilogram', 1, '#e6a94e', 0),
        (263, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'กากตะกอนไขมัน (ฝังกลบ)', 'Fat Sludge (Landfill)', 'กิโลกรัม', 'Kilogram', 1, '#617fad', 0),
        (272, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกสีรวม (PET)', 'Mixed color plastic (PET)', 'กิโลกรัม', 'Kilogram', 1, '#41ab7b', 1.031),
        (273, 'ขยะรีไซเคิล', 'พลาสติก', 'HDPE ขาวขุ่น สกรีน', 'Transparent HDPE with screening', 'กิโลกรัม', 'Kilogram', 1, '#69b39d', 1.031),
        (284, 'ขยะรีไซเคิล', 'โลหะ', 'หม้อน้ำอลูมิเนียม', 'Aluminium Radiator', 'กิโลกรัม', 'Kilogram', 1, '#6a8a6a', 9.127),
        (285, 'ขยะรีไซเคิล', 'อื่นๆ', 'ถังน้ำแข็ง', 'Ice Bucket', 'กิโลกรัม', 'Kilogram', 1, '#628c8a', 1.031),
        (286, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ไม้ (ขยะทั่วไป)', 'Wood (General Waste)', 'กิโลกรัม', 'Kilogram', 1, '#628c8a', 0),
        (287, 'ขยะรีไซเคิล', 'พลาสติก', 'ขวดใส PET แบบสกรีน', 'Screened color PET', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (288, 'ขยะรีไซเคิล', 'พลาสติก', 'ขวดใส PET แบบลอกสลาก', 'PET with no label', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (289, 'ขยะรีไซเคิล', 'พลาสติก', 'ขวดใส PET แบบไม่ลอกสลาก', 'PET with label', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (290, 'ขยะรีไซเคิล', 'อื่นๆ', 'วัสดุรีไซเคิลรวม', 'Recyclable Material', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 1.031),
        (291, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ขยะอินทรีย์และเศษอาหาร', 'Organic and Food Waste', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0.465),
        (292, 'ขยะอันตราย', 'อื่นๆ', 'ขยะอันตรายรวม', 'Hazardous Waste', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0),
        (293, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ขยะพลังงานรวม', 'Waste to Energy', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0),
        (294, 'ขยะทางการแพทย์/ติดเชื้อ', 'อื่นๆ', 'ขยะติดเชื้อรวม', 'Biohazardous Waste', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0),
        (295, 'ขยะอิเล็กทรอนิกส์', 'อื่นๆ', 'ขยะอิเล็กทรอนิกส์รวม', 'Electronic Waste', 'กิโลกรัม', 'Kilogram', 1, '#20519d', 0),
        (297, 'ขยะรีไซเคิล', 'ไม้', 'เศษไม้', 'Wood scrap', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0),
        (298, 'ขยะรีไซเคิล', 'อื่นๆ', 'รีไซเคิลรวม', 'Recyclables', 'กิโลกรัม', 'Kilogram', 1, '#808080', 2.32),
        (299, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'อุจจาระและสิ่งปฏิกูล', 'Sanitary waste', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0),
        (304, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายแลน', 'LAN Cable', 'กิโลกรัม', 'Kilogram', 1, '#808080', 0),
        (305, 'ขยะอินทรีย์', 'เศษอาหารและพืช', 'เศษอาหารจากการจัดเตรียม', 'Preparation waste', 'กิโลกรัม', 'Kilogram', 1, '#4bcf31', 0.465),
        (306, 'ขยะอินทรีย์', 'เศษอาหารและพืช', 'เศษอาหารจากจาน', 'Plate waste', 'กิโลกรัม', 'Kilogram', 1, '#4bcf31', 0.465),
        (307, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติก', 'PET Cup', 'กิโลกรัม', 'Kilogram', 1, '#808080', 1.031),
        (308, 'ขยะอินทรีย์', 'เศษอาหารและพืช', 'อาหารส่วนเกิน', 'Food Surplus', 'กิโลกรัม', 'Kilogram', 1, '#808080', 2.531),
        (309, 'ขยะอันตราย', 'เคมีและของเหลว', 'ยาหมดอายุ', 'Expired medicine', 'กิโลกรัม', 'Kilogram', 1, '#000000', 0),
        (310, 'ขยะอันตราย', 'เคมีและของเหลว', 'สารเคมีใช้แล้ว', 'Used chemicals', 'กิโลกรัม', 'Kilogram', 1, '#000000', 0),
        (311, 'ขยะอันตราย', 'เคมีและของเหลว', 'บรรจุภัณฑ์สารเคมี', 'Chemical packaging', 'กิโลกรัม', 'Kilogram', 1, '#000000', 0)

) AS mat_data(migration_id, category_th, main_material_th, name_th, name_en, unit_name_th, unit_name_en, unit_weight, color, calc_ghg)
LEFT JOIN category_mapping cat ON cat.category_name_th = mat_data.category_th
LEFT JOIN main_material_mapping mm ON mm.main_material_name_th = mat_data.main_material_th
ON CONFLICT (migration_id) DO UPDATE SET
    name_th = EXCLUDED.name_th,
    name_en = EXCLUDED.name_en,
    unit_name_th = EXCLUDED.unit_name_th,
    unit_name_en = EXCLUDED.unit_name_en,
    unit_weight = EXCLUDED.unit_weight,
    color = EXCLUDED.color,
    calc_ghg = EXCLUDED.calc_ghg,
    updated_date = NOW();

-- ======================================
-- DATA VERIFICATION
-- ======================================

DO $$
DECLARE
    category_count INTEGER;
    main_material_count INTEGER;
    material_count INTEGER;
    materials_with_migration_id INTEGER;
BEGIN
    SELECT COUNT(*) INTO category_count FROM material_categories WHERE is_active = true;
    SELECT COUNT(*) INTO main_material_count FROM main_materials WHERE is_active = true;
    SELECT COUNT(*) INTO material_count FROM materials WHERE is_active = true;
    SELECT COUNT(*) INTO materials_with_migration_id FROM materials WHERE migration_id IS NOT NULL;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'COMPLETE MATERIALS MIGRATION COMPLETED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Material Categories: % records', category_count;
    RAISE NOTICE 'Main Materials: % records', main_material_count;
    RAISE NOTICE 'Total Materials: % records', material_count;
    RAISE NOTICE 'Materials with migration_id: % records', materials_with_migration_id;
    RAISE NOTICE 'Expected from CSV: 260 records';

    IF materials_with_migration_id >= 260 THEN
        RAISE NOTICE '✅ SUCCESS: All CSV materials have been migrated!';
    ELSE
        RAISE NOTICE '⚠️  WARNING: Missing materials: %', (260 - materials_with_migration_id);
    END IF;

    RAISE NOTICE '============================================';

    -- Verify all materials have proper relationships
    PERFORM 1 FROM materials WHERE category_id IS NULL OR main_material_id IS NULL;
    IF FOUND THEN
        RAISE WARNING 'Some materials have missing category or main material relationships!';
    ELSE
        RAISE NOTICE '✅ All materials have proper relationships';
    END IF;
END $$;

-- Migration completed