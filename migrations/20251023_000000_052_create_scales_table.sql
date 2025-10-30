-- Migration: Create scales table
-- Date: 2025-10-23
-- Version: 052

-- Create iot_devices table
CREATE TABLE IF NOT EXISTS iot_devices (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    device_type VARCHAR(64) NOT NULL DEFAULT 'scale',
    device_name VARCHAR(255) NOT NULL,
    mac_address_bluetooth VARCHAR(64),
    mac_address_tablet VARCHAR(64),
    password VARCHAR(255),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_iot_devices_active ON iot_devices (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_iot_devices_deleted ON iot_devices (deleted_date) WHERE deleted_date IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_iot_devices_mac_bluetooth ON iot_devices (mac_address_bluetooth) WHERE mac_address_bluetooth IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_iot_devices_mac_tablet ON iot_devices (mac_address_tablet) WHERE mac_address_tablet IS NOT NULL;

-- Comments
COMMENT ON TABLE iot_devices IS 'Stores IoT devices (e.g., scales, sensors) including optional MAC addresses';
COMMENT ON COLUMN iot_devices.device_type IS 'Type/category of the IoT device (e.g., scale, sensor, gateway)';
COMMENT ON COLUMN iot_devices.device_name IS 'Human-readable name for the IoT device';
COMMENT ON COLUMN iot_devices.mac_address_bluetooth IS 'Bluetooth MAC address of the device (unique when present)';
COMMENT ON COLUMN iot_devices.mac_address_tablet IS 'Tablet MAC address paired with the device (unique when present)';
COMMENT ON COLUMN iot_devices.password IS 'Hashed password for device authentication (never store plaintext)';

