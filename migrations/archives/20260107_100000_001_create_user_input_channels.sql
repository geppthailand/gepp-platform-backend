-- Migration: Create user_input_channels table
-- Date: 2026-01-07
-- Description: Creates the user_input_channels table for QR code-based mobile transaction input

-- Drop existing table if it exists with wrong schema
DROP TABLE IF EXISTS user_input_channels CASCADE;

-- Create user_input_channels table with full schema
CREATE TABLE IF NOT EXISTS user_input_channels (
    id BIGSERIAL PRIMARY KEY,

    -- User and organization linkage
    user_location_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- QR Code hash for unique identification
    hash VARCHAR(255) UNIQUE NOT NULL,

    -- Channel configuration
    channel_type VARCHAR(100) DEFAULT 'qr',  -- qr, api, etc.
    form_type VARCHAR(50) DEFAULT 'form',     -- form, daily, monthly

    -- Material configuration (JSON arrays)
    sub_material_ids JSONB DEFAULT '[]'::jsonb,              -- List of material IDs
    sub_material_destination_ids JSONB DEFAULT '[]'::jsonb,  -- List of destination location IDs

    -- Sub-user configuration
    subuser_names JSONB DEFAULT '[]'::jsonb,  -- List of sub-user names for login

    -- Feature flags
    enable_upload_image BOOLEAN DEFAULT FALSE,
    required_tag BOOLEAN DEFAULT FALSE,
    is_drop_off_point BOOLEAN DEFAULT FALSE,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_input_channels_user_location_id ON user_input_channels(user_location_id);
CREATE INDEX IF NOT EXISTS idx_user_input_channels_organization_id ON user_input_channels(organization_id);
CREATE INDEX IF NOT EXISTS idx_user_input_channels_hash ON user_input_channels(hash);
CREATE INDEX IF NOT EXISTS idx_user_input_channels_is_active ON user_input_channels(is_active);
CREATE INDEX IF NOT EXISTS idx_user_input_channels_deleted_date ON user_input_channels(deleted_date) WHERE deleted_date IS NULL;

-- Add comments for documentation
COMMENT ON TABLE user_input_channels IS 'Stores QR code-based input channel configurations for mobile transaction input';
COMMENT ON COLUMN user_input_channels.hash IS 'Unique QR code hash for public access';
COMMENT ON COLUMN user_input_channels.channel_type IS 'Type of input channel: qr, api, etc.';
COMMENT ON COLUMN user_input_channels.form_type IS 'Form type: form (standard), daily, monthly';
COMMENT ON COLUMN user_input_channels.sub_material_ids IS 'JSON array of material IDs available for input';
COMMENT ON COLUMN user_input_channels.sub_material_destination_ids IS 'JSON array of destination location IDs corresponding to materials';
COMMENT ON COLUMN user_input_channels.subuser_names IS 'JSON array of sub-user names allowed to use this channel';
COMMENT ON COLUMN user_input_channels.enable_upload_image IS 'Enable image upload for transaction evidence';
COMMENT ON COLUMN user_input_channels.required_tag IS 'Require location tag selection';
COMMENT ON COLUMN user_input_channels.is_drop_off_point IS 'Enable drop-off point mode';
