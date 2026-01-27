-- Migration: Add organization_id column to iot_devices table
-- Date: 2026-01-15
-- Description: Add organization_id column to associate IoT devices with organizations

-- Add organization_id column to iot_devices table
ALTER TABLE iot_devices
ADD COLUMN IF NOT EXISTS organization_id BIGINT;

-- Add foreign key constraint to organizations table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_iot_devices_organization_id'
        AND table_name = 'iot_devices'
    ) THEN
        ALTER TABLE iot_devices
        ADD CONSTRAINT fk_iot_devices_organization_id
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_iot_devices_organization_id
ON iot_devices(organization_id);

-- Add comment to the column
COMMENT ON COLUMN iot_devices.organization_id IS 'Organization that owns this IoT device (nullable)';
