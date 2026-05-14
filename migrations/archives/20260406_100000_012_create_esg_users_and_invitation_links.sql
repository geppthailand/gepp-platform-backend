-- =============================================
-- ESG Users: External platform users (LINE, WhatsApp, WeChat, etc.)
-- Separate from user_locations (desktop web users)
-- =============================================

CREATE TABLE IF NOT EXISTS esg_users (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id),
    platform VARCHAR(20) NOT NULL,             -- 'line', 'whatsapp', 'wechat', 'telegram'
    platform_user_id VARCHAR(255) NOT NULL,    -- LINE userId / WhatsApp number / etc.
    display_name VARCHAR(255),
    profile_image_url VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_esg_users_platform_user UNIQUE (platform, platform_user_id)
);

CREATE INDEX IF NOT EXISTS idx_esg_users_organization ON esg_users(organization_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_users_platform_user ON esg_users(platform, platform_user_id);

COMMENT ON TABLE esg_users IS 'External platform users for ESG (LINE, WhatsApp, WeChat). Separate from user_locations.';

-- =============================================
-- ESG External Invitation Links: platform-agnostic invitations
-- One link works for any platform (LINE, WhatsApp, WeChat, etc.)
-- =============================================

CREATE TABLE IF NOT EXISTS esg_external_invitation_links (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    invited_by_id BIGINT REFERENCES user_locations(id),
    token VARCHAR(64) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    used_by_esg_user_id BIGINT REFERENCES esg_users(id),
    used_by_platform VARCHAR(20),
    used_by_platform_user_id VARCHAR(255),
    used_by_display_name VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_esg_invitation_token UNIQUE (token)
);

CREATE INDEX IF NOT EXISTS idx_esg_invitation_token ON esg_external_invitation_links(token);
CREATE INDEX IF NOT EXISTS idx_esg_invitation_org ON esg_external_invitation_links(organization_id);

COMMENT ON TABLE esg_external_invitation_links IS 'Platform-agnostic invitation links for external users to join an organization.';

-- =============================================
-- Update esg_data_entries FK: user_id now references esg_users
-- =============================================

ALTER TABLE esg_data_entries DROP CONSTRAINT IF EXISTS esg_data_entries_user_id_fkey;
ALTER TABLE esg_data_entries ADD CONSTRAINT esg_data_entries_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES esg_users(id);
