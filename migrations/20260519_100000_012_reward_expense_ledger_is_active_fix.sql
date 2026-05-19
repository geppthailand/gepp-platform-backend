-- ============================================================
-- B2B2C Rewards System — Expense Ledger is_active column fix
-- Date: 2026-05-19
-- Purpose:
--   Migration 011 created the expense ledger tables without the `is_active` column,
--   but BaseModel (which every reward model inherits) declares it as NOT NULL with
--   default TRUE. SQLAlchemy inserts referenced the column → UndefinedColumn error.
--   Adds the column with default TRUE for both tables.
-- ============================================================

BEGIN;

ALTER TABLE reward_expense_categories
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE reward_campaign_expenses
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;
