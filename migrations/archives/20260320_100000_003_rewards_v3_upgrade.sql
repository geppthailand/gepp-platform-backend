-- ============================================================
-- B2B2C Rewards System v3 Upgrade
-- Date: 2026-03-20
-- Changes:
--   1. reward_staff_invites table (staff invite deep link)
--   2. hash column on reward_campaign_droppoints (campaign+droppoint QR)
--   3. redemption_group_hash on reward_redemptions (cart single QR)
--   4. image_ids on reward_point_transactions (claim photo)
--   5. transaction_method 'reward' support
-- ============================================================

-- ============================================================
-- 1. reward_staff_invites — One-time staff invite deep links
-- ============================================================
CREATE TABLE IF NOT EXISTS reward_staff_invites (
    id BIGSERIAL PRIMARY KEY,
    hash VARCHAR(64) NOT NULL UNIQUE,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    created_by_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    used_by_id BIGINT REFERENCES reward_users(id),
    used_date TIMESTAMPTZ,
    expires_date TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reward_staff_invites_hash
    ON reward_staff_invites(hash);
CREATE INDEX IF NOT EXISTS idx_reward_staff_invites_org
    ON reward_staff_invites(organization_id);

-- ============================================================
-- 2. Campaign-Droppoint hash — 1 QR per campaign+droppoint pair
-- ============================================================
ALTER TABLE reward_campaign_droppoints
    ADD COLUMN IF NOT EXISTS hash VARCHAR(64) UNIQUE;

-- Backfill existing records with generated hashes
UPDATE reward_campaign_droppoints
    SET hash = md5(random()::text || clock_timestamp()::text || id::text)
    WHERE hash IS NULL;

-- Make NOT NULL after backfill
ALTER TABLE reward_campaign_droppoints
    ALTER COLUMN hash SET NOT NULL;

-- ============================================================
-- 3. Redemption group hash — 1 QR per cart (multiple items)
-- ============================================================
ALTER TABLE reward_redemptions
    ADD COLUMN IF NOT EXISTS redemption_group_hash VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_reward_redemptions_group_hash
    ON reward_redemptions(redemption_group_hash);

-- ============================================================
-- 4. Image IDs on point transactions — claim photo support
-- ============================================================
ALTER TABLE reward_point_transactions
    ADD COLUMN IF NOT EXISTS image_ids JSONB;

-- ============================================================
-- 5. Transaction method 'reward' — allow reward claims to
--    create real transactions in the main transaction system
-- ============================================================
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_method;
ALTER TABLE transactions ADD CONSTRAINT chk_transaction_method
    CHECK (transaction_method IN (
        'origin', 'transport', 'transform',
        'qr_input', 'scale_input', 'reward'
    ));
