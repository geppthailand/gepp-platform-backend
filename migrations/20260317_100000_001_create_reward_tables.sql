-- ============================================================
-- B2B2C Rewards System v2 — 14 Tables
-- ============================================================

-- Drop old reward tables (37 models → 14 new)
DROP TABLE IF EXISTS redemption_alerts CASCADE;
DROP TABLE IF EXISTS redemption_reports CASCADE;
DROP TABLE IF EXISTS redemption_batch_items CASCADE;
DROP TABLE IF EXISTS redemption_batches CASCADE;
DROP TABLE IF EXISTS redemption_documents CASCADE;
DROP TABLE IF EXISTS redemption_status_history CASCADE;
DROP TABLE IF EXISTS reward_wishlists CASCADE;
DROP TABLE IF EXISTS reward_inventory_logs CASCADE;
DROP TABLE IF EXISTS reward_promotions CASCADE;
DROP TABLE IF EXISTS reward_ratings CASCADE;
DROP TABLE IF EXISTS reward_categories CASCADE;
DROP TABLE IF EXISTS rewards CASCADE;
DROP TABLE IF EXISTS points_adjustments CASCADE;
DROP TABLE IF EXISTS points_promotions CASCADE;
DROP TABLE IF EXISTS points_tiers CASCADE;
DROP TABLE IF EXISTS user_point_transactions CASCADE;
DROP TABLE IF EXISTS claim_rules CASCADE;
DROP TABLE IF EXISTS user_points CASCADE;
DROP TABLE IF EXISTS reward_integrations CASCADE;
DROP TABLE IF EXISTS reward_audit_logs CASCADE;
DROP TABLE IF EXISTS reward_configurations CASCADE;
DROP TABLE IF EXISTS reward_notifications CASCADE;
DROP TABLE IF EXISTS reward_analytics CASCADE;
DROP TABLE IF EXISTS campaign_participants CASCADE;

-- Drop new tables too (for idempotent re-runs)
DROP TABLE IF EXISTS reward_campaign_droppoints CASCADE;
DROP TABLE IF EXISTS reward_redemptions CASCADE;
DROP TABLE IF EXISTS reward_point_transactions CASCADE;
DROP TABLE IF EXISTS reward_stocks CASCADE;
DROP TABLE IF EXISTS reward_campaign_catalog CASCADE;
DROP TABLE IF EXISTS reward_campaign_claims CASCADE;
DROP TABLE IF EXISTS organization_reward_users CASCADE;
DROP TABLE IF EXISTS droppoints CASCADE;
DROP TABLE IF EXISTS droppoint_types CASCADE;
DROP TABLE IF EXISTS reward_activity_materials CASCADE;
DROP TABLE IF EXISTS reward_campaigns CASCADE;
DROP TABLE IF EXISTS reward_catalog CASCADE;
DROP TABLE IF EXISTS reward_users CASCADE;
DROP TABLE IF EXISTS reward_setup CASCADE;

-- ============================================================
-- 1. reward_setup
-- ============================================================
CREATE TABLE reward_setup (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    program_name VARCHAR(255),
    program_name_local VARCHAR(255),
    points_rounding_method VARCHAR(20) DEFAULT 'round',
    points_per_transaction_limit INTEGER DEFAULT 100,
    points_per_day_limit INTEGER DEFAULT 500,
    timezone VARCHAR(100) DEFAULT 'Asia/Bangkok',
    cost_per_point NUMERIC(10,4) DEFAULT 0.25,
    qr_code_size INTEGER DEFAULT 200,
    qr_error_correction VARCHAR(1) DEFAULT 'M',
    receipt_template VARCHAR(255),
    hash VARCHAR(64) NOT NULL UNIQUE,
    welcome_message TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_setup_org ON reward_setup(organization_id);

-- ============================================================
-- 2. reward_catalog
-- ============================================================
CREATE TABLE reward_catalog (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    thumbnail_id BIGINT,
    images JSONB,
    price NUMERIC(10,2),
    unit VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_catalog_org ON reward_catalog(organization_id);

-- ============================================================
-- 3. reward_campaigns
-- ============================================================
CREATE TABLE reward_campaigns (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    image_id BIGINT,
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_campaigns_org ON reward_campaigns(organization_id);
CREATE INDEX idx_reward_campaigns_status ON reward_campaigns(status);

-- ============================================================
-- 4. reward_activity_materials
-- ============================================================
CREATE TABLE reward_activity_materials (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(20) NOT NULL,
    material_id BIGINT,
    image_id BIGINT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_activity_materials_org ON reward_activity_materials(organization_id);

-- ============================================================
-- 5. reward_campaign_claims
-- ============================================================
CREATE TABLE reward_campaign_claims (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    campaign_id BIGINT NOT NULL REFERENCES reward_campaigns(id),
    activity_material_id BIGINT NOT NULL REFERENCES reward_activity_materials(id),
    points NUMERIC(10,2) NOT NULL,
    max_claims_total INTEGER,
    max_claims_per_user INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_campaign_claims_campaign ON reward_campaign_claims(campaign_id);

-- ============================================================
-- 6. reward_campaign_catalog
-- ============================================================
CREATE TABLE reward_campaign_catalog (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES reward_campaigns(id),
    catalog_id BIGINT NOT NULL REFERENCES reward_catalog(id),
    points_cost INTEGER NOT NULL,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_campaign_catalog_campaign ON reward_campaign_catalog(campaign_id);

-- ============================================================
-- 7. reward_users
-- ============================================================
CREATE TABLE reward_users (
    id BIGSERIAL PRIMARY KEY,
    display_name VARCHAR(255),
    email VARCHAR(255),
    phone_number VARCHAR(50),
    address TEXT,
    line_user_id VARCHAR(255) UNIQUE,
    line_display_name VARCHAR(255),
    line_picture_url VARCHAR(500),
    line_status_message VARCHAR(500),
    whatsapp_user_id VARCHAR(255) UNIQUE,
    wechat_user_id VARCHAR(255) UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_users_line ON reward_users(line_user_id);

-- ============================================================
-- 8. organization_reward_users
-- ============================================================
CREATE TABLE organization_reward_users (
    id BIGSERIAL PRIMARY KEY,
    reward_user_id BIGINT NOT NULL REFERENCES reward_users(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_org_reward_users_org ON organization_reward_users(organization_id);
CREATE INDEX idx_org_reward_users_user ON organization_reward_users(reward_user_id);

-- ============================================================
-- 9. droppoint_types
-- ============================================================
CREATE TABLE droppoint_types (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

-- Seed data
INSERT INTO droppoint_types (name, description) VALUES
    ('reward_droppoint', 'Drop point for reward claim and redemption'),
    ('logistic_droppoint', 'Drop point for logistics and waste collection')
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 10. droppoints
-- ============================================================
CREATE TABLE droppoints (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    hash VARCHAR(64) NOT NULL UNIQUE,
    tag_id BIGINT,
    tenant_id BIGINT,
    user_location_id BIGINT,
    type VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_droppoints_org ON droppoints(organization_id);
CREATE INDEX idx_droppoints_hash ON droppoints(hash);

-- ============================================================
-- 11. reward_stocks
-- ============================================================
CREATE TABLE reward_stocks (
    id BIGSERIAL PRIMARY KEY,
    reward_catalog_id BIGINT NOT NULL REFERENCES reward_catalog(id),
    "values" INTEGER NOT NULL,
    reward_campaign_id BIGINT REFERENCES reward_campaigns(id),
    note TEXT,
    reward_user_id BIGINT REFERENCES reward_users(id),
    user_location_id BIGINT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_stocks_catalog ON reward_stocks(reward_catalog_id);
CREATE INDEX idx_reward_stocks_campaign ON reward_stocks(reward_campaign_id);

-- ============================================================
-- 12. reward_point_transactions
-- ============================================================
CREATE TABLE reward_point_transactions (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    reward_user_id BIGINT NOT NULL REFERENCES reward_users(id),
    points NUMERIC(10,2) NOT NULL,
    reward_activity_materials_id BIGINT REFERENCES reward_activity_materials(id),
    reward_campaign_id BIGINT REFERENCES reward_campaigns(id),
    value NUMERIC(10,4),
    unit VARCHAR(50),
    claimed_date TIMESTAMPTZ,
    staff_id BIGINT,
    droppoint_id BIGINT REFERENCES droppoints(id),
    reference_type VARCHAR(20),
    reference_id BIGINT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_pt_org ON reward_point_transactions(organization_id);
CREATE INDEX idx_reward_pt_user ON reward_point_transactions(reward_user_id);
CREATE INDEX idx_reward_pt_campaign ON reward_point_transactions(reward_campaign_id);

-- ============================================================
-- 13. reward_redemptions
-- ============================================================
CREATE TABLE reward_redemptions (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    reward_user_id BIGINT NOT NULL REFERENCES reward_users(id),
    reward_campaign_id BIGINT NOT NULL REFERENCES reward_campaigns(id),
    catalog_id BIGINT NOT NULL REFERENCES reward_catalog(id),
    points_redeemed INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'inprogress',
    stock_action_id BIGINT,
    hash VARCHAR(64) NOT NULL UNIQUE,
    staff_id BIGINT,
    note TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_redemptions_org ON reward_redemptions(organization_id);
CREATE INDEX idx_reward_redemptions_user ON reward_redemptions(reward_user_id);
CREATE INDEX idx_reward_redemptions_hash ON reward_redemptions(hash);
CREATE INDEX idx_reward_redemptions_status ON reward_redemptions(status);

-- ============================================================
-- 14. reward_campaign_droppoints
-- ============================================================
CREATE TABLE reward_campaign_droppoints (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES reward_campaigns(id),
    droppoint_id BIGINT NOT NULL REFERENCES droppoints(id),
    tag_id BIGINT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);
CREATE INDEX idx_reward_campaign_droppoints_campaign ON reward_campaign_droppoints(campaign_id);
CREATE INDEX idx_reward_campaign_droppoints_droppoint ON reward_campaign_droppoints(droppoint_id);
