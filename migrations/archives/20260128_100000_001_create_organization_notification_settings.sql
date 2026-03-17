-- Migration: Create organization_notification_settings table
-- Date: 2026-01-28
-- Description: Stores per-organization notification preferences by event and role (channel mask: EMAIL=1, BELL=2, BOTH=3)

CREATE TABLE IF NOT EXISTS organization_notification_settings (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event VARCHAR(50) NOT NULL,
    role_id BIGINT NOT NULL REFERENCES organization_roles(id) ON DELETE CASCADE,
    channels_mask INTEGER NOT NULL DEFAULT 0,
    email_time TIME,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    UNIQUE(organization_id, event, role_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_org_notification_settings_org_id ON organization_notification_settings(organization_id);
CREATE INDEX IF NOT EXISTS idx_org_notification_settings_event ON organization_notification_settings(event);
CREATE INDEX IF NOT EXISTS idx_org_notification_settings_role_id ON organization_notification_settings(role_id);
CREATE INDEX IF NOT EXISTS idx_org_notification_settings_deleted ON organization_notification_settings(deleted_date) WHERE deleted_date IS NULL;

-- Add comments
COMMENT ON TABLE organization_notification_settings IS 'Per-organization notification preferences by event and organization role (organization_roles.id)';
COMMENT ON COLUMN organization_notification_settings.event IS 'Event type (e.g. CREATE_ITEM, UPDATE_ITEM)';
COMMENT ON COLUMN organization_notification_settings.role_id IS 'Reference to organization_roles(id)';
COMMENT ON COLUMN organization_notification_settings.channels_mask IS 'Bitmask: EMAIL=1 (0001), BELL=2 (0010), BOTH=3 (0011)';
COMMENT ON COLUMN organization_notification_settings.email_time IS 'Time of day for email notifications (when EMAIL in channels_mask)';
