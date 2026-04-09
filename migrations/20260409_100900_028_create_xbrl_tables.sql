-- XBRL Tagging System for ISSB/IFRS S1+S2 and SEC Thailand Compliance
-- Maps ESG datapoints to standardized reporting taxonomies

CREATE TABLE IF NOT EXISTS esg_xbrl_tags (
    id BIGSERIAL PRIMARY KEY,
    taxonomy VARCHAR(50) NOT NULL,
    tag_name VARCHAR(200) NOT NULL,
    tag_label VARCHAR(300),
    tag_label_th VARCHAR(300),
    data_type VARCHAR(30) NOT NULL DEFAULT 'quantity',
    datapoint_id BIGINT REFERENCES esg_datapoints(id),
    category_id BIGINT REFERENCES esg_data_categories(id),
    period_type VARCHAR(20) NOT NULL DEFAULT 'duration',
    unit VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_xbrl_taxonomy CHECK (taxonomy IN ('issb_s1', 'issb_s2', 'sec_th', 'gri', 'esrs')),
    CONSTRAINT chk_xbrl_datatype CHECK (data_type IN ('monetary', 'quantity', 'percentage', 'text', 'date', 'boolean')),
    CONSTRAINT chk_xbrl_period CHECK (period_type IN ('instant', 'duration'))
);

CREATE INDEX IF NOT EXISTS idx_esg_xbrl_tags_taxonomy
    ON esg_xbrl_tags (taxonomy)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_xbrl_tags_datapoint
    ON esg_xbrl_tags (datapoint_id)
    WHERE is_active = TRUE AND datapoint_id IS NOT NULL;

COMMENT ON TABLE esg_xbrl_tags IS 'XBRL taxonomy mapping for automated compliance report tagging (ISSB, SEC Thailand, GRI)';


CREATE TABLE IF NOT EXISTS esg_xbrl_report_values (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    tag_id BIGINT NOT NULL REFERENCES esg_xbrl_tags(id),
    reporting_year INT NOT NULL,
    value TEXT NOT NULL,
    unit VARCHAR(50),
    context_ref VARCHAR(100),
    data_entry_id BIGINT REFERENCES esg_data_entries(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_esg_xbrl_values_org_year
    ON esg_xbrl_report_values (organization_id, reporting_year)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_xbrl_report_values IS 'Generated XBRL tag values for regulatory filing exports';

-- Seed ISSB S2 Climate Disclosure Tags
INSERT INTO esg_xbrl_tags (taxonomy, tag_name, tag_label, tag_label_th, data_type, period_type, unit) VALUES
    ('issb_s2', 'ifrs-s2:AbsoluteGrossScope1GHGEmissions', 'Absolute Gross Scope 1 GHG Emissions', 'การปล่อยก๊าซเรือนกระจก Scope 1 (ค่าสัมบูรณ์)', 'quantity', 'duration', 'tCO2e'),
    ('issb_s2', 'ifrs-s2:AbsoluteGrossScope2GHGEmissionsLocationBased', 'Absolute Gross Scope 2 GHG Emissions (Location-based)', 'การปล่อยก๊าซเรือนกระจก Scope 2 (ตามที่ตั้ง)', 'quantity', 'duration', 'tCO2e'),
    ('issb_s2', 'ifrs-s2:AbsoluteGrossScope3GHGEmissions', 'Absolute Gross Scope 3 GHG Emissions', 'การปล่อยก๊าซเรือนกระจก Scope 3 (ค่าสัมบูรณ์)', 'quantity', 'duration', 'tCO2e'),
    ('issb_s2', 'ifrs-s2:GHGEmissionsIntensityPerRevenueUnit', 'GHG Emissions Intensity per Revenue', 'ความเข้มข้นการปล่อยต่อรายได้', 'quantity', 'duration', 'tCO2e/MTHB'),
    ('issb_s2', 'ifrs-s2:PercentageRenewableEnergy', 'Percentage of Renewable Energy', 'สัดส่วนพลังงานหมุนเวียน (%)', 'percentage', 'instant', '%'),
    ('issb_s2', 'ifrs-s2:InternalCarbonPrice', 'Internal Carbon Price', 'ราคาคาร์บอนภายในองค์กร', 'monetary', 'instant', 'THB/tCO2e'),
    ('issb_s2', 'ifrs-s2:ClimateRelatedTargetReductionPercentage', 'Climate-related Target Reduction %', 'เป้าหมายลดก๊าซเรือนกระจก (%)', 'percentage', 'instant', '%'),
    ('issb_s2', 'ifrs-s2:ClimateRelatedTargetYear', 'Climate-related Target Year', 'ปีเป้าหมายลดก๊าซเรือนกระจก', 'date', 'instant', 'year'),
    -- SEC Thailand ONE Report Tags
    ('sec_th', 'sec-th:GHGScope1Emissions', 'GHG Scope 1 Emissions', 'การปล่อยก๊าซเรือนกระจกทางตรง (Scope 1)', 'quantity', 'duration', 'tCO2e'),
    ('sec_th', 'sec-th:GHGScope2Emissions', 'GHG Scope 2 Emissions', 'การปล่อยก๊าซเรือนกระจกทางอ้อมจากพลังงาน (Scope 2)', 'quantity', 'duration', 'tCO2e'),
    ('sec_th', 'sec-th:TotalEnergyConsumption', 'Total Energy Consumption', 'การใช้พลังงานรวม', 'quantity', 'duration', 'GJ'),
    ('sec_th', 'sec-th:WaterWithdrawal', 'Total Water Withdrawal', 'ปริมาณน้ำที่ใช้ทั้งหมด', 'quantity', 'duration', 'm3'),
    ('sec_th', 'sec-th:TotalWasteGenerated', 'Total Waste Generated', 'ปริมาณของเสียทั้งหมด', 'quantity', 'duration', 'tonnes'),
    ('sec_th', 'sec-th:EmployeeCount', 'Total Number of Employees', 'จำนวนพนักงานทั้งหมด', 'quantity', 'instant', 'persons'),
    ('sec_th', 'sec-th:EmployeeTurnoverRate', 'Employee Turnover Rate', 'อัตราการลาออกของพนักงาน', 'percentage', 'duration', '%'),
    ('sec_th', 'sec-th:BoardIndependenceRatio', 'Board Independence Ratio', 'สัดส่วนกรรมการอิสระ', 'percentage', 'instant', '%')
ON CONFLICT DO NOTHING;
