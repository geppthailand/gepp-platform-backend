-- CRM: denormalized per-user + per-org profiles refreshed nightly
-- Source of truth for segment evaluation (never evaluate rules directly against crm_events)

CREATE TABLE IF NOT EXISTS crm_user_profiles (
    user_location_id BIGINT PRIMARY KEY REFERENCES user_locations(id) ON DELETE CASCADE,
    organization_id BIGINT REFERENCES organizations(id),
    last_login_at TIMESTAMP WITH TIME ZONE,
    days_since_last_login INT,
    login_count_30d INT NOT NULL DEFAULT 0,
    transaction_count_30d INT NOT NULL DEFAULT 0,
    transaction_count_lifetime INT NOT NULL DEFAULT 0,
    qr_count_30d INT NOT NULL DEFAULT 0,
    reward_claim_count_30d INT NOT NULL DEFAULT 0,
    iot_readings_count_30d INT NOT NULL DEFAULT 0,
    gri_submission_count_30d INT NOT NULL DEFAULT 0,
    traceability_count_30d INT NOT NULL DEFAULT 0,
    first_login_at TIMESTAMP WITH TIME ZONE,
    onboarded BOOLEAN NOT NULL DEFAULT FALSE,
    engagement_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    activity_tier VARCHAR(16) NOT NULL DEFAULT 'dormant',
    last_profile_refresh_at TIMESTAMP WITH TIME ZONE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crm_user_tier CHECK (activity_tier IN ('active', 'at_risk', 'dormant', 'lead'))
);

CREATE INDEX IF NOT EXISTS idx_crm_user_profiles_org ON crm_user_profiles (organization_id);
CREATE INDEX IF NOT EXISTS idx_crm_user_profiles_tier ON crm_user_profiles (activity_tier);
CREATE INDEX IF NOT EXISTS idx_crm_user_profiles_score ON crm_user_profiles (engagement_score DESC);
CREATE INDEX IF NOT EXISTS idx_crm_user_profiles_last_login ON crm_user_profiles (last_login_at DESC NULLS LAST);

COMMENT ON TABLE crm_user_profiles IS
    'Per-user CRM profile rolled up from crm_events nightly. Used as WHERE target for segment evaluation.';


CREATE TABLE IF NOT EXISTS crm_org_profiles (
    organization_id BIGINT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    active_user_count_30d INT NOT NULL DEFAULT 0,
    total_user_count INT NOT NULL DEFAULT 0,
    active_user_ratio NUMERIC(5,2) NOT NULL DEFAULT 0,
    transaction_count_30d INT NOT NULL DEFAULT 0,
    traceability_count_30d INT NOT NULL DEFAULT 0,
    gri_submission_count_30d INT NOT NULL DEFAULT 0,
    subscription_plan_id BIGINT,
    subscription_active BOOLEAN NOT NULL DEFAULT FALSE,
    quota_used_pct NUMERIC(5,2),
    activity_tier VARCHAR(16) NOT NULL DEFAULT 'dormant',
    last_activity_at TIMESTAMP WITH TIME ZONE,
    last_profile_refresh_at TIMESTAMP WITH TIME ZONE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crm_org_tier CHECK (activity_tier IN ('active', 'at_risk', 'dormant'))
);

CREATE INDEX IF NOT EXISTS idx_crm_org_profiles_tier ON crm_org_profiles (activity_tier);
CREATE INDEX IF NOT EXISTS idx_crm_org_profiles_active_ratio ON crm_org_profiles (active_user_ratio DESC);

COMMENT ON TABLE crm_org_profiles IS
    'Per-organization CRM profile rolled up from crm_events nightly';
