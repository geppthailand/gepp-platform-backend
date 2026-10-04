-- ============================================================================
-- Migration: Thai wording "ขยะรีไซเคิล" → "วัสดุรีไซเคิล" in material master data
-- Date: 2026-10-02
-- Description:
--   Platform-wide wording change: recyclables are "วัสดุรีไซเคิล" (material), not "ขยะ" (waste).
--   Scope is limited to the GLOBAL material master tables:
--     material_categories, main_materials, materials, base_materials.
--   Deliberately NOT touched (customer data / history):
--     transactions, transaction_records, transaction_audits, files, user_locations,
--     organization_setup, reward_* tables, org-owned material_tags / material_tag_groups.
--   English names ("Recyclable Waste") are unchanged.
-- Idempotent: re-running changes nothing.
-- ============================================================================

BEGIN;

UPDATE material_categories
SET name_th     = replace(name_th, 'ขยะรีไซเคิล', 'วัสดุรีไซเคิล'),
    description = replace(description, 'ขยะรีไซเคิล', 'วัสดุรีไซเคิล'),
    updated_date = NOW()
WHERE name_th LIKE '%ขยะรีไซเคิล%' OR description LIKE '%ขยะรีไซเคิล%';

UPDATE main_materials
SET name_th    = replace(name_th, 'ขยะรีไซเคิล', 'วัสดุรีไซเคิล'),
    name_local = replace(name_local, 'ขยะรีไซเคิล', 'วัสดุรีไซเคิล'),
    updated_date = NOW()
WHERE name_th LIKE '%ขยะรีไซเคิล%' OR name_local LIKE '%ขยะรีไซเคิล%';

UPDATE materials
SET name_th = replace(name_th, 'ขยะรีไซเคิล', 'วัสดุรีไซเคิล'),
    updated_date = NOW()
WHERE name_th LIKE '%ขยะรีไซเคิล%';

UPDATE base_materials
SET name_th = replace(name_th, 'ขยะรีไซเคิล', 'วัสดุรีไซเคิล'),
    updated_date = NOW()
WHERE name_th LIKE '%ขยะรีไซเคิล%';

COMMIT;
