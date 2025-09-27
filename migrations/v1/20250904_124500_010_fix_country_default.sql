-- Migration: Fix country_id default value and foreign key constraints
-- Date: 2025-01-09
-- Description: Fix the hardcoded country_id default to use actual Thailand ID

-- First, ensure Thailand exists in location_countries
INSERT INTO location_countries (id, name_en, name_th, code, phone_code, currency_code, created_date, updated_date, is_active) 
VALUES (212, 'Thailand', 'ประเทศไทย', 'TH', '+66', 'THB', NOW(), NOW(), TRUE)
ON CONFLICT (id) DO UPDATE SET
    name_en = EXCLUDED.name_en,
    name_th = EXCLUDED.name_th,
    code = EXCLUDED.code,
    phone_code = EXCLUDED.phone_code,
    currency_code = EXCLUDED.currency_code,
    updated_date = NOW();

-- Ensure currency with ID 12 exists (THB)
INSERT INTO currencies (id, name_en, name_th, code, symbol, created_date, updated_date, is_active)
VALUES (12, 'Thai Baht', 'บาทไทย', 'THB', '฿', NOW(), NOW(), TRUE)
ON CONFLICT (id) DO UPDATE SET
    name_en = EXCLUDED.name_en,
    name_th = EXCLUDED.name_th,
    code = EXCLUDED.code,
    symbol = EXCLUDED.symbol,
    updated_date = NOW();

-- Also insert other common countries with predictable IDs
INSERT INTO location_countries (id, name_en, name_th, code, phone_code, currency_code, created_date, updated_date, is_active) VALUES
    (1, 'United States', 'สหรัฐอเมริกา', 'US', '+1', 'USD', NOW(), NOW(), TRUE),
    (65, 'Singapore', 'สิงคโปร์', 'SG', '+65', 'SGD', NOW(), NOW(), TRUE)
ON CONFLICT (id) DO UPDATE SET
    name_en = EXCLUDED.name_en,
    name_th = EXCLUDED.name_th,
    code = EXCLUDED.code,
    phone_code = EXCLUDED.phone_code,
    currency_code = EXCLUDED.currency_code,
    updated_date = NOW();

-- Insert corresponding currencies with predictable IDs
INSERT INTO currencies (id, name_en, name_th, code, symbol, created_date, updated_date, is_active) VALUES
    (1, 'US Dollar', 'ดอลลาร์สหรัฐ', 'USD', '$', NOW(), NOW(), TRUE),
    (65, 'Singapore Dollar', 'ดอลลาร์สิงคโปร์', 'SGD', 'S$', NOW(), NOW(), TRUE)
ON CONFLICT (id) DO UPDATE SET
    name_en = EXCLUDED.name_en,
    name_th = EXCLUDED.name_th,
    code = EXCLUDED.code,
    symbol = EXCLUDED.symbol,
    updated_date = NOW();