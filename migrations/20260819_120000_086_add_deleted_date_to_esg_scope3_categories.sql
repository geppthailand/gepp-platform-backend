-- ============================================================
-- Migration 086 — add deleted_date to esg_scope3_categories
-- ============================================================
-- Date: 2026-08-19
--
-- Why: models/esg/scope3_categories.py declares EsgScope3Category(Base, BaseModel)
-- and BaseModel contributes `deleted_date`, but the original CREATE TABLE in
-- 20260506_100200_057_seed_scope3_categories.sql omitted it. Any SELECT through
-- the ORM therefore failed with:
--
--   column esg_scope3_categories.deleted_date does not exist
--
-- This was invisible until /api/esg/supply-chain/scope3/categories became
-- reachable (the supply_chain module had never been wired into the ESG
-- dispatcher), so no query had ever hit the table via the ORM.
--
-- Additive and nullable — safe to run on a live database.
-- ============================================================

ALTER TABLE esg_scope3_categories
  ADD COLUMN IF NOT EXISTS deleted_date TIMESTAMPTZ NULL;

COMMENT ON COLUMN esg_scope3_categories.deleted_date IS
'Soft-delete marker. Present for BaseModel parity; the 15 GHG Protocol categories are reference data and are never deleted.';
