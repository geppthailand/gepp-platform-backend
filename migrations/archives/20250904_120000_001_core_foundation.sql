-- Migration: Core Foundation Tables
-- Date: 2025-01-09 12:00:00
-- Description: Creates foundation tables for locations, references, and core system data

-- Enable required extensions with fallback
DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EXCEPTION
    WHEN OTHERS THEN 
        RAISE NOTICE 'uuid-ossp extension not available, using alternative UUID generation';
END $$;

-- Create custom enum types if they don't exist
DO $$ BEGIN
    CREATE TYPE platform_enum AS ENUM ('NA', 'WEB', 'MOBILE', 'API');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create updated_date trigger function
CREATE OR REPLACE FUNCTION update_updated_date_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Location Countries
CREATE TABLE IF NOT EXISTS location_countries (
    id BIGSERIAL PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10) UNIQUE,
    region VARCHAR(100),
    continent VARCHAR(50),
    currency_code VARCHAR(10),
    phone_code VARCHAR(10),
    timezone VARCHAR(50),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Location Regions
CREATE TABLE IF NOT EXISTS location_regions (
    id BIGSERIAL PRIMARY KEY,
    country_id BIGINT NOT NULL REFERENCES location_countries(id),
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Location Provinces
CREATE TABLE IF NOT EXISTS location_provinces (
    id BIGSERIAL PRIMARY KEY,
    region_id BIGINT REFERENCES location_regions(id),
    country_id BIGINT NOT NULL REFERENCES location_countries(id),
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Location Districts
CREATE TABLE IF NOT EXISTS location_districts (
    id BIGSERIAL PRIMARY KEY,
    province_id BIGINT NOT NULL REFERENCES location_provinces(id),
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Location Subdistricts
CREATE TABLE IF NOT EXISTS location_subdistricts (
    id BIGSERIAL PRIMARY KEY,
    district_id BIGINT NOT NULL REFERENCES location_districts(id),
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10),
    postal_code VARCHAR(10),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Banks
CREATE TABLE IF NOT EXISTS banks (
    id BIGSERIAL PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10) UNIQUE,
    swift_code VARCHAR(20),
    country_id BIGINT REFERENCES location_countries(id),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Currencies
CREATE TABLE IF NOT EXISTS currencies (
    id BIGSERIAL PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10) UNIQUE,
    symbol VARCHAR(10),
    exchange_rate DECIMAL(15, 6) DEFAULT 1.0,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Nationalities
CREATE TABLE IF NOT EXISTS nationalities (
    id BIGSERIAL PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(10) UNIQUE,
    country_id BIGINT REFERENCES location_countries(id),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Phone Number Country Codes
CREATE TABLE IF NOT EXISTS phone_number_country_codes (
    id BIGSERIAL PRIMARY KEY,
    country_id BIGINT NOT NULL REFERENCES location_countries(id),
    code VARCHAR(10),
    country_name VARCHAR(255),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Material Categories
CREATE TABLE IF NOT EXISTS material_mains (
    id BIGSERIAL PRIMARY KEY,
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(50) UNIQUE,
    category VARCHAR(100),
    description TEXT,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Materials
CREATE TABLE IF NOT EXISTS materials (
    id BIGSERIAL PRIMARY KEY,
    main_id BIGINT REFERENCES material_mains(id),
    name_th VARCHAR(255),
    name_en VARCHAR(255),
    code VARCHAR(50) UNIQUE,
    density DECIMAL(10, 4),
    unit VARCHAR(20),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Locales
CREATE TABLE IF NOT EXISTS locales (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100),
    code VARCHAR(15) UNIQUE,
    language_code VARCHAR(10),
    country_code VARCHAR(10),
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_location_countries_code ON location_countries(code);
CREATE INDEX IF NOT EXISTS idx_location_countries_active ON location_countries(is_active);
CREATE INDEX IF NOT EXISTS idx_location_regions_country ON location_regions(country_id);
CREATE INDEX IF NOT EXISTS idx_location_provinces_region ON location_provinces(region_id);
CREATE INDEX IF NOT EXISTS idx_location_provinces_country ON location_provinces(country_id);
CREATE INDEX IF NOT EXISTS idx_location_districts_province ON location_districts(province_id);
CREATE INDEX IF NOT EXISTS idx_location_subdistricts_district ON location_subdistricts(district_id);
CREATE INDEX IF NOT EXISTS idx_banks_code ON banks(code);
CREATE INDEX IF NOT EXISTS idx_currencies_code ON currencies(code);
CREATE INDEX IF NOT EXISTS idx_nationalities_code ON nationalities(code);
CREATE INDEX IF NOT EXISTS idx_materials_main ON materials(main_id);
CREATE INDEX IF NOT EXISTS idx_materials_code ON materials(code);

-- Create triggers for updated_date columns
CREATE TRIGGER update_location_countries_updated_date BEFORE UPDATE ON location_countries
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_location_regions_updated_date BEFORE UPDATE ON location_regions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_location_provinces_updated_date BEFORE UPDATE ON location_provinces
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_location_districts_updated_date BEFORE UPDATE ON location_districts
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_location_subdistricts_updated_date BEFORE UPDATE ON location_subdistricts
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_banks_updated_date BEFORE UPDATE ON banks
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_currencies_updated_date BEFORE UPDATE ON currencies
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_nationalities_updated_date BEFORE UPDATE ON nationalities
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_material_mains_updated_date BEFORE UPDATE ON material_mains
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_materials_updated_date BEFORE UPDATE ON materials
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Insert default data
INSERT INTO location_countries (name_en, code, phone_code, currency_code) VALUES
    ('Thailand', 'TH', '+66', 'THB'),
    ('United States', 'US', '+1', 'USD'),
    ('Singapore', 'SG', '+65', 'SGD')
ON CONFLICT (code) DO NOTHING;

INSERT INTO currencies (name_en, code, symbol) VALUES
    ('Thai Baht', 'THB', '฿'),
    ('US Dollar', 'USD', '$'),
    ('Singapore Dollar', 'SGD', 'S$')
ON CONFLICT (code) DO NOTHING;