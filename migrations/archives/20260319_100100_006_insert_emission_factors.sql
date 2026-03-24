-- Migration: 006 - Insert Emission Factors
-- Date: 2026-03-19
-- Description: Pre-populate emission factors from TGO and IPCC sources
--   Factors are in kgCO2e per kg of waste

INSERT INTO esg_emission_factors (waste_type, waste_category, treatment_method, factor_value, factor_unit, source, source_version, country_code, notes)
VALUES
-- ============================================================
-- LANDFILL — TGO Thailand (based on IPCC AR6)
-- ============================================================
('general', 'municipal_solid', 'landfill', 0.580000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Mixed MSW landfill, Thailand average'),
('organic', 'municipal_solid', 'landfill', 1.200000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Food/garden waste, high methane potential'),
('paper', 'municipal_solid', 'landfill', 0.460000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Paper/cardboard in landfill'),
('plastic', 'municipal_solid', 'landfill', 0.040000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Plastic in landfill (low degradation)'),
('glass', 'municipal_solid', 'landfill', 0.010000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Glass in landfill (inert)'),
('metal', 'municipal_solid', 'landfill', 0.010000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Metal in landfill (inert)'),
('electronic', 'industrial', 'landfill', 0.700000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'E-waste in landfill'),
('hazardous', 'industrial', 'landfill', 0.800000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Hazardous waste in controlled landfill'),

-- ============================================================
-- INCINERATION — TGO Thailand
-- ============================================================
('general', 'municipal_solid', 'incineration', 0.930000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Mixed MSW incineration without energy recovery'),
('organic', 'municipal_solid', 'incineration', 0.350000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Food waste incineration'),
('paper', 'municipal_solid', 'incineration', 0.910000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Paper incineration (biogenic CO2 excluded)'),
('plastic', 'municipal_solid', 'incineration', 2.300000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Plastic incineration (fossil carbon)'),
('electronic', 'industrial', 'incineration', 1.500000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'E-waste incineration'),
('hazardous', 'industrial', 'incineration', 1.800000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Hazardous waste high-temp incineration'),

-- ============================================================
-- RECYCLING — TGO Thailand (credit-adjusted, net emission)
-- ============================================================
('general', 'municipal_solid', 'recycling', 0.021000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Mixed recyclables processing'),
('paper', 'municipal_solid', 'recycling', 0.018000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Paper recycling (net after credit)'),
('plastic', 'municipal_solid', 'recycling', 0.025000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Plastic recycling (net after credit)'),
('glass', 'municipal_solid', 'recycling', 0.015000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Glass recycling'),
('metal', 'municipal_solid', 'recycling', 0.012000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Metal recycling'),
('electronic', 'industrial', 'recycling', 0.050000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'E-waste recycling/recovery'),

-- ============================================================
-- COMPOSTING — TGO Thailand
-- ============================================================
('organic', 'municipal_solid', 'composting', 0.010000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Aerobic composting'),
('general', 'municipal_solid', 'composting', 0.025000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Mixed waste composting'),

-- ============================================================
-- ANAEROBIC DIGESTION — TGO Thailand
-- ============================================================
('organic', 'municipal_solid', 'anaerobic_digestion', 0.008000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Biogas with energy recovery'),
('general', 'municipal_solid', 'anaerobic_digestion', 0.015000, 'kgCO2e/kg', 'TGO', '2024', 'TH', 'Mixed waste anaerobic digestion'),

-- ============================================================
-- IPCC AR6 Global Defaults (fallback)
-- ============================================================
('general', 'municipal_solid', 'landfill', 0.600000, 'kgCO2e/kg', 'IPCC', 'AR6', NULL, 'IPCC default for managed landfill'),
('general', 'municipal_solid', 'incineration', 0.980000, 'kgCO2e/kg', 'IPCC', 'AR6', NULL, 'IPCC default for mass-burn incineration'),
('general', 'municipal_solid', 'recycling', 0.020000, 'kgCO2e/kg', 'IPCC', 'AR6', NULL, 'IPCC default for recycling'),
('organic', 'municipal_solid', 'composting', 0.012000, 'kgCO2e/kg', 'IPCC', 'AR6', NULL, 'IPCC default for composting')

ON CONFLICT (waste_type, treatment_method, source, country_code) DO NOTHING;
