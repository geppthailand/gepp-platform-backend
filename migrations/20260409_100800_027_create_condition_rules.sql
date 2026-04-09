-- ESG Condition Rules Engine
-- Database-driven rules for alerts, recommendations, and commendations
-- Replaces hardcoded rules in esg_insight_engine.py with extensible system

CREATE TABLE IF NOT EXISTS esg_condition_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(50) NOT NULL UNIQUE,
    category VARCHAR(30) NOT NULL,
    condition_type VARCHAR(30) NOT NULL,
    condition_expression JSONB NOT NULL,
    insight_type VARCHAR(20) NOT NULL,
    severity INT NOT NULL DEFAULT 0,
    target_section VARCHAR(50),
    title VARCHAR(200) NOT NULL,
    title_th VARCHAR(200),
    message_template TEXT NOT NULL,
    message_template_th TEXT,
    action_url VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_rule_category CHECK (category IN ('emission', 'financial', 'framework', 'data_quality', 'supply_chain', 'target', 'general')),
    CONSTRAINT chk_rule_type CHECK (condition_type IN ('threshold', 'comparison', 'trend', 'completeness', 'missing', 'composite')),
    CONSTRAINT chk_rule_insight CHECK (insight_type IN ('quickwin', 'opportunity', 'alert', 'critical', 'praise', 'info')),
    CONSTRAINT chk_rule_severity CHECK (severity BETWEEN 0 AND 4)
);

CREATE INDEX IF NOT EXISTS idx_esg_rules_active
    ON esg_condition_rules (is_active, category)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_condition_rules IS 'Extensible condition rules engine for smart alerts, recommendations, and commendations across ESG dashboard';

-- Seed initial condition rules
INSERT INTO esg_condition_rules (rule_code, category, condition_type, condition_expression, insight_type, severity, target_section, title, title_th, message_template, message_template_th) VALUES
    -- Emission rules
    ('EM001', 'emission', 'threshold', '{"and": [{"field": "scope2_pct", "op": ">", "value": 60}, {"field": "renewable_energy_pct", "op": "<", "value": 20}]}', 'alert', 2, 'scope_breakdown', 'High Scope 2 Dependency', 'พึ่งพา Scope 2 สูง', 'Scope 2 represents {scope2_pct}% of your emissions with only {renewable_energy_pct}% renewable energy. Consider a solar PPA or green electricity tariff.', 'Scope 2 คิดเป็น {scope2_pct}% ของการปล่อยก๊าซเรือนกระจก โดยใช้พลังงานหมุนเวียนเพียง {renewable_energy_pct}% พิจารณาทำ Solar PPA หรือซื้อไฟฟ้าสีเขียว'),
    ('EM002', 'emission', 'threshold', '{"and": [{"field": "scope3_coverage_pct", "op": "<", "value": 40}, {"field": "total_tco2e", "op": ">", "value": 100}]}', 'alert', 3, 'scope3_detail', 'Scope 3 Data Gap', 'ข้อมูล Scope 3 ไม่ครบ', 'Your Scope 3 data covers only {scope3_coverage_pct}% of value chain categories. Start with Category 1 (Purchased Goods) and Category 5 (Waste).', 'ข้อมูล Scope 3 ครอบคลุมเพียง {scope3_coverage_pct}% ของ value chain เริ่มจาก Category 1 (สินค้าที่จัดซื้อ) และ Category 5 (ของเสีย)'),
    ('EM003', 'emission', 'trend', '{"and": [{"field": "intensity_yoy_change", "op": ">", "value": 5}, {"field": "production_volume_change", "op": "<", "value": 10}]}', 'critical', 4, 'esg_kpis', 'Emission Intensity Rising', 'ค่าความเข้มข้นการปล่อยเพิ่มขึ้น', 'Carbon intensity increased {intensity_yoy_change}% despite production growing only {production_volume_change}%. Investigate energy efficiency.', 'ค่าความเข้มข้นคาร์บอนเพิ่มขึ้น {intensity_yoy_change}% แม้การผลิตเพิ่มเพียง {production_volume_change}% ตรวจสอบประสิทธิภาพพลังงาน'),
    ('EM004', 'target', 'comparison', '{"and": [{"field": "current_reduction_pct", "op": ">", "value": 0}, {"field": "reduction_vs_pace", "op": ">", "value": 1.2}]}', 'praise', 0, 'target_progress', 'Excellent Reduction Pace', 'ทำได้ดีมาก! ลดได้เร็วกว่าเป้า', 'Outstanding! Your {current_reduction_pct}% reduction is ahead of the pace needed for your {target_year} target.', 'ยอดเยี่ยม! ลดได้ {current_reduction_pct}% เร็วกว่าเป้าหมายปี {target_year}'),
    ('EM005', 'emission', 'threshold', '{"and": [{"field": "electricity_mom_change", "op": ">", "value": 20}, {"field": "production_volume_change", "op": "<", "value": 5}]}', 'critical', 4, 'monthly_trend', 'Production Energy Spike', 'การใช้ไฟฟ้าในการผลิตพุ่ง', 'Electricity consumption spiked {electricity_mom_change}% month-over-month without proportional production increase.', 'การใช้ไฟฟ้าพุ่ง {electricity_mom_change}% เดือนต่อเดือน โดยไม่มีการเพิ่มการผลิตตามสัดส่วน'),
    -- Financial rules
    ('FIN001', 'financial', 'threshold', '{"field": "carbon_tax_pct_revenue", "op": ">", "value": 2}', 'critical', 4, 'pl_impact', 'Carbon Tax High Exposure', 'ความเสี่ยงภาษีคาร์บอนสูง', 'Estimated carbon tax liability exceeds 2% of revenue. Prioritize emission reduction to lower financial exposure.', 'ภาษีคาร์บอนประเมินเกิน 2% ของรายได้ เร่งลดการปล่อยเพื่อลดความเสี่ยงทางการเงิน'),
    ('FIN002', 'financial', 'comparison', '{"and": [{"field": "savings_from_reduction", "op": ">", "value": 0}, {"field": "savings_vs_tax_low", "op": ">", "value": 1}]}', 'praise', 0, 'pl_impact', 'ROI-Positive Reduction', 'การลดคาร์บอนคุ้มทุน', 'Your emission reductions generate savings of {savings_from_reduction} THB/yr, exceeding low-scenario carbon tax liability.', 'การลดการปล่อยก๊าซสร้างผลประหยัด {savings_from_reduction} บาท/ปี สูงกว่าภาษีคาร์บอนกรณีต่ำ'),
    -- Framework rules
    ('FW001', 'framework', 'completeness', '{"and": [{"field": "scope1_completeness", "op": ">", "value": 90}, {"field": "scope2_completeness", "op": ">", "value": 90}]}', 'praise', 0, 'framework_alignment', 'TGO CFO Ready', 'พร้อมขอใบรับรอง TGO CFO', 'Congratulations! Your Scope 1 and Scope 2 data completeness exceeds 90%, meeting TGO Carbon Footprint for Organization readiness.', 'ยินดีด้วย! ข้อมูล Scope 1 และ 2 ครบถ้วนกว่า 90% พร้อมขอใบรับรอง TGO CFO'),
    ('FW002', 'framework', 'threshold', '{"and": [{"field": "gri_alignment", "op": "<", "value": 50}, {"field": "data_completeness", "op": ">", "value": 70}]}', 'alert', 2, 'framework_alignment', 'GRI Gap Detected', 'พบช่องว่าง GRI', 'Your GRI alignment score is {gri_alignment}% despite having 70%+ data completeness. Map existing data to GRI disclosures.', 'คะแนน GRI อยู่ที่ {gri_alignment}% แม้มีข้อมูลครบ 70%+ ลอง Map ข้อมูลที่มีเข้ากับ GRI disclosures'),
    -- Data quality rules
    ('DQ001', 'data_quality', 'missing', '{"field": "days_since_last_entry", "op": ">", "value": 30}', 'alert', 3, 'hero_card', 'Data Stale', 'ข้อมูลค้าง', 'No new data entries in {days_since_last_entry} days. Regular data capture ensures accurate reporting.', 'ไม่มีข้อมูลใหม่มา {days_since_last_entry} วัน การเก็บข้อมูลสม่ำเสมอช่วยให้รายงานแม่นยำ'),
    ('DQ002', 'data_quality', 'threshold', '{"and": [{"field": "verified_percent", "op": "<", "value": 40}, {"field": "total_entries", "op": ">", "value": 20}]}', 'alert', 2, 'data_quality', 'Low Verification Rate', 'อัตราการยืนยันข้อมูลต่ำ', 'Only {verified_percent}% of your {total_entries} entries are verified. Verify data to improve report credibility.', 'มีเพียง {verified_percent}% ของ {total_entries} รายการที่ได้รับการยืนยัน ตรวจสอบข้อมูลเพื่อเพิ่มความน่าเชื่อถือ'),
    ('DQ003', 'data_quality', 'completeness', '{"and": [{"field": "verified_percent", "op": ">", "value": 85}, {"field": "data_completeness", "op": ">", "value": 90}]}', 'praise', 0, 'hero_card', 'Excellent Data Quality', 'คุณภาพข้อมูลยอดเยี่ยม', 'Outstanding data quality! {verified_percent}% verified with {data_completeness}% completeness.', 'คุณภาพข้อมูลยอดเยี่ยม! ยืนยันแล้ว {verified_percent}% ครบถ้วน {data_completeness}%'),
    ('DQ004', 'data_quality', 'comparison', '{"field": "pillar_gap", "op": ">", "value": 40}', 'alert', 2, 'esg_completeness', 'Pillar Imbalance', 'ข้อมูล ESG ไม่สมดุล', 'Your ESG pillars are unbalanced: highest at {max_pillar}%, lowest at {min_pillar}%. Focus on the weaker pillar.', 'ข้อมูล ESG ไม่สมดุล: สูงสุด {max_pillar}% ต่ำสุด {min_pillar}% เน้นปรับปรุง pillar ที่อ่อน'),
    -- Supply chain rules
    ('SC001', 'supply_chain', 'threshold', '{"and": [{"field": "supplier_response_rate", "op": "<", "value": 50}, {"field": "total_suppliers", "op": ">", "value": 5}]}', 'alert', 3, 'supply_chain', 'Low Supplier Response Rate', 'Supplier ตอบกลับน้อย', 'Only {supplier_response_rate}% of your suppliers have submitted data. Enable automated chasers to improve coverage.', 'มีเพียง {supplier_response_rate}% ของ Supplier ที่ส่งข้อมูลมา เปิดระบบทวงอัตโนมัติเพื่อเพิ่ม coverage'),
    ('SC002', 'supply_chain', 'threshold', '{"field": "scope3_from_suppliers_pct", "op": ">", "value": 60}', 'praise', 0, 'scope3_detail', 'Strong Supplier Coverage', 'ข้อมูล Supplier ครอบคลุมดี', 'Excellent! {scope3_from_suppliers_pct}% of your Scope 3 data comes from supplier-specific measurements.', 'ยอดเยี่ยม! {scope3_from_suppliers_pct}% ของข้อมูล Scope 3 มาจากข้อมูลจริงของ Supplier')
ON CONFLICT (rule_code) DO NOTHING;
