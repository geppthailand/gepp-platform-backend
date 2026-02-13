-- Migration: Create notifications table
-- Date: 2026-01-28
-- Description: Stores notification records; resource is flexible JSON for backend use; notification_type references organization_notification_settings

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    resource JSONB NOT NULL DEFAULT '{}'::jsonb,
    notification_type VARCHAR(50) NOT NULL,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_notifications_created_by_id ON notifications(created_by_id);
CREATE INDEX IF NOT EXISTS idx_notifications_notification_type ON notifications(notification_type);
CREATE INDEX IF NOT EXISTS idx_notifications_deleted ON notifications(deleted_date) WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_resource ON notifications USING GIN(resource);

-- Add comments
COMMENT ON TABLE notifications IS 'Notification records; resource holds flexible JSON (e.g. transaction_id, etc.) for backend use';
COMMENT ON COLUMN notifications.resource IS 'Flexible JSON object for backend use (e.g. { transaction_id: 123 })';
COMMENT ON COLUMN notifications.notification_type IS 'Event type (e.g. CREATE_ITEM, UPDATE_ITEM)';
