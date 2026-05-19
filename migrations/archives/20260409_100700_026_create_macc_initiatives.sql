-- MACC (Marginal Abatement Cost Curve) Initiatives
-- Database of carbon reduction measures with cost-effectiveness data

CREATE TABLE IF NOT EXISTS esg_macc_initiatives (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id),
    name VARCHAR(300) NOT NULL,
    name_th VARCHAR(300),
    description TEXT,
    category VARCHAR(100) NOT NULL,
    applicable_scope VARCHAR(20) NOT NULL DEFAULT 'all',
    abatement_potential_tco2e NUMERIC(18, 6) NOT NULL DEFAULT 0,
    implementation_cost NUMERIC(18, 2) NOT NULL DEFAULT 0,
    annual_operating_cost NUMERIC(18, 2) DEFAULT 0,
    annual_savings NUMERIC(18, 2) DEFAULT 0,
    cost_per_tco2e NUMERIC(18, 4) DEFAULT 0,
    payback_years NUMERIC(6, 2),
    implementation_timeline VARCHAR(20) NOT NULL DEFAULT 'short_term',
    difficulty VARCHAR(20) NOT NULL DEFAULT 'moderate',
    is_template BOOLEAN NOT NULL DEFAULT FALSE,
    industry_sector VARCHAR(100),
    source VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'available',
    metadata JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_macc_category CHECK (category IN ('energy_efficiency', 'renewables', 'process', 'transport', 'waste', 'supply_chain', 'other')),
    CONSTRAINT chk_macc_scope CHECK (applicable_scope IN ('scope1', 'scope2', 'scope3', 'all')),
    CONSTRAINT chk_macc_timeline CHECK (implementation_timeline IN ('immediate', 'short_term', 'medium_term', 'long_term')),
    CONSTRAINT chk_macc_difficulty CHECK (difficulty IN ('easy', 'moderate', 'complex')),
    CONSTRAINT chk_macc_status CHECK (status IN ('available', 'planned', 'in_progress', 'completed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_esg_macc_org
    ON esg_macc_initiatives (organization_id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_macc_templates
    ON esg_macc_initiatives (is_template, category)
    WHERE is_active = TRUE AND is_template = TRUE;

COMMENT ON TABLE esg_macc_initiatives IS 'Carbon reduction initiatives library for Marginal Abatement Cost Curve generation';

-- Seed global template initiatives (common Thai industry measures)
INSERT INTO esg_macc_initiatives (name, name_th, category, applicable_scope, abatement_potential_tco2e, implementation_cost, annual_savings, cost_per_tco2e, payback_years, implementation_timeline, difficulty, is_template, source) VALUES
    ('LED Lighting Retrofit', 'เปลี่ยนหลอดไฟเป็น LED', 'energy_efficiency', 'scope2', 8.0, 80000, 45000, -5625, 1.8, 'short_term', 'easy', TRUE, 'TGO Thailand'),
    ('Solar Rooftop PPA', 'ติดตั้งโซลาร์เซลล์บนหลังคา (PPA)', 'renewables', 'scope2', 50.0, 0, 180000, -3600, 0, 'medium_term', 'moderate', TRUE, 'DEDE Thailand'),
    ('HVAC Scheduling Optimization', 'ปรับเวลาเปิด-ปิดระบบปรับอากาศ', 'energy_efficiency', 'scope2', 12.0, 30000, 60000, -5000, 0.5, 'immediate', 'easy', TRUE, 'DEDE Thailand'),
    ('Fleet EV Transition (Partial)', 'เปลี่ยนรถยนต์เป็นไฟฟ้า (บางส่วน)', 'transport', 'scope1', 25.0, 1500000, 120000, 55200, 4.5, 'medium_term', 'complex', TRUE, 'IEA'),
    ('Waste Heat Recovery', 'ระบบนำความร้อนเหลือใช้กลับมาใช้', 'process', 'scope1', 18.0, 500000, 150000, -8333, 3.3, 'medium_term', 'moderate', TRUE, 'TGO Thailand'),
    ('Green Procurement Policy', 'นโยบายจัดซื้อจัดจ้างสีเขียว', 'supply_chain', 'scope3', 15.0, 50000, 20000, -1333, 2.5, 'short_term', 'easy', TRUE, 'GHG Protocol'),
    ('Supplier Engagement Program', 'โปรแกรมร่วมมือกับ Supplier', 'supply_chain', 'scope3', 30.0, 300000, 50000, 8333, 2.0, 'medium_term', 'moderate', TRUE, 'CDP'),
    ('Compressed Air Optimization', 'ปรับปรุงระบบอัดอากาศ', 'energy_efficiency', 'scope2', 5.0, 40000, 35000, -7000, 1.1, 'short_term', 'easy', TRUE, 'DEDE Thailand'),
    ('Power Factor Correction', 'ปรับค่าเพาเวอร์แฟกเตอร์', 'energy_efficiency', 'scope2', 4.0, 75000, 40000, -10000, 1.9, 'short_term', 'easy', TRUE, 'DEDE Thailand'),
    ('Biofuel Blending (B20)', 'ใช้ไบโอดีเซล B20', 'transport', 'scope1', 10.0, 20000, 5000, 1500, 4.0, 'immediate', 'easy', TRUE, 'TGO Thailand'),
    ('Smart Metering System', 'ติดตั้งระบบมิเตอร์อัจฉริยะ', 'energy_efficiency', 'scope2', 7.0, 120000, 50000, -7143, 2.4, 'short_term', 'easy', TRUE, 'DEDE Thailand'),
    ('Process Electrification', 'เปลี่ยนกระบวนการผลิตเป็นไฟฟ้า', 'process', 'scope1', 40.0, 3000000, 200000, 70000, 5.0, 'long_term', 'complex', TRUE, 'IEA'),
    ('Water Recycling System', 'ระบบรีไซเคิลน้ำ', 'other', 'scope3', 3.0, 500000, 100000, -33333, 5.0, 'medium_term', 'moderate', TRUE, 'TGO Thailand'),
    ('Building Insulation Upgrade', 'ปรับปรุงฉนวนกันความร้อนอาคาร', 'energy_efficiency', 'scope2', 6.0, 250000, 40000, -6667, 6.3, 'medium_term', 'moderate', TRUE, 'DEDE Thailand'),
    ('Carbon Credit Purchase (T-VER)', 'ซื้อคาร์บอนเครดิต (T-VER)', 'other', 'all', 100.0, 1200000, 0, 12000, 0, 'immediate', 'easy', TRUE, 'TGO Thailand')
ON CONFLICT DO NOTHING;
