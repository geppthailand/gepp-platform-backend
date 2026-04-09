-- Emission factors table for tCO2e calculation
-- Maps activity categories (electricity, fuel, etc.) to CO2e conversion factors

CREATE TABLE IF NOT EXISTS esg_emission_factors (
    id BIGSERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    fuel_type VARCHAR(100),
    factor_value NUMERIC(18, 8) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    result_unit VARCHAR(50) NOT NULL DEFAULT 'tCO2e',
    scope VARCHAR(20) NOT NULL,
    source VARCHAR(200),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_esg_emission_factors_category
    ON esg_emission_factors (category)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_emission_factors_category_unit
    ON esg_emission_factors (category, unit)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_emission_factors IS 'CO2e conversion factors for ESG data entry auto-calculation';

-- Seed common Thailand TGO emission factors
INSERT INTO esg_emission_factors (category, subcategory, factor_value, unit, result_unit, scope, source, description) VALUES
    ('electricity', 'grid', 0.000499900, 'kWh', 'tCO2e', 'Scope 2', 'TGO 2022', 'Thailand grid electricity'),
    ('diesel', 'vehicle', 0.002681000, 'Liter', 'tCO2e', 'Scope 1', 'TGO 2022', 'Diesel fuel for company vehicles'),
    ('gasoline', 'vehicle', 0.002271000, 'Liter', 'tCO2e', 'Scope 1', 'TGO 2022', 'Gasoline for company vehicles'),
    ('lpg', 'cooking', 0.001810000, 'kg', 'tCO2e', 'Scope 1', 'TGO 2022', 'LPG for cooking/heating'),
    ('natural_gas', 'heating', 0.002016000, 'Nm3', 'tCO2e', 'Scope 1', 'TGO 2022', 'Natural gas combustion'),
    ('water', 'tap', 0.000390000, 'm3', 'tCO2e', 'Scope 3', 'TGO 2022', 'Municipal water supply'),
    ('paper', 'office', 0.000900000, 'kg', 'tCO2e', 'Scope 3', 'TGO 2022', 'Paper consumption'),
    ('business_travel', 'flight_domestic', 0.000133000, 'km', 'tCO2e', 'Scope 3', 'TGO 2022', 'Domestic flights per passenger-km'),
    ('business_travel', 'flight_international', 0.000195000, 'km', 'tCO2e', 'Scope 3', 'TGO 2022', 'International flights per passenger-km'),
    ('waste', 'landfill', 0.000467000, 'kg', 'tCO2e', 'Scope 3', 'TGO 2022', 'Waste to landfill')
ON CONFLICT DO NOTHING;
