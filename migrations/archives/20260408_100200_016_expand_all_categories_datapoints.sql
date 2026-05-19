-- ============================================================
-- Comprehensive ESG Category Expansion
-- Adds datapoints for: Scope 1, Scope 2, E pillar (Water/Waste/Energy/Biodiversity/Air),
-- Financial datapoints for Scope 3, S pillar, G pillar
-- ============================================================

-- ==========================================
-- SCOPE 1 DATAPOINTS - Stationary Combustion
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Fuel type', 'ประเภทเชื้อเพลิง', 'Type of fuel used (diesel, natural gas, LPG, fuel oil, coal)', NULL, 'text', 1),
    ('Fuel quantity', 'ปริมาณเชื้อเพลิง', 'Quantity of fuel consumed', NULL, 'numeric', 2),
    ('Fuel unit', 'หน่วยเชื้อเพลิง', 'Unit of fuel measurement (liters, kg, m3, MMBtu)', NULL, 'text', 3),
    ('Equipment type', 'ประเภทอุปกรณ์', 'Type of stationary equipment (boiler, furnace, generator, heater)', NULL, 'text', 4),
    ('Operating hours', 'ชั่วโมงใช้งาน', 'Total operating hours during the period', 'hours', 'numeric', 5),
    ('Emission factor', 'ค่าสัมประสิทธิ์การปล่อย', 'Emission factor for the fuel type', 'kgCO2e/unit', 'numeric', 6),
    ('Total emissions', 'การปล่อยก๊าซรวม', 'Total GHG emissions from combustion', 'tCO2e', 'numeric', 7),
    ('Rate per unit', 'ราคาต่อหน่วย', 'Price per unit of fuel', NULL, 'numeric', 8),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total fuel cost', NULL, 'numeric', 9),
    ('Supplier name', 'ชื่อผู้จัดจำหน่าย', 'Fuel supplier name', NULL, 'text', 10),
    ('Billing period', 'รอบบิล', 'Period covered by the fuel bill', NULL, 'text', 11),
    ('Invoice reference', 'เลขที่ใบแจ้งหนี้', 'Invoice or receipt reference number', NULL, 'text', 12)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Stationary Combustion'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- SCOPE 1 DATAPOINTS - Mobile Combustion
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Vehicle type', 'ประเภทยานพาหนะ', 'Type of vehicle (car, truck, van, motorcycle, forklift)', NULL, 'text', 1),
    ('Fuel type', 'ประเภทเชื้อเพลิง', 'Fuel type (gasoline, diesel, LPG, CNG, electric)', NULL, 'text', 2),
    ('Fuel consumed', 'เชื้อเพลิงที่ใช้', 'Total fuel consumed', 'liters', 'numeric', 3),
    ('Distance traveled', 'ระยะทาง', 'Total distance traveled', 'km', 'numeric', 4),
    ('Vehicle count', 'จำนวนยานพาหนะ', 'Number of vehicles in fleet', 'units', 'numeric', 5),
    ('Emission factor', 'ค่าสัมประสิทธิ์การปล่อย', 'Emission factor for the fuel/vehicle type', 'kgCO2e/unit', 'numeric', 6),
    ('Total emissions', 'การปล่อยก๊าซรวม', 'Total GHG emissions from mobile combustion', 'tCO2e', 'numeric', 7),
    ('Rate per unit', 'ราคาต่อหน่วย', 'Fuel price per unit', NULL, 'numeric', 8),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total fuel cost', NULL, 'numeric', 9),
    ('License plate', 'ทะเบียนรถ', 'Vehicle license plate or fleet ID', NULL, 'text', 10),
    ('Record date', 'วันที่บันทึก', 'Date of fuel purchase or travel record', NULL, 'date', 11)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Mobile Combustion'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- SCOPE 1 DATAPOINTS - Fugitive Emissions
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Gas type', 'ประเภทก๊าซ', 'Type of fugitive gas (R-22, R-134a, R-410A, CO2, CH4, SF6)', NULL, 'text', 1),
    ('Refrigerant type', 'ประเภทสารทำความเย็น', 'Refrigerant classification and chemical name', NULL, 'text', 2),
    ('Equipment type', 'ประเภทอุปกรณ์', 'Type of equipment (AC unit, chiller, fire extinguisher, switchgear)', NULL, 'text', 3),
    ('Charge amount', 'ปริมาณสารทำความเย็นบรรจุ', 'Total refrigerant charge in equipment', 'kg', 'numeric', 4),
    ('Leak rate', 'อัตราการรั่วไหล', 'Estimated annual leak rate', '%', 'numeric', 5),
    ('Quantity leaked', 'ปริมาณที่รั่วไหล', 'Actual quantity of gas leaked or topped up', 'kg', 'numeric', 6),
    ('GWP', 'ศักยภาพภาวะโลกร้อน', 'Global Warming Potential of the gas', NULL, 'numeric', 7),
    ('Emission factor', 'ค่าสัมประสิทธิ์การปล่อย', 'Emission factor for the gas', 'tCO2e/kg', 'numeric', 8),
    ('Total emissions', 'การปล่อยก๊าซรวม', 'Total GHG emissions from fugitive releases', 'tCO2e', 'numeric', 9),
    ('Maintenance date', 'วันที่บำรุงรักษา', 'Date of maintenance or leak check', NULL, 'date', 10),
    ('Technician/vendor', 'ช่างเทคนิค/ผู้ให้บริการ', 'Service technician or vendor name', NULL, 'text', 11),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total cost of refrigerant recharge or repair', NULL, 'numeric', 12)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Fugitive Emissions'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- SCOPE 2 DATAPOINTS - Purchased Electricity
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Electricity consumed', 'ไฟฟ้าที่ใช้', 'Total electricity consumption during the period', 'kWh', 'numeric', 1),
    ('Grid emission factor', 'ค่าสัมประสิทธิ์กริด', 'Grid emission factor used for calculation', 'kgCO2e/kWh', 'numeric', 2),
    ('Total emissions', 'การปล่อยก๊าซรวม', 'Total GHG emissions from purchased electricity', 'tCO2e', 'numeric', 3),
    ('Provider name', 'ชื่อผู้ให้บริการ', 'Electricity utility or provider name', NULL, 'text', 4),
    ('Rate per unit', 'อัตราค่าไฟ', 'Electricity rate per kWh', NULL, 'numeric', 5),
    ('Total cost', 'ค่าไฟรวม', 'Total electricity bill amount', NULL, 'numeric', 6),
    ('Renewable percentage', 'สัดส่วนพลังงานหมุนเวียน', 'Percentage of electricity from renewable sources', '%', 'numeric', 7),
    ('Meter number', 'หมายเลขมิเตอร์', 'Electricity meter reference number', NULL, 'text', 8),
    ('Billing period', 'รอบบิล', 'Billing period (e.g. Jan 2023, Q1 2023)', NULL, 'text', 9),
    ('Facility/location', 'สถานที่/สาขา', 'Facility or location consuming the electricity', NULL, 'text', 10),
    ('Invoice reference', 'เลขที่ใบแจ้งหนี้', 'Electricity bill reference number', NULL, 'text', 11)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Purchased Electricity'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- SCOPE 2 DATAPOINTS - Purchased Heat & Steam
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Energy type', 'ประเภทพลังงาน', 'Type of purchased energy (heating, cooling, steam)', NULL, 'text', 1),
    ('Energy consumed', 'พลังงานที่ใช้', 'Total energy consumed', 'kWh', 'numeric', 2),
    ('Emission factor', 'ค่าสัมประสิทธิ์การปล่อย', 'Emission factor for the energy source', 'kgCO2e/kWh', 'numeric', 3),
    ('Total emissions', 'การปล่อยก๊าซรวม', 'Total GHG emissions from purchased heat/steam', 'tCO2e', 'numeric', 4),
    ('Provider name', 'ชื่อผู้ให้บริการ', 'Energy provider name', NULL, 'text', 5),
    ('Rate per unit', 'อัตราค่าพลังงาน', 'Price per unit of energy', NULL, 'numeric', 6),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total energy cost', NULL, 'numeric', 7),
    ('Billing period', 'รอบบิล', 'Billing period covered', NULL, 'text', 8),
    ('Invoice reference', 'เลขที่ใบแจ้งหนี้', 'Invoice or receipt reference number', NULL, 'text', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Purchased Heat & Steam'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- E PILLAR - Water Management: Subcategories + Datapoints
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Water Withdrawal', 'การดึงน้ำ', 'Water drawn from various sources for use', 1),
    ('Water Discharge', 'การระบายน้ำ', 'Wastewater discharge and treatment', 2),
    ('Water Consumption', 'การใช้น้ำ', 'Net water consumption (withdrawal minus discharge)', 3)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Water Management'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Water source', 'แหล่งน้ำ', 'Source of water (municipal, groundwell, river, rainwater, recycled)', NULL, 'text', 1),
    ('Volume withdrawn', 'ปริมาณน้ำที่ดึง', 'Total volume of water withdrawn', 'm3', 'numeric', 2),
    ('Water quality', 'คุณภาพน้ำ', 'Quality of water (freshwater, brackish, seawater)', NULL, 'text', 3),
    ('Facility/location', 'สถานที่/สาขา', 'Facility drawing the water', NULL, 'text', 4),
    ('Rate per unit', 'อัตราค่าน้ำ', 'Water rate per cubic meter', NULL, 'numeric', 5),
    ('Total cost', 'ค่าน้ำรวม', 'Total water bill amount', NULL, 'numeric', 6),
    ('Meter number', 'หมายเลขมิเตอร์', 'Water meter reference number', NULL, 'text', 7),
    ('Billing period', 'รอบบิล', 'Billing period covered', NULL, 'text', 8),
    ('Invoice reference', 'เลขที่ใบแจ้งหนี้', 'Invoice or receipt reference number', NULL, 'text', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Water Withdrawal'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Discharge destination', 'จุดระบายน้ำ', 'Where wastewater is discharged (municipal sewer, water body, treatment plant)', NULL, 'text', 1),
    ('Volume discharged', 'ปริมาณน้ำที่ระบาย', 'Total volume of water discharged', 'm3', 'numeric', 2),
    ('Treatment method', 'วิธีการบำบัด', 'Wastewater treatment method applied', NULL, 'text', 3),
    ('BOD level', 'ค่า BOD', 'Biochemical Oxygen Demand of discharge', 'mg/L', 'numeric', 4),
    ('COD level', 'ค่า COD', 'Chemical Oxygen Demand of discharge', 'mg/L', 'numeric', 5),
    ('Treatment cost', 'ค่าบำบัดน้ำเสีย', 'Cost of wastewater treatment', NULL, 'numeric', 6),
    ('Record date', 'วันที่บันทึก', 'Date of discharge measurement or record', NULL, 'date', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Water Discharge'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Net water consumed', 'การใช้น้ำสุทธิ', 'Net water consumption (withdrawal minus discharge)', 'm3', 'numeric', 1),
    ('Water recycled', 'น้ำรีไซเคิล', 'Volume of water recycled or reused', 'm3', 'numeric', 2),
    ('Recycling rate', 'อัตราการรีไซเคิล', 'Percentage of water recycled', '%', 'numeric', 3),
    ('Water intensity', 'ปริมาณน้ำต่อหน่วยผลิต', 'Water consumption per unit of production or revenue', 'm3/unit', 'numeric', 4),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered by the consumption data', NULL, 'text', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Water Consumption'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- E PILLAR - Waste Management: Subcategories + Datapoints
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Hazardous Waste', 'ของเสียอันตราย', 'Generation and disposal of hazardous waste', 1),
    ('Non-Hazardous Waste', 'ของเสียไม่อันตราย', 'Generation and disposal of non-hazardous waste', 2),
    ('Waste Diversion & Recycling', 'การเบี่ยงเบนและรีไซเคิลของเสีย', 'Waste diverted from landfill through recycling, composting, etc.', 3)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Waste Management'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Waste type', 'ประเภทของเสีย', 'Type of hazardous waste', NULL, 'text', 1),
    ('Waste classification code', 'รหัสจำแนกของเสีย', 'Hazardous waste classification code', NULL, 'text', 2),
    ('Waste weight', 'น้ำหนักของเสีย', 'Weight of hazardous waste generated', 'kg', 'numeric', 3),
    ('Treatment method', 'วิธีการจัดการ', 'Treatment or disposal method', NULL, 'text', 4),
    ('Disposal vendor', 'ผู้ให้บริการกำจัด', 'Licensed waste disposal company name', NULL, 'text', 5),
    ('Disposal cost', 'ค่ากำจัด', 'Cost of hazardous waste disposal', NULL, 'numeric', 6),
    ('Waste manifest number', 'เลขที่ใบกำกับ', 'Waste manifest tracking number', NULL, 'text', 7),
    ('Record date', 'วันที่บันทึก', 'Date of waste generation or disposal', NULL, 'date', 8)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Hazardous Waste'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Waste type', 'ประเภทของเสีย', 'Type of non-hazardous waste (general, organic, paper, plastic, glass, metal)', NULL, 'text', 1),
    ('Waste weight', 'น้ำหนักของเสีย', 'Weight of non-hazardous waste generated', 'kg', 'numeric', 2),
    ('Treatment method', 'วิธีการจัดการ', 'Treatment method (landfill, incineration, recycling, composting)', NULL, 'text', 3),
    ('Disposal vendor', 'ผู้ให้บริการกำจัด', 'Waste collection or disposal company name', NULL, 'text', 4),
    ('Disposal cost', 'ค่ากำจัด', 'Cost of waste disposal', NULL, 'numeric', 5),
    ('Origin location', 'สถานที่เกิดของเสีย', 'Location where waste was generated', NULL, 'text', 6),
    ('Record date', 'วันที่บันทึก', 'Date of waste record', NULL, 'date', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Non-Hazardous Waste'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Material type', 'ประเภทวัสดุ', 'Type of material diverted (paper, plastic, metal, glass, organic)', NULL, 'text', 1),
    ('Weight diverted', 'น้ำหนักที่เบี่ยงเบน', 'Weight of waste diverted from disposal', 'kg', 'numeric', 2),
    ('Diversion method', 'วิธีการเบี่ยงเบน', 'Method of diversion (recycling, composting, reuse, donation)', NULL, 'text', 3),
    ('Diversion rate', 'อัตราการเบี่ยงเบน', 'Percentage of total waste diverted', '%', 'numeric', 4),
    ('Revenue from recycling', 'รายได้จากรีไซเคิล', 'Revenue earned from selling recyclable materials', NULL, 'numeric', 5),
    ('Recycling partner', 'คู่ค้ารีไซเคิล', 'Name of recycling partner or buyer', NULL, 'text', 6),
    ('Record date', 'วันที่บันทึก', 'Date of diversion record', NULL, 'date', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Waste Diversion & Recycling'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- E PILLAR - Energy Management: Subcategories + Datapoints
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Energy Consumption', 'การใช้พลังงาน', 'Total energy consumption across all sources', 1),
    ('Renewable Energy', 'พลังงานหมุนเวียน', 'Generation and procurement of renewable energy', 2),
    ('Energy Efficiency', 'ประสิทธิภาพพลังงาน', 'Energy efficiency measures and improvements', 3)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Energy Management'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Energy source', 'แหล่งพลังงาน', 'Source of energy (electricity, diesel, natural gas, solar, etc.)', NULL, 'text', 1),
    ('Energy consumed', 'พลังงานที่ใช้', 'Total energy consumed', 'kWh', 'numeric', 2),
    ('Energy intensity', 'ปริมาณพลังงานต่อหน่วย', 'Energy consumption per unit of output or revenue', 'kWh/unit', 'numeric', 3),
    ('Facility/location', 'สถานที่/สาขา', 'Facility consuming the energy', NULL, 'text', 4),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total energy cost', NULL, 'numeric', 5),
    ('Billing period', 'รอบบิล', 'Period covered', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Energy Consumption'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Renewable source', 'แหล่งพลังงานหมุนเวียน', 'Type of renewable energy (solar, wind, biomass, hydro)', NULL, 'text', 1),
    ('Energy generated', 'พลังงานที่ผลิต', 'Total renewable energy generated on-site', 'kWh', 'numeric', 2),
    ('Energy purchased (REC)', 'พลังงานที่ซื้อ (REC)', 'Renewable energy certificates or green tariff purchased', 'kWh', 'numeric', 3),
    ('Renewable share', 'สัดส่วนพลังงานหมุนเวียน', 'Percentage of total energy from renewable sources', '%', 'numeric', 4),
    ('Installation capacity', 'กำลังการผลิตติดตั้ง', 'Installed renewable generation capacity', 'kW', 'numeric', 5),
    ('Investment cost', 'ค่าลงทุน', 'Capital investment in renewable energy', NULL, 'numeric', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Renewable Energy'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Initiative description', 'รายละเอียดโครงการ', 'Description of energy efficiency initiative', NULL, 'text', 1),
    ('Energy saved', 'พลังงานที่ประหยัด', 'Energy savings from the initiative', 'kWh', 'numeric', 2),
    ('Cost savings', 'ค่าใช้จ่ายที่ประหยัด', 'Monetary savings from energy efficiency', NULL, 'numeric', 3),
    ('Implementation date', 'วันที่ดำเนินการ', 'Date of implementation', NULL, 'date', 4),
    ('Investment cost', 'ค่าลงทุน', 'Investment in efficiency improvement', NULL, 'numeric', 5),
    ('Payback period', 'ระยะเวลาคืนทุน', 'Expected payback period', 'years', 'numeric', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Energy Efficiency'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- E PILLAR - Biodiversity: Subcategories + Datapoints
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Land Use & Impact', 'การใช้ที่ดินและผลกระทบ', 'Operational land use and impact on ecosystems', 1),
    ('Species & Habitat Protection', 'การปกป้องสายพันธุ์และถิ่นที่อยู่', 'Efforts to protect endangered species and habitats', 2)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Biodiversity'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Total operational area', 'พื้นที่ปฏิบัติการทั้งหมด', 'Total land area used for operations', 'hectares', 'numeric', 1),
    ('Protected area proximity', 'ความใกล้เคียงพื้นที่คุ้มครอง', 'Distance to nearest protected or high-biodiversity area', 'km', 'numeric', 2),
    ('Area restored', 'พื้นที่ที่ฟื้นฟู', 'Area of land restored or rehabilitated', 'hectares', 'numeric', 3),
    ('Land use type', 'ประเภทการใช้ที่ดิน', 'Type of land use (industrial, agricultural, office, natural)', NULL, 'text', 4),
    ('Assessment date', 'วันที่ประเมิน', 'Date of environmental impact assessment', NULL, 'date', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Land Use & Impact'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Species affected', 'สายพันธุ์ที่ได้รับผลกระทบ', 'Number of IUCN Red List species affected', 'species', 'numeric', 1),
    ('Conservation program', 'โปรแกรมอนุรักษ์', 'Description of biodiversity conservation program', NULL, 'text', 2),
    ('Conservation investment', 'เงินลงทุนอนุรักษ์', 'Investment in conservation activities', NULL, 'numeric', 3),
    ('Trees planted', 'จำนวนต้นไม้ที่ปลูก', 'Number of trees planted in reforestation programs', 'trees', 'numeric', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Species & Habitat Protection'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- E PILLAR - Air Quality & Pollution: Subcategories + Datapoints
-- ==========================================

INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'E', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Air Emissions', 'การปล่อยมลพิษทางอากาศ', 'Non-GHG air pollutant emissions (NOx, SOx, PM, VOCs)', 1),
    ('Noise & Other Pollution', 'เสียงและมลพิษอื่นๆ', 'Noise, light, and other forms of pollution', 2)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Air Quality & Pollution'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Pollutant type', 'ประเภทมลพิษ', 'Type of air pollutant (NOx, SOx, PM2.5, PM10, VOCs, CO)', NULL, 'text', 1),
    ('Emission quantity', 'ปริมาณการปล่อย', 'Quantity of pollutant emitted', 'kg', 'numeric', 2),
    ('Emission source', 'แหล่งกำเนิด', 'Source of emission (stack, fugitive, mobile)', NULL, 'text', 3),
    ('Measurement method', 'วิธีการวัด', 'Method used to measure (CEMS, stack test, calculation)', NULL, 'text', 4),
    ('Regulatory limit', 'ค่ามาตรฐาน', 'Applicable regulatory limit', 'mg/m3', 'numeric', 5),
    ('Measured concentration', 'ค่าที่วัดได้', 'Measured concentration of pollutant', 'mg/m3', 'numeric', 6),
    ('Monitoring date', 'วันที่ตรวจวัด', 'Date of emission monitoring', NULL, 'date', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Air Emissions'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Pollution type', 'ประเภทมลพิษ', 'Type of pollution (noise, light, vibration, odor)', NULL, 'text', 1),
    ('Measured level', 'ระดับที่วัดได้', 'Measured pollution level', NULL, 'numeric', 2),
    ('Measurement unit', 'หน่วยวัด', 'Unit of measurement (dB, lux, etc.)', NULL, 'text', 3),
    ('Regulatory limit', 'ค่ามาตรฐาน', 'Applicable regulatory limit', NULL, 'numeric', 4),
    ('Monitoring location', 'จุดตรวจวัด', 'Location where monitoring was performed', NULL, 'text', 5),
    ('Monitoring date', 'วันที่ตรวจวัด', 'Date of monitoring', NULL, 'date', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Noise & Other Pollution'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- SCOPE 3 - Add financial datapoints to categories missing them
-- Categories 3, 4, 7, 9, 11, 12, 13, 14
-- ==========================================

-- Category 3: Fuel and Energy Related Activities (add Rate per unit + Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Rate per unit', 'ราคาต่อหน่วย', 'Price per unit of fuel or energy', NULL, 'numeric', 9),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total fuel or energy cost', NULL, 'numeric', 10)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 3: Fuel and Energy Related Activities'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 4: Upstream Transportation (add Rate per unit + Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Rate per unit', 'ราคาต่อหน่วย', 'Transportation rate per unit/km', NULL, 'numeric', 11),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total transportation cost', NULL, 'numeric', 12)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 4: Upstream Transportation and Distribution'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 7: Employee Commuting (add Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total commuting subsidy or estimated cost', NULL, 'numeric', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 7: Employee Commuting'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 9: Downstream Transportation (add Rate per unit + Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Rate per unit', 'ราคาต่อหน่วย', 'Delivery rate per unit or per km', NULL, 'numeric', 8),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total delivery or logistics cost', NULL, 'numeric', 9)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 9: Downstream Transportation and Distribution'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 11: Use of Sold Products (add Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Revenue from product', 'รายได้จากผลิตภัณฑ์', 'Revenue generated from product sales', NULL, 'numeric', 8)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 11: Use of Sold Products'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 12: End-of-Life (add Treatment cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Treatment cost', 'ค่าจัดการปลายทาง', 'Cost of end-of-life treatment or disposal', NULL, 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 12: End-of-Life Treatment of Sold Products'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 13: Downstream Leased Assets (add Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Annual rental income', 'รายได้ค่าเช่าต่อปี', 'Annual rental income from leased assets', NULL, 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 13: Downstream Leased Assets'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Category 14: Franchises (add Total cost)
INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Total franchise revenue', 'รายได้แฟรนไชส์รวม', 'Total revenue from franchise operations', NULL, 'numeric', 7)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 14: Franchises'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- S PILLAR - Subcategories + Datapoints
-- ==========================================

-- Labor Practices
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Employment', 'การจ้างงาน', 'Employment statistics including hiring, turnover, and benefits', 1),
    ('Wages & Benefits', 'ค่าจ้างและสวัสดิการ', 'Compensation, minimum wage compliance, and employee benefits', 2)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Labor Practices'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Total employees', 'จำนวนพนักงานทั้งหมด', 'Total number of employees', 'persons', 'numeric', 1),
    ('New hires', 'พนักงานใหม่', 'Number of new employees hired during the period', 'persons', 'numeric', 2),
    ('Turnover rate', 'อัตราการลาออก', 'Employee turnover rate', '%', 'numeric', 3),
    ('Full-time employees', 'พนักงานประจำ', 'Number of full-time employees', 'persons', 'numeric', 4),
    ('Part-time/contract employees', 'พนักงานชั่วคราว/สัญญาจ้าง', 'Number of part-time or contract employees', 'persons', 'numeric', 5),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered by employment data', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Employment'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Average salary', 'เงินเดือนเฉลี่ย', 'Average employee salary', NULL, 'numeric', 1),
    ('Minimum wage ratio', 'อัตราส่วนค่าแรงขั้นต่ำ', 'Ratio of entry-level wage to local minimum wage', NULL, 'numeric', 2),
    ('Total payroll', 'ค่าจ้างรวม', 'Total payroll expense', NULL, 'numeric', 3),
    ('Benefits coverage', 'ความครอบคลุมสวัสดิการ', 'Percentage of employees receiving benefits (health, pension)', '%', 'numeric', 4),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Wages & Benefits'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Health & Safety
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, sub.name, sub.name_th, sub.description, sub.sort_order
FROM esg_data_category
CROSS JOIN (VALUES
    ('Occupational Incidents', 'อุบัติเหตุจากการทำงาน', 'Work-related injuries, illnesses, and fatalities', 1),
    ('Safety Programs', 'โปรแกรมความปลอดภัย', 'Safety training, audits, and prevention programs', 2)
) AS sub(name, name_th, description, sort_order)
WHERE esg_data_category.name = 'Health & Safety'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = sub.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Lost-time injury rate (LTIR)', 'อัตราการบาดเจ็บจากการหยุดงาน', 'Number of lost-time injuries per 200,000 hours worked', NULL, 'numeric', 1),
    ('Total recordable incidents', 'จำนวนอุบัติเหตุทั้งหมด', 'Total number of recordable work incidents', 'cases', 'numeric', 2),
    ('Fatalities', 'ผู้เสียชีวิต', 'Number of work-related fatalities', 'persons', 'numeric', 3),
    ('Lost work days', 'วันหยุดงาน', 'Total work days lost due to injuries', 'days', 'numeric', 4),
    ('Near-miss incidents', 'เหตุการณ์เกือบเกิดอุบัติเหตุ', 'Number of near-miss incidents reported', 'cases', 'numeric', 5),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Occupational Incidents'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Safety training hours', 'ชั่วโมงฝึกอบรมความปลอดภัย', 'Total hours of safety training conducted', 'hours', 'numeric', 1),
    ('Employees trained', 'จำนวนพนักงานที่ฝึกอบรม', 'Number of employees who completed safety training', 'persons', 'numeric', 2),
    ('Safety audits conducted', 'จำนวนการตรวจสอบความปลอดภัย', 'Number of safety audits or inspections', 'audits', 'numeric', 3),
    ('Safety investment', 'ค่าลงทุนด้านความปลอดภัย', 'Investment in safety equipment and programs', NULL, 'numeric', 4),
    ('Program date', 'วันที่ดำเนินโปรแกรม', 'Date of safety program or audit', NULL, 'date', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Safety Programs'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Human Rights
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Human Rights Assessment', 'การประเมินสิทธิมนุษยชน', 'Human rights due diligence and impact assessments', 1
FROM esg_data_category WHERE esg_data_category.name = 'Human Rights'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Human Rights Assessment'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Assessments conducted', 'จำนวนการประเมิน', 'Number of human rights assessments conducted', 'assessments', 'numeric', 1),
    ('Operations assessed', 'สถานประกอบการที่ประเมิน', 'Number or percentage of operations assessed', '%', 'numeric', 2),
    ('Grievances filed', 'ข้อร้องเรียน', 'Number of human rights grievances filed', 'cases', 'numeric', 3),
    ('Grievances resolved', 'ข้อร้องเรียนที่แก้ไข', 'Number of grievances resolved', 'cases', 'numeric', 4),
    ('Child labor incidents', 'เหตุการณ์ใช้แรงงานเด็ก', 'Number of child labor incidents identified', 'cases', 'numeric', 5),
    ('Assessment date', 'วันที่ประเมิน', 'Date of assessment', NULL, 'date', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Human Rights Assessment'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Community Engagement
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Community Programs', 'โปรแกรมชุมชน', 'Community investment, engagement, and impact programs', 1
FROM esg_data_category WHERE esg_data_category.name = 'Community Engagement'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Community Programs'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Community investment', 'เงินลงทุนชุมชน', 'Total monetary investment in community programs', NULL, 'numeric', 1),
    ('Beneficiaries', 'ผู้ได้รับประโยชน์', 'Number of community members benefited', 'persons', 'numeric', 2),
    ('Volunteer hours', 'ชั่วโมงอาสาสมัคร', 'Total employee volunteer hours', 'hours', 'numeric', 3),
    ('Program description', 'รายละเอียดโปรแกรม', 'Description of community engagement program', NULL, 'text', 4),
    ('Program date', 'วันที่ดำเนินโปรแกรม', 'Date of program or event', NULL, 'date', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Community Programs'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Diversity & Inclusion
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Workforce Diversity', 'ความหลากหลายของกำลังคน', 'Diversity metrics across gender, age, and other dimensions', 1
FROM esg_data_category WHERE esg_data_category.name = 'Diversity & Inclusion'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Workforce Diversity'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Female employees', 'พนักงานหญิง', 'Percentage of female employees', '%', 'numeric', 1),
    ('Female in management', 'ผู้หญิงในตำแหน่งบริหาร', 'Percentage of women in management positions', '%', 'numeric', 2),
    ('Disability employees', 'พนักงานผู้พิการ', 'Number of employees with disabilities', 'persons', 'numeric', 3),
    ('Age diversity', 'ความหลากหลายด้านอายุ', 'Distribution across age groups (under 30, 30-50, over 50)', NULL, 'text', 4),
    ('Pay equity ratio', 'อัตราส่วนความเท่าเทียมค่าจ้าง', 'Ratio of female to male average salary', NULL, 'numeric', 5),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Workforce Diversity'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Training & Development
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Employee Training', 'การฝึกอบรมพนักงาน', 'Training programs, hours, and skill development', 1
FROM esg_data_category WHERE esg_data_category.name = 'Training & Development'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Employee Training'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Training hours per employee', 'ชั่วโมงฝึกอบรมต่อคน', 'Average training hours per employee', 'hours', 'numeric', 1),
    ('Total training hours', 'ชั่วโมงฝึกอบรมรวม', 'Total training hours across all employees', 'hours', 'numeric', 2),
    ('Employees trained', 'จำนวนพนักงานที่ฝึกอบรม', 'Number of employees who received training', 'persons', 'numeric', 3),
    ('Training investment', 'ค่าลงทุนฝึกอบรม', 'Total investment in training programs', NULL, 'numeric', 4),
    ('Training topic', 'หัวข้อฝึกอบรม', 'Topic or category of training', NULL, 'text', 5),
    ('Training date', 'วันที่ฝึกอบรม', 'Date of training program', NULL, 'date', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Employee Training'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Supply Chain Social
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'S', id, 'Supplier Social Assessment', 'การประเมินด้านสังคมของผู้จัดจำหน่าย', 'Social screening and assessment of suppliers', 1
FROM esg_data_category WHERE esg_data_category.name = 'Supply Chain Social'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Supplier Social Assessment'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'S', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Suppliers screened', 'ผู้จัดจำหน่ายที่คัดกรอง', 'Number of suppliers screened for social criteria', 'suppliers', 'numeric', 1),
    ('Screening rate', 'อัตราการคัดกรอง', 'Percentage of suppliers screened', '%', 'numeric', 2),
    ('Suppliers with violations', 'ผู้จัดจำหน่ายที่มีการละเมิด', 'Number of suppliers with significant social violations', 'suppliers', 'numeric', 3),
    ('Corrective actions taken', 'การดำเนินการแก้ไข', 'Number of corrective actions implemented', 'actions', 'numeric', 4),
    ('Assessment date', 'วันที่ประเมิน', 'Date of supplier assessment', NULL, 'date', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Supplier Social Assessment'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- ==========================================
-- G PILLAR - Subcategories + Datapoints
-- ==========================================

-- Board & Governance Structure
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Board Composition', 'องค์ประกอบคณะกรรมการ', 'Board membership, independence, and diversity', 1
FROM esg_data_category WHERE esg_data_category.name = 'Board & Governance Structure'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Board Composition'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Board members', 'จำนวนกรรมการ', 'Total number of board members', 'persons', 'numeric', 1),
    ('Independent directors', 'กรรมการอิสระ', 'Number of independent directors', 'persons', 'numeric', 2),
    ('Female directors', 'กรรมการหญิง', 'Number of female board members', 'persons', 'numeric', 3),
    ('Board meetings held', 'จำนวนการประชุม', 'Number of board meetings held during the period', 'meetings', 'numeric', 4),
    ('Average attendance rate', 'อัตราการเข้าร่วมเฉลี่ย', 'Average board meeting attendance rate', '%', 'numeric', 5),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Board Composition'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Anti-Corruption
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Anti-Corruption Measures', 'มาตรการต่อต้านการทุจริต', 'Anti-corruption policies, training, and incidents', 1
FROM esg_data_category WHERE esg_data_category.name = 'Anti-Corruption'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Anti-Corruption Measures'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Employees trained', 'พนักงานที่ได้รับการอบรม', 'Number of employees trained on anti-corruption', 'persons', 'numeric', 1),
    ('Training coverage', 'ความครอบคลุมการอบรม', 'Percentage of employees who completed anti-corruption training', '%', 'numeric', 2),
    ('Corruption incidents', 'เหตุการณ์ทุจริต', 'Number of confirmed corruption incidents', 'cases', 'numeric', 3),
    ('Whistleblower reports', 'รายงานแจ้งเบาะแส', 'Number of whistleblower reports received', 'reports', 'numeric', 4),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Anti-Corruption Measures'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Risk Management
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Risk Assessment & Mitigation', 'การประเมินและลดความเสี่ยง', 'Enterprise risk assessment, identification, and mitigation', 1
FROM esg_data_category WHERE esg_data_category.name = 'Risk Management'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Risk Assessment & Mitigation'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Risks identified', 'ความเสี่ยงที่ระบุ', 'Number of material ESG risks identified', 'risks', 'numeric', 1),
    ('Risks mitigated', 'ความเสี่ยงที่บรรเทา', 'Number of risks with mitigation plans implemented', 'risks', 'numeric', 2),
    ('Risk category', 'หมวดความเสี่ยง', 'Category of risk (climate, regulatory, operational, reputational)', NULL, 'text', 3),
    ('Assessment date', 'วันที่ประเมิน', 'Date of risk assessment', NULL, 'date', 4)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Risk Assessment & Mitigation'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Compliance
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Regulatory Compliance', 'การปฏิบัติตามข้อกำหนด', 'Legal and regulatory compliance tracking', 1
FROM esg_data_category WHERE esg_data_category.name = 'Compliance'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Regulatory Compliance'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Violations/fines', 'การละเมิด/ค่าปรับ', 'Number of regulatory violations or fines', 'cases', 'numeric', 1),
    ('Total fines amount', 'จำนวนค่าปรับรวม', 'Total monetary value of fines', NULL, 'numeric', 2),
    ('Compliance audits', 'การตรวจสอบการปฏิบัติตาม', 'Number of compliance audits conducted', 'audits', 'numeric', 3),
    ('Non-compliance issues', 'ประเด็นไม่ปฏิบัติตาม', 'Number of non-compliance issues identified', 'issues', 'numeric', 4),
    ('Regulation type', 'ประเภทข้อกำหนด', 'Type of regulation (environmental, labor, financial, safety)', NULL, 'text', 5),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Regulatory Compliance'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Ethics & Transparency
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Ethics & Code of Conduct', 'จริยธรรมและจรรยาบรรณ', 'Code of conduct adherence, ethics training, and disclosure', 1
FROM esg_data_category WHERE esg_data_category.name = 'Ethics & Transparency'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Ethics & Code of Conduct'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Ethics training coverage', 'ความครอบคลุมการอบรมจริยธรรม', 'Percentage of employees who completed ethics training', '%', 'numeric', 1),
    ('Ethics violations', 'การละเมิดจริยธรรม', 'Number of ethics violations reported', 'cases', 'numeric', 2),
    ('Grievance cases', 'จำนวนเรื่องร้องเรียน', 'Number of grievance cases through ethics hotline', 'cases', 'numeric', 3),
    ('Cases resolved', 'เรื่องที่แก้ไขแล้ว', 'Number of ethics cases resolved', 'cases', 'numeric', 4),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 5)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Ethics & Code of Conduct'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );

-- Data Privacy & Security
INSERT INTO esg_data_subcategory (pillar, esg_data_category_id, name, name_th, description, sort_order)
SELECT 'G', id, 'Data Protection', 'การคุ้มครองข้อมูล', 'Data privacy incidents, compliance, and security measures', 1
FROM esg_data_category WHERE esg_data_category.name = 'Data Privacy & Security'
  AND NOT EXISTS (
    SELECT 1 FROM esg_data_subcategory es WHERE es.esg_data_category_id = esg_data_category.id AND es.name = 'Data Protection'
  );

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'G', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Data breach incidents', 'เหตุการณ์ข้อมูลรั่วไหล', 'Number of data breach incidents', 'incidents', 'numeric', 1),
    ('Records affected', 'จำนวนข้อมูลที่ได้รับผลกระทบ', 'Number of customer/employee records affected', 'records', 'numeric', 2),
    ('Privacy training coverage', 'ความครอบคลุมการอบรมความเป็นส่วนตัว', 'Percentage of employees trained on data privacy', '%', 'numeric', 3),
    ('Security investment', 'ค่าลงทุนด้านความปลอดภัย', 'Investment in cybersecurity and data protection', NULL, 'numeric', 4),
    ('PDPA compliance status', 'สถานะการปฏิบัติตาม PDPA', 'Current PDPA/GDPR compliance status', NULL, 'text', 5),
    ('Reporting period', 'ระยะเวลารายงาน', 'Period covered', NULL, 'text', 6)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Data Protection'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );
