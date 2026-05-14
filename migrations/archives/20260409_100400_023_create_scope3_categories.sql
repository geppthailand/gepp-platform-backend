-- GHG Protocol Scope 3 Categories Reference Table
-- Seeds all 15 standard categories for value chain emissions tracking

CREATE TABLE IF NOT EXISTS esg_scope3_categories (
    id BIGSERIAL PRIMARY KEY,
    category_number INT NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    name_th VARCHAR(200),
    description TEXT,
    direction VARCHAR(10) NOT NULL,
    default_method VARCHAR(30) NOT NULL DEFAULT 'spend_based',
    relevance_criteria TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_scope3_direction CHECK (direction IN ('upstream', 'downstream')),
    CONSTRAINT chk_scope3_method CHECK (default_method IN ('spend_based', 'supplier_specific', 'average_data', 'hybrid'))
);

COMMENT ON TABLE esg_scope3_categories IS 'GHG Protocol 15 Scope 3 categories reference data';

-- Seed all 15 GHG Protocol Scope 3 categories
INSERT INTO esg_scope3_categories (category_number, name, name_th, description, direction, default_method, relevance_criteria) VALUES
    (1, 'Purchased goods and services', 'สินค้าและบริการที่จัดซื้อ', 'Extraction, production, and transportation of goods and services purchased by the reporting company', 'upstream', 'spend_based', 'Relevant for all companies with procurement spend'),
    (2, 'Capital goods', 'สินค้าทุน', 'Extraction, production, and transportation of capital goods purchased by the reporting company', 'upstream', 'spend_based', 'Relevant for companies with significant capital expenditure'),
    (3, 'Fuel- and energy-related activities', 'กิจกรรมที่เกี่ยวข้องกับเชื้อเพลิงและพลังงาน', 'Extraction, production, and transportation of fuels and energy not included in Scope 1 or 2', 'upstream', 'average_data', 'Relevant for all companies using energy (transmission and distribution losses)'),
    (4, 'Upstream transportation and distribution', 'การขนส่งและกระจายสินค้าต้นน้ำ', 'Transportation and distribution of products purchased in vehicles not owned by the reporting company', 'upstream', 'spend_based', 'Relevant for companies with inbound logistics'),
    (5, 'Waste generated in operations', 'ของเสียจากการดำเนินงาน', 'Disposal and treatment of waste generated in the reporting company operations', 'upstream', 'supplier_specific', 'Relevant for all companies generating waste'),
    (6, 'Business travel', 'การเดินทางเพื่อธุรกิจ', 'Transportation of employees for business-related activities in vehicles not owned by the company', 'upstream', 'spend_based', 'Relevant for companies with employee travel'),
    (7, 'Employee commuting', 'การเดินทางไป-กลับของพนักงาน', 'Transportation of employees between their homes and worksites', 'upstream', 'average_data', 'Relevant for companies with on-site employees'),
    (8, 'Upstream leased assets', 'สินทรัพย์เช่าต้นน้ำ', 'Operation of assets leased by the reporting company not included in Scope 1 and 2', 'upstream', 'average_data', 'Relevant for companies leasing significant assets'),
    (9, 'Downstream transportation and distribution', 'การขนส่งและกระจายสินค้าปลายน้ำ', 'Transportation and distribution of products sold between the reporting company and the end consumer', 'downstream', 'spend_based', 'Relevant for companies selling physical products'),
    (10, 'Processing of sold products', 'การแปรรูปผลิตภัณฑ์ที่ขาย', 'Processing of intermediate products sold by the reporting company', 'downstream', 'average_data', 'Relevant for companies selling intermediate products'),
    (11, 'Use of sold products', 'การใช้ผลิตภัณฑ์ที่ขาย', 'End use of goods and services sold by the reporting company', 'downstream', 'average_data', 'Relevant for companies selling energy-consuming products'),
    (12, 'End-of-life treatment of sold products', 'การจัดการปลายทางของผลิตภัณฑ์ที่ขาย', 'Waste disposal and treatment of products sold by the reporting company at the end of their life', 'downstream', 'average_data', 'Relevant for companies selling physical products'),
    (13, 'Downstream leased assets', 'สินทรัพย์เช่าปลายน้ำ', 'Operation of assets owned by the reporting company and leased to other entities', 'downstream', 'average_data', 'Relevant for companies leasing assets to others'),
    (14, 'Franchises', 'แฟรนไชส์', 'Operation of franchises not included in Scope 1 and 2', 'downstream', 'average_data', 'Relevant for franchisors'),
    (15, 'Investments', 'การลงทุน', 'Operation of investments not included in Scope 1 and 2', 'downstream', 'spend_based', 'Relevant for financial institutions and investors')
ON CONFLICT (category_number) DO NOTHING;
