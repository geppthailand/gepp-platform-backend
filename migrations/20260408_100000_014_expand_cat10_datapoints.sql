-- ==========================================
-- Expand Category 10: Processing of Sold Products
-- Adds 11 new datapoints (sort_order 6-16) to capture
-- material type, processing activity, emission factors,
-- processing emissions, financial data, and invoice references
-- ==========================================

INSERT INTO esg_datapoint (pillar, esg_data_subcategory_id, name, name_th, description, unit, data_type, sort_order)
SELECT 'E', s.id, dp.name, dp.name_th, dp.description, dp.unit, dp.data_type, dp.sort_order
FROM esg_data_subcategory s
CROSS JOIN (VALUES
    ('Product reference', 'รหัสอ้างอิงผลิตภัณฑ์', 'Product reference code or purchase order number', NULL, 'text', 6),
    ('Material type', 'ประเภทวัสดุ', 'Type of material being processed (e.g. steel, plastics, aluminum)', NULL, 'text', 7),
    ('Processing activity', 'กิจกรรมการแปรรูป', 'Description of the processing activity performed (e.g. laser cutting, injection molding)', NULL, 'text', 8),
    ('Processing category', 'หมวดหมู่การแปรรูป', 'Category of downstream processing (e.g. cutting, molding, packaging, quality assurance)', NULL, 'text', 9),
    ('Energy type', 'ประเภทพลังงาน', 'Type of energy used in downstream processing (e.g. electric, natural gas, steam)', NULL, 'text', 10),
    ('Emission factor', 'ค่าสัมประสิทธิ์การปล่อย', 'Emission factor for the processing activity', 'tCO2e/unit', 'numeric', 11),
    ('Processing emissions', 'การปล่อยก๊าซจากการแปรรูป', 'Total GHG emissions from the processing activity', 'tCO2e', 'numeric', 12),
    ('Rate per unit', 'ราคาต่อหน่วย', 'Price or rate charged per unit of processing', NULL, 'numeric', 13),
    ('Total cost', 'ค่าใช้จ่ายรวม', 'Total monetary cost for the processing service line item', NULL, 'numeric', 14),
    ('Processing date', 'วันที่แปรรูป', 'Date when downstream processing was performed', NULL, 'date', 15),
    ('Invoice reference number', 'เลขที่ใบแจ้งหนี้', 'Invoice or document reference number', NULL, 'text', 16)
) AS dp(name, name_th, description, unit, data_type, sort_order)
WHERE s.name = 'Category 10: Processing of Sold Products'
  AND NOT EXISTS (
    SELECT 1 FROM esg_datapoint ep
    WHERE ep.esg_data_subcategory_id = s.id AND ep.name = dp.name
  );
