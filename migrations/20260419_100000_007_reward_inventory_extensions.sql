-- ============================================================
-- B2B2C Rewards System — Reward Inventory Tab Extensions
-- Date: 2026-04-19
-- Purpose:
--   1. New table: reward_catalog_categories (org-managed preset list)
--   2. Extend reward_catalog: category_id, min_threshold, limit_per_user_per_campaign, status
--   3. Extend reward_stocks: ledger_type, transfer_group_id, receipt fields, admin_user_id
--   4. Backfill ledger_type from existing data
-- ============================================================

-- 1. Reward catalog categories (new)
CREATE TABLE IF NOT EXISTS reward_catalog_categories (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_reward_catalog_categories_org
    ON reward_catalog_categories(organization_id);

-- 2. reward_catalog: new columns
ALTER TABLE reward_catalog
    ADD COLUMN IF NOT EXISTS category_id BIGINT REFERENCES reward_catalog_categories(id),
    ADD COLUMN IF NOT EXISTS min_threshold INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS limit_per_user_per_campaign INTEGER,
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived'));

-- Migrate is_active → status (keep is_active as legacy flag)
UPDATE reward_catalog
   SET status = CASE WHEN is_active THEN 'active' ELSE 'archived' END
 WHERE status = 'active';  -- only touch rows that still have default

CREATE INDEX IF NOT EXISTS idx_reward_catalog_status ON reward_catalog(status);
CREATE INDEX IF NOT EXISTS idx_reward_catalog_category ON reward_catalog(category_id);

-- 3. reward_stocks: new columns for ledger enrichment + receipt tracking
ALTER TABLE reward_stocks
    ADD COLUMN IF NOT EXISTS ledger_type VARCHAR(20) NOT NULL DEFAULT 'deposit'
        CHECK (ledger_type IN ('deposit', 'withdraw', 'transfer', 'redeem', 'return')),
    ADD COLUMN IF NOT EXISTS transfer_group_id UUID,
    ADD COLUMN IF NOT EXISTS vendor VARCHAR(200),
    ADD COLUMN IF NOT EXISTS unit_price DECIMAL(12, 2),
    ADD COLUMN IF NOT EXISTS total_price DECIMAL(12, 2),
    ADD COLUMN IF NOT EXISTS receipt_file_id BIGINT,
    ADD COLUMN IF NOT EXISTS admin_user_id BIGINT;  -- no FK: platform users managed outside schema

-- Backfill ledger_type from existing data by inferring from (sign of values, campaign_id, note)
-- Pattern observed in stock_service.assign_to_campaign: uses note prefixes "[assign out]" / "[assign in]"
UPDATE reward_stocks
   SET ledger_type = 'transfer'
 WHERE (note LIKE '[assign out]%' OR note LIKE '[assign in]%');

UPDATE reward_stocks
   SET ledger_type = 'redeem'
 WHERE values < 0
   AND reward_user_id IS NOT NULL
   AND ledger_type = 'deposit';  -- redemptions set reward_user_id

UPDATE reward_stocks
   SET ledger_type = 'withdraw'
 WHERE values < 0
   AND reward_user_id IS NULL
   AND reward_campaign_id IS NULL
   AND ledger_type = 'deposit';

-- remaining rows with values > 0 and no campaign = deposits (default already correct)

CREATE INDEX IF NOT EXISTS idx_reward_stocks_ledger_type ON reward_stocks(ledger_type);
CREATE INDEX IF NOT EXISTS idx_reward_stocks_transfer_group ON reward_stocks(transfer_group_id);
CREATE INDEX IF NOT EXISTS idx_reward_stocks_admin_user ON reward_stocks(admin_user_id);
