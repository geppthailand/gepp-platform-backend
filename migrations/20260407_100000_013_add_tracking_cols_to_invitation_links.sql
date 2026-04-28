-- Add tracking columns to esg_external_invitation_links
-- Records who used the invitation (platform, user ID, display name)

ALTER TABLE esg_external_invitation_links
    ADD COLUMN IF NOT EXISTS used_by_platform VARCHAR(20),
    ADD COLUMN IF NOT EXISTS used_by_platform_user_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS used_by_display_name VARCHAR(255);
