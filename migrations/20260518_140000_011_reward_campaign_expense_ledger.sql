-- ============================================================
-- B2B2C Rewards System — Campaign Expense Ledger
-- Date: 2026-05-18
-- Purpose:
--   Per-campaign expense ledger (Manpower / Transport / Marketing / etc.). The "ของรางวัล"
--   (inventory) category is system-managed and locked — its amount is computed from
--   inventory deposits, not entered manually.
--
-- Tables:
--   reward_expense_categories — org-managed (mirrors reward_catalog_categories pattern)
--     · "ของรางวัล" is_inventory=true + is_system=true → can't be edited/deleted from UI
--   reward_campaign_expenses  — per-entry ledger (entry-level granularity)
--
-- Default categories are seeded lazily by the service on first GET — no seed in this
-- migration to keep it idempotent and avoid org-scan loops.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS reward_expense_categories (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(100) NOT NULL,
    -- locked "ของรางวัล" auto-mapped from inventory deposits
    is_inventory BOOLEAN NOT NULL DEFAULT FALSE,
    -- system rows (cannot be deleted from UI)
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    created_by BIGINT,
    updated_by BIGINT
);
CREATE INDEX IF NOT EXISTS idx_reward_expense_categories_org
    ON reward_expense_categories (organization_id) WHERE deleted_date IS NULL;
-- Partial unique to prevent the "ของรางวัล" inventory row from being duplicated per org
CREATE UNIQUE INDEX IF NOT EXISTS uq_reward_expense_categories_inventory
    ON reward_expense_categories (organization_id)
    WHERE is_inventory = TRUE AND deleted_date IS NULL;

CREATE TABLE IF NOT EXISTS reward_campaign_expenses (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    reward_campaign_id BIGINT NOT NULL REFERENCES reward_campaigns(id),
    expense_category_id BIGINT NOT NULL REFERENCES reward_expense_categories(id),
    amount_baht DECIMAL(12, 2) NOT NULL,
    expense_date DATE NOT NULL,
    vendor VARCHAR(255),
    note TEXT,
    receipt_file_id BIGINT,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    created_by BIGINT,
    updated_by BIGINT
);
CREATE INDEX IF NOT EXISTS idx_reward_campaign_expenses_campaign
    ON reward_campaign_expenses (reward_campaign_id, deleted_date);
CREATE INDEX IF NOT EXISTS idx_reward_campaign_expenses_category
    ON reward_campaign_expenses (expense_category_id, deleted_date);
CREATE INDEX IF NOT EXISTS idx_reward_campaign_expenses_org_date
    ON reward_campaign_expenses (organization_id, expense_date) WHERE deleted_date IS NULL;

COMMENT ON TABLE reward_expense_categories IS
    'Org-managed expense categories for campaign cost tracking (Manpower / Transport / etc.)';
COMMENT ON TABLE reward_campaign_expenses IS
    'Per-campaign expense ledger entries (entry-level granularity, manual admin input).';
COMMENT ON COLUMN reward_expense_categories.is_inventory IS
    'TRUE for the locked "ของรางวัล" category — its amount is computed from inventory deposits, not from this ledger.';

COMMIT;
