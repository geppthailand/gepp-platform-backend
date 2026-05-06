-- Migration 056 — Per-organization Scope 3 focus mode + category whitelist
-- Date: 2026-05-06
--
-- Adds the platform-wide "Carbon Scope 3 only" focus mode at the
-- organization level. Two new columns on esg_organization_settings:
--
--   focus_mode                  TEXT — 'scope3_only' (default) | 'full_esg'
--   enabled_scope3_categories   JSONB — array of int category IDs (1..15)
--                                       — set-union'd from each teammate's
--                                       derived_categories on materiality
--                                       complete; falls back to a sensible
--                                       default of [1, 5, 6, 7] for
--                                       brand-new orgs.
--
-- Also adds an `is_scope3` boolean to esg_data_category so the LLM cascade
-- prompt can filter to Scope 3 rows server-side without hardcoding IDs.
-- The 15 GHG Protocol Scope 3 categories are documented at
-- docs/Services/GEPP-ESG/mvp1.1/scope3_deep_dive.html#L340-L484.
--
-- Both surfaces are hide-not-delete: switching focus_mode back to
-- 'full_esg' restores Social, Governance, and non-Scope-3 environmental
-- pillars in the UI and the prompt without code changes.

ALTER TABLE esg_organization_settings
    ADD COLUMN IF NOT EXISTS focus_mode VARCHAR(32) NOT NULL DEFAULT 'scope3_only',
    ADD COLUMN IF NOT EXISTS enabled_scope3_categories JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE esg_data_category
    ADD COLUMN IF NOT EXISTS is_scope3 BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS scope3_category_id INTEGER;

-- Index makes the LLM prompt narrowing query (filter by is_scope3 + IN list)
-- O(matches) instead of a full table scan.
CREATE INDEX IF NOT EXISTS esg_data_category_scope3
    ON esg_data_category (is_scope3, scope3_category_id)
    WHERE is_scope3 = TRUE;

COMMENT ON COLUMN esg_organization_settings.focus_mode IS 'Either ''scope3_only'' (default — show only Carbon Scope 3 surfaces) or ''full_esg'' (show full E/S/G triad). Read by frontend FocusGate + sidebar nav, and by backend extraction prompt builder.';
COMMENT ON COLUMN esg_organization_settings.enabled_scope3_categories IS 'Org-wide whitelist of Scope 3 category IDs (1..15) that drive every consumer: For You page, Data Warehouse hierarchy API, dashboard widgets, LLM cascade prompt menu, and _create_entry_from_extraction validation guard. Populated as the union of teammates'' derived_categories from the materiality wizard.';
COMMENT ON COLUMN esg_data_category.is_scope3 IS 'TRUE for the 15 GHG Protocol Scope 3 categories. Backfilled to TRUE for the seeded Scope 3 rows; FALSE for non-Scope-3 environmental and all S/G categories.';
COMMENT ON COLUMN esg_data_category.scope3_category_id IS 'When is_scope3 = TRUE, the GHG Protocol category number (1..15). NULL otherwise. Lets the prompt builder render the user-facing list with stable numbering even if the row id changes.';
