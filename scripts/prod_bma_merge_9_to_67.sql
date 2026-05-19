-- ============================================================================
-- v3 PROD — Merge org 9 (GEPP ADMIN, duplicate) into org 67 (BMA)
-- ============================================================================
-- Background:
--   v2 admin@gepp.me → v2 org 384 is the source for BMA data.
--   v3 has two orgs both representing it:
--     - org 67 "BMA"         : user bmadatabase@gepp.me, 1,683 txs (old sync)
--     - org 9  "GEPP ADMIN"  : user admin@gepp.me, 1,362 locs + 45 txs (synced
--                              yesterday after mis-mapped v2 384 → v3 9)
--   Correct state: everything under org 67, migration_id=384.
-- ============================================================================

BEGIN;

-- ------------------------------------------------------------------
-- 0. Capture counts BEFORE
-- ------------------------------------------------------------------
\echo '===== BEFORE ====='
SELECT 'org9 user_locations' AS item, COUNT(*) FROM user_locations WHERE organization_id=9
UNION ALL SELECT 'org9 txs',             COUNT(*) FROM transactions WHERE organization_id=9 AND is_active=true AND deleted_date IS NULL
UNION ALL SELECT 'org67 user_locations', COUNT(*) FROM user_locations WHERE organization_id=67
UNION ALL SELECT 'org67 txs',            COUNT(*) FROM transactions WHERE organization_id=67 AND is_active=true AND deleted_date IS NULL;

-- ------------------------------------------------------------------
-- 1. Move all user_locations from org 9 → org 67
-- ------------------------------------------------------------------
UPDATE user_locations SET organization_id = 67, updated_date = NOW()
WHERE organization_id = 9;

-- ------------------------------------------------------------------
-- 2. Move all transactions (and their records) from org 9 → org 67
--    transaction_records don't have organization_id — they belong via parent.
-- ------------------------------------------------------------------
UPDATE transactions SET organization_id = 67, updated_date = NOW()
WHERE organization_id = 9;

-- Move other BMA-data tables that carry organization_id
UPDATE files SET organization_id = 67 WHERE organization_id = 9;
UPDATE traceability_transaction_group SET organization_id = 67 WHERE organization_id = 9;

-- ------------------------------------------------------------------
-- 3. Merge org 9's active organization_setup tree into org 67's
--    - Take root_nodes + hub_node.children from org 9's active row
--    - Append to org 67's active row (dedup by nodeId)
-- ------------------------------------------------------------------
WITH src AS (
  SELECT root_nodes AS rn, hub_node AS hn
  FROM organization_setup WHERE organization_id=9 AND is_active=true LIMIT 1
),
dst AS (
  SELECT id, root_nodes, hub_node
  FROM organization_setup WHERE organization_id=67 AND is_active=true LIMIT 1
),
merged AS (
  SELECT
    dst.id,
    (
      SELECT jsonb_agg(node)
      FROM (
        SELECT DISTINCT ON (node->>'nodeId') node
        FROM (
          SELECT jsonb_array_elements(dst.root_nodes) AS node
          UNION ALL
          SELECT jsonb_array_elements(src.rn) AS node
        ) u
      ) d
    ) AS new_roots,
    jsonb_set(
      COALESCE(dst.hub_node, '{"children":[]}'::jsonb),
      '{children}',
      (
        SELECT jsonb_agg(node)
        FROM (
          SELECT DISTINCT ON (node->>'nodeId') node
          FROM (
            SELECT jsonb_array_elements(COALESCE(dst.hub_node->'children','[]'::jsonb)) AS node
            UNION ALL
            SELECT jsonb_array_elements(COALESCE(src.hn->'children','[]'::jsonb)) AS node
          ) u
        ) d
      )
    ) AS new_hub
  FROM src, dst
)
UPDATE organization_setup os SET
  root_nodes = m.new_roots,
  hub_node = m.new_hub,
  version = (os.version::numeric + 1)::text,
  updated_date = NOW()
FROM merged m WHERE os.id = m.id;

-- Deactivate org 9's setup rows (they're now empty-referenced)
UPDATE organization_setup SET is_active = false, updated_date = NOW()
WHERE organization_id = 9 AND is_active = true;

-- ------------------------------------------------------------------
-- 4. Fix migration_id on orgs
-- ------------------------------------------------------------------
UPDATE organizations SET migration_id = 384, updated_date = NOW() WHERE id = 67;
UPDATE organizations SET migration_id = NULL, updated_date = NOW() WHERE id = 9;

-- ------------------------------------------------------------------
-- 5. Fix v2_v3_mapping entries for organizations
-- ------------------------------------------------------------------
DELETE FROM v2_v3_mapping WHERE v2_table='organization' AND v2_id=3057 AND v3_id=67;
DELETE FROM v2_v3_mapping WHERE v2_table='organization' AND v2_id=384  AND v3_id=9;

INSERT INTO v2_v3_mapping (v2_table, v2_id, v3_table, v3_id, sync_status, last_sync_at, created_at)
VALUES ('organization', 384, 'organizations', 67, 'synced', NOW(), NOW())
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------------
-- 6. Soft-delete org 9 (leave the row for audit trail)
-- ------------------------------------------------------------------
UPDATE organizations SET is_active = false, deleted_date = NOW(), updated_date = NOW()
WHERE id = 9;

-- ------------------------------------------------------------------
-- 7. Verify AFTER
-- ------------------------------------------------------------------
\echo '===== AFTER ====='
SELECT 'org9 user_locations (should be 0)' AS item, COUNT(*) FROM user_locations WHERE organization_id=9
UNION ALL SELECT 'org9 txs (should be 0)',             COUNT(*) FROM transactions WHERE organization_id=9 AND is_active=true AND deleted_date IS NULL
UNION ALL SELECT 'org67 user_locations', COUNT(*) FROM user_locations WHERE organization_id=67
UNION ALL SELECT 'org67 txs',            COUNT(*) FROM transactions WHERE organization_id=67 AND is_active=true AND deleted_date IS NULL
UNION ALL SELECT 'org67 migration_id',   (SELECT migration_id FROM organizations WHERE id=67)
UNION ALL SELECT 'mapping v2 384→67',    (SELECT COUNT(*) FROM v2_v3_mapping WHERE v2_table='organization' AND v2_id=384 AND v3_id=67);

COMMIT;
