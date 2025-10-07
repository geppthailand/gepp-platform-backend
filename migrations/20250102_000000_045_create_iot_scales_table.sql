-- Migration: Create IoT Scales table
-- Created: 2025-01-02
-- Description: Create iot_scales table for digital scale devices

-- Create iot_scales table
CREATE TABLE iot_scales (
    id BIGSERIAL PRIMARY KEY,
    scale_name VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    owner_user_location_id BIGINT NOT NULL,
    location_point_id BIGINT NOT NULL,
    added_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_date TIMESTAMPTZ,
    mac_tablet VARCHAR(17),
    mac_scale VARCHAR(17),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    scale_type VARCHAR(100) NOT NULL DEFAULT 'digital',
    calibration_data TEXT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    
    -- Foreign key constraints
    CONSTRAINT fk_iot_scales_owner_user_location 
        FOREIGN KEY (owner_user_location_id) 
        REFERENCES user_locations(id) 
        ON DELETE RESTRICT,
        
    CONSTRAINT fk_iot_scales_location_point 
        FOREIGN KEY (location_point_id) 
        REFERENCES user_locations(id) 
        ON DELETE RESTRICT,
    
    -- Check constraints
    CONSTRAINT chk_iot_scales_status 
        CHECK (status IN ('active', 'maintenance', 'offline', 'inactive')),
        
    CONSTRAINT chk_iot_scales_scale_type 
        CHECK (scale_type IN ('digital', 'analog', 'hybrid')),
        
    CONSTRAINT chk_iot_scales_mac_format 
        CHECK (
            (mac_tablet IS NULL OR mac_tablet ~ '^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$') AND
            (mac_scale IS NULL OR mac_scale ~ '^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
        )
);

-- Create indexes for performance
CREATE INDEX idx_iot_scales_scale_name ON iot_scales(scale_name);
CREATE INDEX idx_iot_scales_owner ON iot_scales(owner_user_location_id);
CREATE INDEX idx_iot_scales_location ON iot_scales(location_point_id);
CREATE INDEX idx_iot_scales_status ON iot_scales(status);
CREATE INDEX idx_iot_scales_is_active ON iot_scales(is_active);
CREATE INDEX idx_iot_scales_end_date ON iot_scales(end_date);
CREATE INDEX idx_iot_scales_mac_tablet ON iot_scales(mac_tablet);
CREATE INDEX idx_iot_scales_mac_scale ON iot_scales(mac_scale);

-- Create trigger for updated_date
CREATE OR REPLACE FUNCTION update_iot_scales_updated_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_update_iot_scales_updated_date
    BEFORE UPDATE ON iot_scales
    FOR EACH ROW
    EXECUTE FUNCTION update_iot_scales_updated_date();

-- Add comments for documentation
COMMENT ON TABLE iot_scales IS 'IoT Scale devices that can authenticate and send weight data';
COMMENT ON COLUMN iot_scales.scale_name IS 'Unique name for the scale, used for authentication';
COMMENT ON COLUMN iot_scales.password IS 'Hashed password for scale authentication';
COMMENT ON COLUMN iot_scales.owner_user_location_id IS 'User who owns/manages this scale';
COMMENT ON COLUMN iot_scales.location_point_id IS 'Physical location where the scale is installed';
COMMENT ON COLUMN iot_scales.added_date IS 'Date when the scale was added to the system';
COMMENT ON COLUMN iot_scales.end_date IS 'Date when the scale access expires (NULL = no expiration)';
COMMENT ON COLUMN iot_scales.mac_tablet IS 'MAC address of the controlling tablet device';
COMMENT ON COLUMN iot_scales.mac_scale IS 'MAC address of the scale device itself';
COMMENT ON COLUMN iot_scales.status IS 'Current status of the scale (active, maintenance, offline, inactive)';
COMMENT ON COLUMN iot_scales.scale_type IS 'Type of scale (digital, analog, hybrid)';
COMMENT ON COLUMN iot_scales.calibration_data IS 'JSON string containing calibration settings';
COMMENT ON COLUMN iot_scales.notes IS 'Additional notes about the scale';
