-- ============================================================
-- Rewards v3 — Phase 2: Activity Types master + campaign join
-- Date: 2026-05-05
-- Purpose: Activity-type campaigns track specific activities (BYO Bag, Refuse Plastic,
--          Clean Beach, etc.). Admins can manage activity types per organization,
--          and 7 system defaults (organization_id NULL) are seeded for all orgs.
-- ============================================================

-- 1. Master table
CREATE TABLE IF NOT EXISTS reward_activity_types (
    id           BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name         VARCHAR(100) NOT NULL,
    name_local   VARCHAR(100) NULL,
    emoji        VARCHAR(10)  NULL,
    color        VARCHAR(20)  NULL,
    description  TEXT         NULL,
    is_default   BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP WITH TIME ZONE NULL
);

CREATE INDEX IF NOT EXISTS idx_reward_activity_types_org
    ON reward_activity_types(organization_id) WHERE deleted_date IS NULL;

-- Unique name per org (NULL org_id = system defaults)
CREATE UNIQUE INDEX IF NOT EXISTS idx_reward_activity_types_org_name
    ON reward_activity_types(COALESCE(organization_id, 0), LOWER(name))
    WHERE deleted_date IS NULL;

COMMENT ON TABLE reward_activity_types IS
    'Activity types that activity-based campaigns can track (BYO Bag, Refuse Plastic, etc). NULL organization_id = system default available to all orgs.';

-- 2. Seed 7 system defaults (idempotent — only insert if not present)
INSERT INTO reward_activity_types (organization_id, name, name_local, emoji, color, is_default)
SELECT * FROM (
  VALUES
    (NULL::BIGINT, 'BYO Bag',           'ถือถุงผ้าเอง',     '🛍️', '#16A34A', TRUE),
    (NULL::BIGINT, 'BYO Cup',           'ถือแก้วเอง',       '☕', '#F59E0B', TRUE),
    (NULL::BIGINT, 'Refuse Plastic',    'ปฏิเสธพลาสติก',    '🚫', '#DC2626', TRUE),
    (NULL::BIGINT, 'Clean Beach',       'เก็บขยะชายหาด',    '🏖️', '#0EA5E9', TRUE),
    (NULL::BIGINT, 'Recycle Workshop',  'เวิร์กช็อปรีไซเคิล', '♻️', '#15803D', TRUE),
    (NULL::BIGINT, 'Training',          'อบรม / เทรนนิ่ง',  '📚', '#2563EB', TRUE),
    (NULL::BIGINT, 'Plant Tree',        'ปลูกต้นไม้',        '🌳', '#166534', TRUE)
) AS seed(organization_id, name, name_local, emoji, color, is_default)
WHERE NOT EXISTS (
  SELECT 1 FROM reward_activity_types
  WHERE organization_id IS NULL AND LOWER(name) = LOWER(seed.name) AND deleted_date IS NULL
);

-- 3. Campaign × Activity Types join
CREATE TABLE IF NOT EXISTS reward_campaign_activity_types (
    id                BIGSERIAL PRIMARY KEY,
    campaign_id       BIGINT NOT NULL REFERENCES reward_campaigns(id) ON DELETE CASCADE,
    activity_type_id  BIGINT NOT NULL REFERENCES reward_activity_types(id) ON DELETE CASCADE,
    points_per_event  DECIMAL(10, 2) NULL,  -- optional override; null = use claim rule
    created_date      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (campaign_id, activity_type_id)
);

CREATE INDEX IF NOT EXISTS idx_rcat_campaign ON reward_campaign_activity_types(campaign_id);
CREATE INDEX IF NOT EXISTS idx_rcat_activity_type ON reward_campaign_activity_types(activity_type_id);

COMMENT ON TABLE reward_campaign_activity_types IS
    'Many-to-many: which activity types each activity-based campaign tracks';
