-- ============================================================
-- B2B2C Rewards System — Overview Dashboard Support
-- Date: 2026-04-17
-- Purpose: Add fields needed for Overview KPI dashboard:
--   1. reward_catalog.cost_baht     — actual cost in THB (for budget tracking)
--   2. reward_activity_materials.selling_price_per_kg — waste revenue
--   3. reward_activity_materials.ghg_factor          — GHG per kg (kg CO2e/kg)
--   4. reward_setup.reward_budget_total              — org-level budget cap
--   5. reward_setup.low_stock_threshold              — configurable alert threshold
-- ============================================================

-- 1. Catalog cost (for "งบรางวัล" financial KPI)
ALTER TABLE reward_catalog
    ADD COLUMN IF NOT EXISTS cost_baht DECIMAL(10,2);

-- 2. Activity material: selling price + GHG factor
ALTER TABLE reward_activity_materials
    ADD COLUMN IF NOT EXISTS selling_price_per_kg DECIMAL(10,2),
    ADD COLUMN IF NOT EXISTS ghg_factor DECIMAL(6,3);
    -- ghg_factor example: PET=1.5, aluminum=9.0 (kg CO2e per kg material)

-- 3. Reward setup: budget + low-stock threshold
ALTER TABLE reward_setup
    ADD COLUMN IF NOT EXISTS reward_budget_total DECIMAL(12,2),
    ADD COLUMN IF NOT EXISTS low_stock_threshold INTEGER DEFAULT 10;
    -- Default: items with total_stock < 10 flagged as low-stock
