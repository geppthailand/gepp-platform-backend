-- ============================================================
-- ESG Seed Data: Categories, Subcategories, and Datapoints
-- Focus: E pillar - Carbon Scope 3 (all 15 GHG Protocol categories)
-- Also includes stub categories for Scope 1, Scope 2, S, and G pillars
-- ============================================================

-- ==========================================
-- E PILLAR CATEGORIES
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order) VALUES
('E', 'Carbon Emissions Scope 1', 'การปล่อยก๊าซเรือนกระจก ขอบเขตที่ 1', 'Direct GHG emissions from owned or controlled sources', 1),
('E', 'Carbon Emissions Scope 2', 'การปล่อยก๊าซเรือนกระจก ขอบเขตที่ 2', 'Indirect GHG emissions from purchased energy', 2),
('E', 'Carbon Emissions Scope 3', 'การปล่อยก๊าซเรือนกระจก ขอบเขตที่ 3', 'All other indirect GHG emissions in the value chain', 3),
('E', 'Water Management', 'การจัดการน้ำ', 'Water consumption, discharge, and stewardship', 4),
('E', 'Waste Management', 'การจัดการของเสีย', 'Waste generation, treatment, and circular economy', 5),
('E', 'Energy Management', 'การจัดการพลังงาน', 'Energy consumption and efficiency', 6),
('E', 'Biodiversity', 'ความหลากหลายทางชีวภาพ', 'Impact on ecosystems and biodiversity', 7),
('E', 'Air Quality & Pollution', 'คุณภาพอากาศและมลพิษ', 'Air pollutants, noise, and other pollution', 8);

-- ==========================================
-- S PILLAR CATEGORIES (stubs)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order) VALUES
('S', 'Labor Practices', 'แนวปฏิบัติด้านแรงงาน', 'Employment practices, wages, and working conditions', 1),
('S', 'Health & Safety', 'สุขภาพและความปลอดภัย', 'Occupational health and safety management', 2),
('S', 'Human Rights', 'สิทธิมนุษยชน', 'Human rights due diligence and assessment', 3),
('S', 'Community Engagement', 'การมีส่วนร่วมของชุมชน', 'Local community impact and engagement', 4),
('S', 'Diversity & Inclusion', 'ความหลากหลายและการรวมกลุ่ม', 'Diversity, equity, and inclusion initiatives', 5),
('S', 'Training & Development', 'การฝึกอบรมและการพัฒนา', 'Employee training and career development', 6),
('S', 'Supply Chain Social', 'ห่วงโซ่อุปทานด้านสังคม', 'Social assessment of suppliers', 7);

-- ==========================================
-- G PILLAR CATEGORIES (stubs)
-- ==========================================

INSERT INTO esg_data_category (pillar, name, name_th, description, sort_order) VALUES
('G', 'Board & Governance Structure', 'โครงสร้างคณะกรรมการและการกำกับดูแล', 'Board composition, independence, and governance', 1),
('G', 'Anti-Corruption', 'การต่อต้านการทุจริต', 'Anti-corruption policies and training', 2),
('G', 'Risk Management', 'การจัดการความเสี่ยง', 'Enterprise risk management framework', 3),
('G', 'Compliance', 'การปฏิบัติตามกฎหมาย', 'Regulatory compliance and legal matters', 4),
('G', 'Ethics & Transparency', 'จริยธรรมและความโปร่งใส', 'Code of conduct, ethics, and disclosure', 5),
('G', 'Data Privacy & Security', 'ความเป็นส่วนตัวและความปลอดภัยของข้อมูล', 'Data protection and cybersecurity', 6);

-- ==========================================
-- SCOPE 1 SUBCATEGORIES (stubs with basic datapoints)
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Stationary Combustion', 'การเผาไหม้แบบอยู่กับที่', 'Emissions from stationary sources like boilers and furnaces', 1
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 1';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Mobile Combustion', 'การเผาไหม้เคลื่อนที่', 'Emissions from company-owned vehicles', 2
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 1';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Fugitive Emissions', 'การปล่อยมลพิษแบบรั่วไหล', 'Refrigerant leaks, gas leaks', 3
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 1';

-- ==========================================
-- SCOPE 2 SUBCATEGORIES (stubs)
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Purchased Electricity', 'ไฟฟ้าที่ซื้อ', 'Emissions from purchased electricity consumption', 1
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 2';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Purchased Heat & Steam', 'ความร้อนและไอน้ำที่ซื้อ', 'Emissions from purchased heating, cooling, and steam', 2
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 2';

-- ==========================================
-- SCOPE 3 SUBCATEGORIES (all 15 GHG Protocol categories)
-- ==========================================

-- Get the Scope 3 category ID for all subcategory inserts
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 1: Purchased Goods and Services', 'หมวด 1: สินค้าและบริการที่จัดซื้อ', 'Extraction, production, and transportation of goods and services purchased by the reporting company', 1
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 2: Capital Goods', 'หมวด 2: สินค้าทุน', 'Extraction, production, and transportation of capital goods purchased by the reporting company', 2
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 3: Fuel and Energy Related Activities', 'หมวด 3: กิจกรรมที่เกี่ยวข้องกับเชื้อเพลิงและพลังงาน', 'Upstream emissions of purchased fuels and electricity not included in Scope 1 or 2', 3
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 4: Upstream Transportation and Distribution', 'หมวด 4: การขนส่งและการกระจายสินค้าต้นน้ำ', 'Transportation and distribution of products purchased between tier 1 suppliers and own operations', 4
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 5: Waste Generated in Operations', 'หมวด 5: ของเสียที่เกิดจากการดำเนินงาน', 'Disposal and treatment of waste generated in company operations', 5
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 6: Business Travel', 'หมวด 6: การเดินทางเพื่อธุรกิจ', 'Transportation of employees for business-related activities', 6
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 7: Employee Commuting', 'หมวด 7: การเดินทางของพนักงาน', 'Transportation of employees between homes and worksites', 7
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 8: Upstream Leased Assets', 'หมวด 8: สินทรัพย์เช่าต้นน้ำ', 'Emissions from operation of assets leased by the reporting company', 8
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 9: Downstream Transportation and Distribution', 'หมวด 9: การขนส่งและการกระจายสินค้าปลายน้ำ', 'Transportation and distribution of products sold between operations and end consumer', 9
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 10: Processing of Sold Products', 'หมวด 10: การแปรรูปผลิตภัณฑ์ที่ขาย', 'Processing of intermediate products sold by downstream companies', 10
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 11: Use of Sold Products', 'หมวด 11: การใช้ผลิตภัณฑ์ที่ขาย', 'End use of goods and services sold by the reporting company', 11
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 12: End-of-Life Treatment of Sold Products', 'หมวด 12: การจัดการปลายทางของผลิตภัณฑ์ที่ขาย', 'Waste disposal and treatment of products sold at end of life', 12
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 13: Downstream Leased Assets', 'หมวด 13: สินทรัพย์เช่าปลายน้ำ', 'Emissions from operation of assets owned and leased to other entities', 13
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 14: Franchises', 'หมวด 14: แฟรนไชส์', 'Emissions from operation of franchises not included in Scope 1 and 2', 14
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, 'Category 15: Investments', 'หมวด 15: การลงทุน', 'Emissions associated with the reporting company investments', 15
FROM esg_data_category WHERE name = 'Carbon Emissions Scope 3';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 1: Purchased Goods and Services
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Total procurement spend', 'ยอดจัดซื้อรวม', 'Total monetary value of purchased goods and services', 'THB', 'numeric', 1),
    ('Supplier name', 'ชื่อผู้จัดจำหน่าย', 'Name of the supplier or vendor', NULL, 'text', 2),
    ('Product/service category', 'ประเภทสินค้า/บริการ', 'Category of the purchased good or service', NULL, 'text', 3),
    ('Product weight', 'น้ำหนักสินค้า', 'Weight of purchased products', 'kg', 'numeric', 4),
    ('Quantity purchased', 'จำนวนที่ซื้อ', 'Number of units purchased', 'units', 'numeric', 5),
    ('Emission factor used', 'ค่าสัมประสิทธิ์การปล่อย', 'Emission factor applied for calculation', 'kgCO2e/unit', 'numeric', 6),
    ('Supplier country of origin', 'ประเทศต้นทางของผู้จัดจำหน่าย', 'Country where the supplier operates', NULL, 'text', 7),
    ('Purchase date', 'วันที่จัดซื้อ', 'Date of purchase transaction', NULL, 'date', 8),
    ('Invoice/receipt number', 'เลขที่ใบแจ้งหนี้/ใบเสร็จ', 'Reference number from invoice or receipt', NULL, 'text', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 1: Purchased Goods and Services';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 2: Capital Goods
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Asset type', 'ประเภทสินทรัพย์', 'Type of capital asset (machinery, building, vehicle, IT equipment)', NULL, 'text', 1),
    ('Purchase value', 'มูลค่าจัดซื้อ', 'Monetary value of the capital good', 'THB', 'numeric', 2),
    ('Asset weight', 'น้ำหนักสินทรัพย์', 'Weight of the capital good', 'kg', 'numeric', 3),
    ('Manufacturer/supplier', 'ผู้ผลิต/ผู้จัดจำหน่าย', 'Manufacturer or supplier name', NULL, 'text', 4),
    ('Expected lifetime', 'อายุการใช้งานที่คาดหวัง', 'Expected useful life of the asset', 'years', 'numeric', 5),
    ('Estimated lifecycle emissions', 'การปล่อยก๊าซตลอดวงจรชีวิตโดยประมาณ', 'Estimated total lifecycle GHG emissions', 'kgCO2e', 'numeric', 6),
    ('Purchase date', 'วันที่จัดซื้อ', 'Date of capital good purchase', NULL, 'date', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 2: Capital Goods';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 3: Fuel and Energy Related Activities
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Fuel type', 'ประเภทเชื้อเพลิง', 'Type of fuel (diesel, gasoline, LPG, natural gas)', NULL, 'text', 1),
    ('Fuel volume consumed', 'ปริมาณเชื้อเพลิงที่ใช้', 'Volume of fuel consumed', 'liters', 'numeric', 2),
    ('Fuel weight consumed', 'น้ำหนักเชื้อเพลิงที่ใช้', 'Weight of fuel consumed', 'kg', 'numeric', 3),
    ('Electricity consumed', 'ไฟฟ้าที่ใช้', 'Total electricity consumption', 'kWh', 'numeric', 4),
    ('Upstream emission factor', 'ค่าสัมประสิทธิ์ต้นน้ำ', 'Upstream emission factor for fuel extraction and processing', 'kgCO2e/unit', 'numeric', 5),
    ('Transmission & distribution losses', 'การสูญเสียจากการส่งและจำหน่าย', 'T&D losses from electricity delivery', 'kWh', 'numeric', 6),
    ('Fuel supplier', 'ผู้จัดจำหน่ายเชื้อเพลิง', 'Name of fuel supplier', NULL, 'text', 7),
    ('Billing period', 'ระยะเวลาเรียกเก็บ', 'Period covered by the fuel/energy bill', NULL, 'text', 8)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 3: Fuel and Energy Related Activities';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 4: Upstream Transportation and Distribution
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Transport mode', 'รูปแบบการขนส่ง', 'Mode of transport (road, rail, sea, air)', NULL, 'text', 1),
    ('Vehicle type', 'ประเภทยานพาหนะ', 'Type of vehicle (truck, van, ship, aircraft)', NULL, 'text', 2),
    ('Distance traveled', 'ระยะทางที่เดินทาง', 'Total distance of transportation', 'km', 'numeric', 3),
    ('Cargo weight', 'น้ำหนักสินค้า', 'Weight of goods transported', 'kg', 'numeric', 4),
    ('Fuel consumed', 'เชื้อเพลิงที่ใช้', 'Fuel consumed during transportation', 'liters', 'numeric', 5),
    ('Origin location', 'สถานที่ต้นทาง', 'Origin point of transportation', NULL, 'text', 6),
    ('Destination location', 'สถานที่ปลายทาง', 'Destination point of transportation', NULL, 'text', 7),
    ('Logistics provider', 'ผู้ให้บริการขนส่ง', 'Name of logistics or shipping company', NULL, 'text', 8),
    ('Shipping date', 'วันที่จัดส่ง', 'Date of shipment', NULL, 'date', 9),
    ('Waybill/tracking number', 'เลขที่ใบส่งสินค้า', 'Shipping document reference number', NULL, 'text', 10)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 4: Upstream Transportation and Distribution';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 5: Waste Generated in Operations
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Waste type', 'ประเภทของเสีย', 'Type of waste (general, organic, plastic, paper, glass, metal, electronic, hazardous)', NULL, 'text', 1),
    ('Waste category', 'หมวดของเสีย', 'Category of waste (municipal solid, industrial, construction)', NULL, 'text', 2),
    ('Waste weight', 'น้ำหนักของเสีย', 'Weight of waste generated', 'kg', 'numeric', 3),
    ('Treatment method', 'วิธีการจัดการ', 'Treatment method (landfill, incineration, recycling, composting, anaerobic digestion)', NULL, 'text', 4),
    ('Disposal vendor', 'ผู้ให้บริการกำจัด', 'Name of waste disposal company', NULL, 'text', 5),
    ('Disposal cost', 'ค่ากำจัด', 'Cost of waste disposal', 'THB', 'numeric', 6),
    ('Waste manifest number', 'เลขที่ใบกำกับของเสีย', 'Waste manifest or tracking number', NULL, 'text', 7),
    ('Waste origin location', 'สถานที่เกิดของเสีย', 'Location where waste was generated', NULL, 'text', 8),
    ('Record date', 'วันที่บันทึก', 'Date of waste record', NULL, 'date', 9),
    ('Recycled material output', 'ผลผลิตวัสดุรีไซเคิล', 'Weight of materials recovered through recycling', 'kg', 'numeric', 10),
    ('Hazardous waste classification', 'การจำแนกของเสียอันตราย', 'Classification code for hazardous waste', NULL, 'text', 11)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 5: Waste Generated in Operations';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 6: Business Travel
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Travel mode', 'รูปแบบการเดินทาง', 'Mode of travel (air, rail, road, taxi, ride-hailing)', NULL, 'text', 1),
    ('Travel class', 'ชั้นการเดินทาง', 'Class of travel (economy, business, first)', NULL, 'text', 2),
    ('Distance traveled', 'ระยะทาง', 'Total distance of the trip', 'km', 'numeric', 3),
    ('Trip origin', 'ต้นทาง', 'Origin city/airport', NULL, 'text', 4),
    ('Trip destination', 'ปลายทาง', 'Destination city/airport', NULL, 'text', 5),
    ('Number of passengers', 'จำนวนผู้โดยสาร', 'Number of employees on the trip', 'persons', 'numeric', 6),
    ('Trip count', 'จำนวนเที่ยว', 'Number of trips (round trip = 2)', 'trips', 'numeric', 7),
    ('Hotel nights', 'จำนวนคืนที่พัก', 'Number of hotel overnight stays', 'nights', 'numeric', 8),
    ('Travel date', 'วันที่เดินทาง', 'Date of travel', NULL, 'date', 9),
    ('Travel cost', 'ค่าเดินทาง', 'Cost of the trip', 'THB', 'numeric', 10),
    ('Booking reference', 'เลขที่จอง', 'Booking or ticket reference number', NULL, 'text', 11),
    ('Travel provider', 'ผู้ให้บริการ', 'Airline, taxi company, or travel service provider', NULL, 'text', 12)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 6: Business Travel';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 7: Employee Commuting
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Commute mode', 'รูปแบบการเดินทาง', 'Mode of commuting (car, motorcycle, bus, BTS/MRT, bicycle, walk)', NULL, 'text', 1),
    ('One-way distance', 'ระยะทางเที่ยวเดียว', 'One-way commuting distance per day', 'km', 'numeric', 2),
    ('Number of employees', 'จำนวนพนักงาน', 'Number of employees using this commute mode', 'persons', 'numeric', 3),
    ('Working days per year', 'วันทำงานต่อปี', 'Number of working days per year', 'days', 'numeric', 4),
    ('Work from home days', 'วันทำงานที่บ้าน', 'Number of work-from-home days per year', 'days', 'numeric', 5),
    ('Vehicle fuel type', 'ประเภทเชื้อเพลิง', 'Fuel type of commuting vehicle (gasoline, diesel, electric, hybrid)', NULL, 'text', 6),
    ('Vehicle fuel efficiency', 'อัตราการใช้เชื้อเพลิง', 'Fuel consumption rate of vehicle', 'km/liter', 'numeric', 7),
    ('Survey date', 'วันที่สำรวจ', 'Date of commuting survey', NULL, 'date', 8)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 7: Employee Commuting';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 8: Upstream Leased Assets
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Asset type', 'ประเภทสินทรัพย์', 'Type of leased asset (office, warehouse, vehicle, equipment)', NULL, 'text', 1),
    ('Leased area', 'พื้นที่เช่า', 'Area of the leased asset', 'sqm', 'numeric', 2),
    ('Energy consumption', 'การใช้พลังงาน', 'Energy consumed by the leased asset', 'kWh', 'numeric', 3),
    ('Lease period', 'ระยะเวลาเช่า', 'Duration of the lease', 'months', 'numeric', 4),
    ('Lessor name', 'ชื่อผู้ให้เช่า', 'Name of the lessor/owner', NULL, 'text', 5),
    ('Asset location', 'สถานที่ตั้ง', 'Location of the leased asset', NULL, 'text', 6),
    ('Monthly rent', 'ค่าเช่ารายเดือน', 'Monthly rental cost', 'THB', 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 8: Upstream Leased Assets';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 9: Downstream Transportation and Distribution
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Transport mode', 'รูปแบบการขนส่ง', 'Mode of transport for product delivery', NULL, 'text', 1),
    ('Distance to customer', 'ระยะทางถึงลูกค้า', 'Distance from operations to customer', 'km', 'numeric', 2),
    ('Product weight shipped', 'น้ำหนักสินค้าที่ส่ง', 'Weight of products shipped', 'kg', 'numeric', 3),
    ('Fuel consumed', 'เชื้อเพลิงที่ใช้', 'Fuel consumed for delivery', 'liters', 'numeric', 4),
    ('Delivery provider', 'ผู้ให้บริการจัดส่ง', 'Name of delivery/logistics company', NULL, 'text', 5),
    ('Delivery date', 'วันที่จัดส่ง', 'Date of delivery', NULL, 'date', 6),
    ('Number of deliveries', 'จำนวนการจัดส่ง', 'Number of delivery trips', 'trips', 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 9: Downstream Transportation and Distribution';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 10: Processing of Sold Products
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Product type', 'ประเภทผลิตภัณฑ์', 'Type of intermediate product sold for further processing', NULL, 'text', 1),
    ('Processing energy required', 'พลังงานที่ใช้ในการแปรรูป', 'Energy consumed during downstream processing', 'kWh', 'numeric', 2),
    ('Waste generated in processing', 'ของเสียจากการแปรรูป', 'Waste generated during downstream processing', 'kg', 'numeric', 3),
    ('Downstream processor name', 'ชื่อผู้แปรรูปปลายน้ำ', 'Name of the downstream processor', NULL, 'text', 4),
    ('Volume of products sold', 'ปริมาณผลิตภัณฑ์ที่ขาย', 'Volume or quantity of products sold for processing', 'units', 'numeric', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 10: Processing of Sold Products';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 11: Use of Sold Products
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Product type', 'ประเภทผลิตภัณฑ์', 'Type of product sold', NULL, 'text', 1),
    ('Energy per use', 'พลังงานต่อการใช้งาน', 'Energy consumed per use of the product', 'kWh', 'numeric', 2),
    ('Uses per lifetime', 'จำนวนการใช้งานตลอดอายุ', 'Number of uses during product lifetime', 'uses', 'numeric', 3),
    ('Product lifetime', 'อายุผลิตภัณฑ์', 'Expected useful lifetime of the product', 'years', 'numeric', 4),
    ('Units sold', 'จำนวนที่ขาย', 'Number of product units sold', 'units', 'numeric', 5),
    ('Direct emissions during use', 'การปล่อยโดยตรงระหว่างใช้งาน', 'Direct GHG emissions during product use (e.g., fuel combustion)', 'kgCO2e', 'numeric', 6),
    ('Fuel consumed during use', 'เชื้อเพลิงที่ใช้ระหว่างใช้งาน', 'Fuel consumed during product use', 'liters', 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 11: Use of Sold Products';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 12: End-of-Life Treatment of Sold Products
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Product type', 'ประเภทผลิตภัณฑ์', 'Type of product reaching end of life', NULL, 'text', 1),
    ('Product weight', 'น้ำหนักผลิตภัณฑ์', 'Weight of products at end of life', 'kg', 'numeric', 2),
    ('Material composition', 'องค์ประกอบวัสดุ', 'Material breakdown of the product (plastic, metal, etc.)', NULL, 'text', 3),
    ('Treatment method', 'วิธีการจัดการ', 'End-of-life treatment (landfill, recycling, incineration)', NULL, 'text', 4),
    ('Recycling rate', 'อัตราการรีไซเคิล', 'Percentage of product recycled', '%', 'numeric', 5),
    ('Units reaching end of life', 'จำนวนที่หมดอายุ', 'Number of units reaching end of life', 'units', 'numeric', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 12: End-of-Life Treatment of Sold Products';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 13: Downstream Leased Assets
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Asset type', 'ประเภทสินทรัพย์', 'Type of asset leased to others (office, retail, warehouse)', NULL, 'text', 1),
    ('Leased area', 'พื้นที่เช่า', 'Total area of leased assets', 'sqm', 'numeric', 2),
    ('Tenant energy consumption', 'การใช้พลังงานของผู้เช่า', 'Energy consumed by tenants', 'kWh', 'numeric', 3),
    ('Number of tenants', 'จำนวนผู้เช่า', 'Number of tenants occupying the asset', 'tenants', 'numeric', 4),
    ('Asset location', 'สถานที่ตั้ง', 'Location of the leased asset', NULL, 'text', 5),
    ('Building energy rating', 'ระดับพลังงานอาคาร', 'Energy efficiency rating of the building', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 13: Downstream Leased Assets';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 14: Franchises
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Number of franchises', 'จำนวนแฟรนไชส์', 'Total number of franchise outlets', 'outlets', 'numeric', 1),
    ('Average energy per franchise', 'พลังงานเฉลี่ยต่อแฟรนไชส์', 'Average annual energy consumption per franchise', 'kWh', 'numeric', 2),
    ('Average waste per franchise', 'ของเสียเฉลี่ยต่อแฟรนไชส์', 'Average annual waste generated per franchise', 'kg', 'numeric', 3),
    ('Average water per franchise', 'น้ำเฉลี่ยต่อแฟรนไชส์', 'Average annual water consumption per franchise', 'm3', 'numeric', 4),
    ('Franchise location', 'สถานที่ตั้งแฟรนไชส์', 'Location of franchise outlet', NULL, 'text', 5),
    ('Franchise area', 'พื้นที่แฟรนไชส์', 'Average floor area per franchise', 'sqm', 'numeric', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 14: Franchises';

-- ==========================================
-- SCOPE 3 DATAPOINTS - Category 15: Investments
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Investment type', 'ประเภทการลงทุน', 'Type of investment (equity, debt, project finance)', NULL, 'text', 1),
    ('Investment amount', 'จำนวนเงินลงทุน', 'Monetary value of the investment', 'THB', 'numeric', 2),
    ('Investee company/project', 'บริษัท/โครงการที่ลงทุน', 'Name of investee company or project', NULL, 'text', 3),
    ('Investment sector', 'ภาคที่ลงทุน', 'Sector of the investee (energy, manufacturing, real estate)', NULL, 'text', 4),
    ('Ownership share', 'สัดส่วนความเป็นเจ้าของ', 'Percentage of equity ownership', '%', 'numeric', 5),
    ('Financed emissions', 'การปล่อยก๊าซจากการลงทุน', 'GHG emissions attributable to the investment', 'tCO2e', 'numeric', 6),
    ('Investment date', 'วันที่ลงทุน', 'Date of investment', NULL, 'date', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 15: Investments';
