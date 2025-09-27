-- Migration: 20250922_130000_023_complete_materials_migration.sql
-- Description: Complete materials migration with all remaining materials (99-311)
-- Adds the missing 163 materials from CSV with proper migration_id
-- Date: 2025-09-22
-- Author: Claude Code Assistant

-- ======================================
-- INSERT REMAINING MATERIALS (99-311)
-- ======================================

-- Insert all remaining materials from CSV that weren't in the original migration
-- Using CTEs to map categories and main materials

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
        -- Materials 99-150 (continuing from where original migration stopped)
        (99, 'ขยะรีไซเคิล', 'พลาสติก', 'กล่องนม กล่องน้ำผลไม้', 'UHT Carton', 'กิโลกรัม', 'Kilogram', 1, '607a3b', 4.255),
        (100, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติก HDPE สี', 'Colored Plastic (HDPE)', 'กิโลกรัม', 'Kilogram', 1, '808080', 1.031),
        (101, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกรวมสี PP', 'Other Color Plastic PP', 'กิโลกรัม', 'Kilogram', 1, '84a19b', 1.031),
        (102, 'ขยะรีไซเคิล', 'พลาสติก', 'อะคริลิค', 'Acrylic', 'กิโลกรัม', 'Kilogram', 1, '808080', 1.031),
        (103, 'ขยะอิเล็กทรอนิกส์', 'เครื่องใช้ไฟฟ้า', 'เครื่องปรับอากาศและคอมเพรสเซอร์แอร์ 1 คู่', 'Fancoil Unit FCU and Condensing Unit CDU', 'เครื่อง', 'Price per unit', 1, '585858', 0),
        (104, 'ขยะรีไซเคิล', 'พลาสติก', 'ซองอ่อนหลายชั้น', 'Multilayer flexible packaging', 'กิโลกรัม', 'Kilogram', 1, '808080', 1.031),
        (105, 'ขยะอันตราย', 'หลอดไฟและสเปรย์', 'หลอดไฟที่ชำรุด', 'Damaged bulb', 'กิโลกรัม', 'Kilogram', 1, 'db3831', 0),
        (106, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'แมคเนติก และ แผงวงจรที่ชำรุด', 'Magnetic and Damaged circuit board', 'กิโลกรัม', 'Kilogram', 1, 'de4b45', 0),
        (107, 'ขยะรีไซเคิล', 'ไม้', 'ไม้', 'Wood', 'กิโลกรัม', 'Kilogram', 1, '89a98b', 0.854),
        (109, 'ขยะอันตราย', 'แบตเตอรี่', 'ถ่านไฟฉายเก่า', 'Old batteries', 'กิโลกรัม', 'Kilogram', 1, 'e25f5a', 0),
        (110, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ขยะทำเชื้อเพลิง', 'Waste to Energy Material', 'กิโลกรัม', 'Kilogram', 1, 'e7853a', 0),
        (111, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'พลาสติกรวม ทำพลังงาน', 'Waste to energy', 'กิโลกรัม', 'Kilogram', 1, '3662a6', 0),
        (113, 'ขยะอันตราย', 'อื่นๆ', 'ขยะอันตรายรวม', 'Mix Hazardous Waste', 'กิโลกรัม', 'Kilogram', 1, 'e5736e', 0),
        (114, 'ขยะอันตราย', 'เคมีและของเหลว', 'น้ำมันพืช', 'Vegetable Cooking Oil', 'กิโลกรัม', 'Kilogram', 1, '9db89f', 0.465),
        (115, 'ขยะทางการแพทย์/ติดเชื้อ', 'อื่นๆ', 'ขยะติดเชื้อ', 'Bio Hazardous', 'กิโลกรัม', 'Kilogram', 1, 'e98783', 0),
        (116, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้ว PLA', 'PLA Cup', 'กิโลกรัม', 'Kilogram', 1, '4c73b0', 0),
        (117, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกพีวีซี รวม', 'Other PVC', 'กิโลกรัม', 'Kilogram', 1, '669999', 1.031),
        (118, 'ขยะรีไซเคิล', 'พลาสติก', 'ท่อพีวีซีรวม', 'Other PVC Pipes', 'กิโลกรัม', 'Kilogram', 1, '1d8079', 1.031),
        (119, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกนิ่ม (PP)', 'PP Soft Plastic Cup', 'กิโลกรัม', 'Kilogram', 1, '2fa38b', 1.031),
        (120, 'ขยะรีไซเคิล', 'พลาสติก', 'แก้วพลาสติกรวม (PP PS BIO)', 'Other Plastic Cup', 'กิโลกรัม', 'Kilogram', 1, '35b89d', 1.031),
        (121, 'ขยะทั่วไป', 'พลาสติกปนเปื้อน', 'เม็ดพลาสติกปนเปื้อน (PS)', 'PS Pellets Contaminate', 'กิโลกรัม', 'Kilogram', 1, '38c9ac', 1.031),
        (122, 'ขยะทั่วไป', 'พลาสติกปนเปื้อน', 'เม็ดพลาสติกปนเปื้อน (PP)', 'PP Pellets Contaminate', 'กิโลกรัม', 'Kilogram', 1, '3bdbbb', 1.031),
        (123, 'ขยะรีไซเคิล', 'พลาสติก', 'เกล็ดโม่ (PP)', 'PP Flakes', 'กิโลกรัม', 'Kilogram', 1, '3febc8', 1.031),
        (124, 'ขยะรีไซเคิล', 'พลาสติก', 'ถังน้ำมันพลาสติกเปล่า 20 ลิตร (HDPE)', 'HDPE Oil container', 'ถัง', 'Price per gallon', 1.5, '42fcd6', 1.031),
        (125, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงบิ๊กแบ็ก (ตัดปาก)', 'Big Bags Wide', 'ใบ', 'Price per bag', 3, '08997b', 1.031),
        (126, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงบิ๊กแบ็ก (ไม่ตัดปาก)', 'Big Bags Narrow', 'ใบ', 'Price per bag', 3, '0bbf9b', 1.031),
        (127, 'ขยะรีไซเคิล', 'พลาสติก', 'เศษก้อน (PS)', 'PS Lumps', 'กิโลกรัม', 'Kilogram', 1, '0ccfa8', 1.031),
        (128, 'ขยะรีไซเคิล', 'พลาสติก', 'เศษก้อน (PP)', 'PP Lumps', 'กิโลกรัม', 'Kilogram', 1, '0bdeb4', 1.031),
        (129, 'ขยะรีไซเคิล', 'กระดาษ', 'แกนกระดาษ', 'Paper Cores', 'กิโลกรัม', 'Kilogram', 1, '4c9404', 5.674),
        (130, 'ขยะรีไซเคิล', 'กระดาษ', 'ถุงกระสอบเคลือบกระดาษ', 'Multiwall Paper Sacks', 'กิโลกรัม', 'Kilogram', 1, '5cb504', 5.674),
        (131, 'ขยะรีไซเคิล', 'โลหะ', 'กระป๋องเหล็ก', 'Metal Cans', 'กิโลกรัม', 'Kilogram', 1, 'a89676', 1.832),
        (132, 'ขยะรีไซเคิล', 'โลหะ', 'เศษขี้กลึงเหล็ก', 'Steel Turning Scrap', 'กิโลกรัม', 'Kilogram', 1, 'b2cc5c', 1.832),
        (133, 'ขยะรีไซเคิล', 'โลหะ', 'เศษเหล็กรวม', 'Steel Scrap', 'กิโลกรัม', 'Kilogram', 1, 'bfdb63', 1.832),
        (134, 'ขยะก่อสร้าง', 'โลหะ', 'ถังน้ำมันเหล็กเปล่า 200 ลิตร ถังใหม่', 'Metal Oil Container 200 liter (New Bucket)', 'ถัง', 'Bucket', 18, '9ab837', 1.832),
        (135, 'ขยะก่อสร้าง', 'โลหะ', 'ถังน้ำมันเหล็กเปล่า 200 ลิตร ถังเก่า', 'Metal Oil Container 200 liter (Old Bucket)', 'ถัง', 'Bucket', 18, 'afd13f', 1.832),
        (136, 'ขยะรีไซเคิล', 'โลหะ', 'เศษอลูมิเนียม', 'Aluminium Scrap', 'กิโลกรัม', 'Kilogram', 1, '77b577', 9.127),
        (137, 'ขยะรีไซเคิล', 'ไม้', 'เศษไม้พาเลท', 'Pallet wood chips', 'กิโลกรัม', 'Kilogram', 1, '6a996d', 0.854),
        (138, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ยางรถ 6 ล้อ', 'Six wheel car tires', 'เส้น', 'Price per line', 40, 'ad4db8', 0),
        (139, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ยางรถยนต์', 'Car tires', 'เส้น', 'Price per line', 15, 'c747d6', 0),
        (140, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ยางรถโฟล์คลิฟท์', 'Forklift car tires', 'เส้น', 'Price per line', 17, 'ea3bff', 0),
        (141, 'ขยะรีไซเคิล', 'อื่นๆ', 'หงส์ทอง ลัง 12 ขวด', 'Hong Thong (12 bottle Carton)', 'ลัง', 'Carton', 4.2, 'b3e3bc', 0.276),
        (142, 'ขยะรีไซเคิล', 'ไม้', 'ไม้พาเลท', 'Pallet wood', 'กิโลกรัม', 'Kilogram', 1, 'cc9266', 0),
        (143, 'ขยะอันตราย', 'หลอดไฟและสเปรย์', 'กระป๋องสเปรย์', 'Aerosol cans', 'กิโลกรัม', 'Kilogram', 1, '8c0500', 0),
        (144, 'ขยะอันตราย', 'เคมีและของเหลว', 'ภาชนะปนเปื้อน', 'Contaminated containers', 'กิโลกรัม', 'Kilogram', 1, 'b30802', 0),
        (145, 'ขยะอิเล็กทรอนิกส์', 'สายไฟ', 'สายโฮส', 'Hose line', 'กิโลกรัม', 'Kilogram', 1, 'd10902', 0),
        (146, 'ขยะรีไซเคิล', 'อื่นๆ', 'อุปกรณ์สำนักงาน', 'Office supplies', 'กิโลกรัม', 'Kilogram', 1, 'ed0a02', 0),
        (147, 'ขยะอันตราย', 'เคมีและของเหลว', 'วัสดุปนเปื้อน', 'Contaminated fabric', 'กิโลกรัม', 'Kilogram', 1, '800703', 0),
        (148, 'ขยะอันตราย', 'เคมีและของเหลว', 'ขี้เลื่อยปนเปื้อนน้ำมัน', 'Sawdust contaminated with oil', 'กิโลกรัม', 'Kilogram', 1, '660300', 0),
        (149, 'ขยะรีไซเคิล', 'อื่นๆ', 'แสงโสม ลัง 12 ขวด', 'Sang Som (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '84ab8b', 0.276),
        (150, 'ขยะรีไซเคิล', 'พลาสติก', 'ฟิล์มยืด', 'Stretch Film', 'กิโลกรัม', 'Kilogram', 1, '49786d', 1.031),

        -- Continue with materials 151-200
        (151, 'ขยะรีไซเคิล', 'พลาสติก', 'สายรัดพลาสติก (PET)', 'Plastic Strap (PET)', 'กิโลกรัม', 'Kilogram', 1, '808080', 1.031),
        (152, 'ขยะรีไซเคิล', 'พลาสติก', 'สายรัดพลาสติก (PP)', 'Plastic Strap (PP)', 'กิโลกรัม', 'Kilogram', 1, '69857e', 1.031),
        (153, 'ขยะรีไซเคิล', 'โลหะ', 'ปี๊บ', 'Bucket Steel', 'กิโลกรัม', 'Kilogram', 1, 'ccccab', 1.832),
        (154, 'ขยะรีไซเคิล', 'โลหะ', 'กระป๋องสเปรย์ (รีไซเคิล)', 'Aerosol Cans (Recycle)', 'กิโลกรัม', 'Kilogram', 1, '828267', 1.832),
        (155, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'โฟม (เผากำจัด)', 'Foam (Inceneration)', 'กิโลกรัม', 'Kilogram', 1, '6d90c7', 0),
        (156, 'ขยะรีไซเคิล', 'พลาสติก', 'โฟม', 'Foam (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, 'f09a59', 0),
        (157, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ถุงพลาสติก (เผากำจัด)', 'Plastic Bag (Inceneration)', 'กิโลกรัม', 'Kilogram', 1, '728581', 0),
        (158, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงพลาสติก', 'Plastic Bag (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, '95a8c4', 0),
        (159, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงขนม / ซองอ่อนหลายชั้น', 'Multilayer packaging (Waste to energy)', 'กิโลกรัม', 'Kilogram', 1, 'd9baa3', 0),
        (160, 'ขยะทั่วไป', 'วัสดุเผาทำเชื้อเพลิง', 'ถุงขนม / ซองอ่อนหลายชั้น (เผากำจัด)', 'Multilayer packaging (Inceneration)', 'กิโลกรัม', 'Kilogram', 1, '98a3a1', 0),
        (186, 'ขยะทั่วไป', 'ขยะทั่วไป', 'ขยะฝังกลบ', 'Waste to Landfill', 'กิโลกรัม', 'Kilogram', 1, '3269bf', 0),
        (187, 'ขยะทางการแพทย์/ติดเชื้อ', 'ของใช้ส่วนตัว', 'ผ้าอนามัย', 'Sanitary napkin', 'กิโลกรัม', 'Kilogram', 1, 'bd6073', 0),
        (188, 'ขยะทางการแพทย์/ติดเชื้อ', 'ของใช้ส่วนตัว', 'หน้ากากอนามัย', 'Face mask', 'กิโลกรัม', 'Kilogram', 1, 'e899a9', 0),
        (189, 'ขยะรีไซเคิล', 'พลาสติก', 'เชือก PP/PE', 'PP/PE Rope', 'กิโลกรัม', 'Kilogram', 1, '7dd1bf', 1.031),
        (190, 'ขยะรีไซเคิล', 'พลาสติก', 'ตาข่าย HDPE', 'HDPE Net', 'กิโลกรัม', 'Kilogram', 1, '9dc7be', 1.031),
        (191, 'ขยะรีไซเคิล', 'พลาสติก', 'ตาข่าย Nylon', 'Nylon Net', 'กิโลกรัม', 'Kilogram', 1, 'a2bdb7', 1.031),
        (192, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วสีรวม (รีไซเคิลทางเลือก)', 'Mixed Glass (Recycling Alternative)', 'กิโลกรัม', 'Kilogram', 1, '3a6642', 0.276),
        (193, 'ขยะอันตราย', 'แบตเตอรี่', 'แบตเตอรี่ วิทยุสื่อสาร', 'Walkie Talkie Battery', 'กิโลกรัม', 'Kilogram', 1, 'b37244', 0),
        (194, 'ขยะก่อสร้าง', 'โลหะ', 'ล้อแม็กซ์', 'Max Wheel (Aluminium Alloy)', 'กิโลกรัม', 'Kilogram', 1, '8da18d', 9.127),
        (195, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกดำ', 'Black Plastic', 'กิโลกรัม', 'Kilogram', 1, '7bedd3', 1.031),
        (196, 'ขยะอันตราย', 'แบตเตอรี่', 'แบตเตอรี่รถยนต์และมอเตอร์ไซค์', 'Automotive Battery', 'กิโลกรัม', 'Kilogram', 1, '825738', 0),
        (197, 'ขยะรีไซเคิล', 'พลาสติก', 'เศษผงพลาสติก (PP)', 'PP Plastic Powder', 'กิโลกรัม', 'Kilogram', 1, 'b6ccc7', 1.031),
        (198, 'ขยะรีไซเคิล', 'โลหะ', 'หม้อน้ำอลูมิเนียม', 'Aluminium Radiator', 'กิโลกรัม', 'Kilogram', 1, '6a8a6a', 9.127),
        (199, 'ขยะรีไซเคิล', 'โลหะ', 'หม้อน้ำทองแดง', 'Copper Radiator', 'กิโลกรัม', 'Kilogram', 1, '9cbf1d', 1.832),
        (200, 'ขยะรีไซเคิล', 'โลหะ', 'อลูมิเนียมฉาก', 'Aluminum Angle', 'กิโลกรัม', 'Kilogram', 1, '4b7d4b', 9.127),

        -- Continue with materials 201-226
        (201, 'ขยะรีไซเคิล', 'พลาสติก', 'ตาข่ายรวม (PE PP Nylon)', 'Fishing Net', 'กิโลกรัม', 'Kilogram', 1, '5bc7b1', 1.031),
        (202, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วรวม ลัง 12 ขวด', 'Colored Glass (12 bottle Carton)', 'ลัง', 'Carton', 4.2, '4bad5e', 0.276),
        (203, 'ขยะรีไซเคิล', 'แก้ว', 'ขวดแก้วรวม ขวดเล็ก ลัง 24 ขวด', 'Colored Glass 320ml (24 bottle carton)', 'ลัง', 'Carton', 7, '5cc470', 0.276),
        (204, 'ขยะรีไซเคิล', 'อื่นๆ', 'เศษผ้า', 'Contaminated Fabric', 'กิโลกรัม', 'Kilogram', 1, 'a88f7d', 0),
        (205, 'ขยะรีไซเคิล', 'พลาสติก', 'พลาสติกรวม', 'Other plastic (Waste to Energy)', 'กิโลกรัม', 'Kilogram', 1, 'ebd8ca', 0),
        (206, 'ขยะอันตราย', 'เคมีและของเหลว', 'สารเคมีอันตราย', 'Hazardous Chemicals', 'กิโลกรัม', 'Kilogram', 1, '66391a', 0),
        (207, 'ขยะอันตราย', 'เคมีและของเหลว', 'น้ำมันหล่อลื่น', 'Lubricant Oil', 'กิโลกรัม', 'Kilogram', 1, 'b0896f', 0),
        (208, 'ขยะอิเล็กทรอนิกส์', 'อุปกรณ์คอมพิวเตอร์', 'ตลับหมึกจากเครื่องปริ้นท์', 'Ink cartridges from printers', 'กิโลกรัม', 'Kilogram', 1, 'dec3b1', 0),
        (209, 'ขยะอันตราย', 'เคมีและของเหลว', 'น้ำจากแอร์คอมเพลสเซอร์ปนเปื้อนน้ำมัน', 'Waste water from compressor', 'กิโลกรัม', 'Kilogram', 1, 'f7b68b', 0),
        (210, 'ขยะรีไซเคิล', 'พลาสติก', 'สายรัดพลาสติกรวม (PET PP HDPE)', 'Plastic Strap (PET PP HDPE)', 'กิโลกรัม', 'Kilogram', 1, '486660', 1.031),
        (211, 'ขยะรีไซเคิล', 'โลหะ', 'ถังโลหะ', 'Metal Bucket', 'กิโลกรัม', 'Kilogram', 1, 'c5f522', 1.832),
        (212, 'ขยะรีไซเคิล', 'โลหะ', 'ถังเหล็กเปล่า 210 ลิตร', 'Steel Container 210 liter', 'กิโลกรัม', 'Kilogram', 1, '749406', 1.832),
        (213, 'ขยะรีไซเคิล', 'ไม้', 'ไม้พาเลท', 'Wood Pallet', 'กิโลกรัม', 'Kilogram', 1, '5bb07c', 0.854),
        (214, 'ขยะรีไซเคิล', 'พลาสติก', 'พาเลทพลาสติกรวม (HDPE PP)', 'Other Plastic Pallet (HDPE PP)', 'กิโลกรัม', 'Kilogram', 1, '73807d', 1.031),
        (215, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'เนยและชีสเสื่อมสภาพ น้ำมันพืช น้ำมัน Stearin', 'Decay Butter and Cheese, Vegetable Cooking Oil, Stearin Oil', 'กิโลกรัม', 'Kilogram', 1, '808080', 0.465),
        (216, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'แป้งเสื่อมสภาพ', 'Starch is not of good quality', 'กิโลกรัม', 'Kilogram', 1, '29d936', 0.465),
        (217, 'ขยะรีไซเคิล', 'อื่นๆ', 'เรซิ่น กรองน้ำ', 'Resin filter', 'กิโลกรัม', 'Kilogram', 1, '9abef5', 0),
        (218, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'กากตะกอนไขมัน', 'Fat Sludge', 'กิโลกรัม', 'Kilogram', 1, 'b1fab7', 0.465),
        (219, 'ขยะอินทรีย์', 'ของเหลวและตะกอน', 'กากตะกอนจากระบบบำบัดน้ำเสีย', 'Sludge from the wastewater treatment system', 'กิโลกรัม', 'Kilogram', 1, '073d0c', 0.465),
        (220, 'ขยะก่อสร้าง', 'วัสดุก่อสร้าง', 'วัสดุกรองน้ำ (หินกรวด)', 'Water filter material (Gravel Stones)', 'กิโลกรัม', 'Kilogram', 1, '7d92b3', 0),
        (221, 'ขยะรีไซเคิล', 'พลาสติก', 'โพลีคาร์บอเนต', 'Polycarbonate', 'กิโลกรัม', 'Kilogram', 1, '12c48f', 1.031),
        (222, 'ขยะรีไซเคิล', 'พลาสติก', 'เชือกโพลีเอสเตอร์', 'Polyester Rope', 'กิโลกรัม', 'Kilogram', 1, '00ffb3', 1.031),
        (223, 'ขยะรีไซเคิล', 'พลาสติก', 'แฟ้ม', 'Document Folder', 'กิโลกรัม', 'Kilogram', 1, 'b2f551', 5.674),
        (224, 'ขยะรีไซเคิล', 'กระดาษ', 'กระดาษเคลือบมัน', 'Coated Paper', 'กิโลกรัม', 'Kilogram', 1, 'caff7d', 5.674),
        (225, 'ขยะรีไซเคิล', 'พลาสติก', 'ถุงกระสอบ', 'Paper Sack Bag', 'กิโลกรัม', 'Kilogram', 1, '9cab85', 5.674),
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
WHERE NOT EXISTS (
    SELECT 1 FROM materials WHERE migration_id = mat_data.migration_id
);

-- ======================================
-- VERIFICATION AND COMPLETION
-- ======================================

DO $$
DECLARE
    total_materials INTEGER;
    materials_with_migration_id INTEGER;
    new_materials_added INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_materials FROM materials WHERE is_active = true;
    SELECT COUNT(*) INTO materials_with_migration_id FROM materials WHERE migration_id IS NOT NULL;

    -- Calculate how many new materials were added in this migration
    SELECT COUNT(*) INTO new_materials_added FROM materials
    WHERE migration_id >= 99 AND migration_id <= 311;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'COMPLETE MATERIALS MIGRATION FINISHED';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Total materials in database: %', total_materials;
    RAISE NOTICE 'Materials with migration_id: %', materials_with_migration_id;
    RAISE NOTICE 'New materials added (99-311): %', new_materials_added;
    RAISE NOTICE 'Expected total from CSV: 261';

    IF materials_with_migration_id >= 261 THEN
        RAISE NOTICE '✅ MIGRATION COMPLETE - All CSV materials migrated!';
    ELSE
        RAISE NOTICE '⚠️  MIGRATION INCOMPLETE - Missing materials: %', (261 - materials_with_migration_id);
    END IF;
    RAISE NOTICE '============================================';
END $$;