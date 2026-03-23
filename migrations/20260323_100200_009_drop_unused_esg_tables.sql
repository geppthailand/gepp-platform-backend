-- ============================================================
-- Migration 009: Drop ESG tables no longer used by Data Insight
-- ============================================================
-- These tables are superseded by the new cascade extraction pipeline:
--   esg_waste_records      → replaced by esg_organization_data_extraction.datapoint_matches JSONB
--   esg_scope3_summaries   → replaced by completeness calculation from esg_data_category hierarchy
--   esg_emission_factors   → cascade extraction stores raw values, no CO2e lookup needed
-- ============================================================

BEGIN;

-- Drop in dependency order (child tables first)

-- 1. esg_waste_records (references esg_documents, esg_emission_factors, organizations)
DROP TABLE IF EXISTS esg_waste_records CASCADE;

-- 2. esg_scope3_summaries (references organizations)
DROP TABLE IF EXISTS esg_scope3_summaries CASCADE;

-- 3. esg_emission_factors (standalone reference table, was referenced by esg_waste_records)
DROP TABLE IF EXISTS esg_emission_factors CASCADE;

COMMIT;
