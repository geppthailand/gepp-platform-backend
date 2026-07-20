-- ============================================================
-- Teardown for seed_rewards_mock_v3.sql
-- Removes ONLY rows this seed created for :target_org (tracked in reward_mock_seed_ids)
-- plus any legacy '[MOCK]'-tagged rows. Real org data is never touched.
--
-- Run:  psql "$DATABASE_URL" -v target_org=2783 -f scripts/unseed_rewards_mock_v3.sql
-- ============================================================
\set ON_ERROR_STOP on
\if :{?target_org}
\else
  \set target_org 2783
\endif
\echo 'Un-seeding rewards demo for org' :target_org

BEGIN;

-- Registry-based removal (children -> parents)
DROP TABLE IF EXISTS _reg_camp; DROP TABLE IF EXISTS _reg_cat;
DROP TABLE IF EXISTS _reg_user; DROP TABLE IF EXISTS _reg_dp;
CREATE TEMP TABLE _reg_camp AS SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_campaigns';
CREATE TEMP TABLE _reg_cat  AS SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_catalog';
CREATE TEMP TABLE _reg_user AS SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_users';
CREATE TEMP TABLE _reg_dp   AS SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='droppoints';

DELETE FROM reward_campaign_expenses  WHERE reward_campaign_id IN (SELECT entity_id FROM _reg_camp);
DELETE FROM reward_redemptions        WHERE reward_campaign_id IN (SELECT entity_id FROM _reg_camp) OR reward_user_id IN (SELECT entity_id FROM _reg_user);
DELETE FROM reward_point_transactions WHERE reward_campaign_id IN (SELECT entity_id FROM _reg_camp) OR reward_user_id IN (SELECT entity_id FROM _reg_user);
DELETE FROM reward_stocks             WHERE reward_catalog_id IN (SELECT entity_id FROM _reg_cat) OR reward_campaign_id IN (SELECT entity_id FROM _reg_camp);
DELETE FROM reward_campaign_catalog   WHERE campaign_id IN (SELECT entity_id FROM _reg_camp) OR catalog_id IN (SELECT entity_id FROM _reg_cat);
DELETE FROM reward_campaign_targets   WHERE reward_campaign_id IN (SELECT entity_id FROM _reg_camp);
DELETE FROM reward_campaign_droppoints WHERE campaign_id IN (SELECT entity_id FROM _reg_camp) OR droppoint_id IN (SELECT entity_id FROM _reg_dp);
DELETE FROM reward_campaign_claims    WHERE campaign_id IN (SELECT entity_id FROM _reg_camp);
DELETE FROM reward_staff_invites      WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_staff_invites');
DELETE FROM reward_campaigns          WHERE id IN (SELECT entity_id FROM _reg_camp);
DELETE FROM droppoints                WHERE id IN (SELECT entity_id FROM _reg_dp);
DELETE FROM reward_catalog            WHERE id IN (SELECT entity_id FROM _reg_cat);
DELETE FROM reward_catalog_categories WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_catalog_categories');
DELETE FROM reward_activity_materials WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_activity_materials');
DELETE FROM reward_expense_categories WHERE id IN (SELECT entity_id FROM reward_mock_seed_ids WHERE organization_id=:target_org AND entity='reward_expense_categories');
DELETE FROM organization_reward_users WHERE reward_user_id IN (SELECT entity_id FROM _reg_user);
DELETE FROM reward_users              WHERE id IN (SELECT entity_id FROM _reg_user);
DELETE FROM reward_mock_seed_ids      WHERE organization_id=:target_org;

-- Legacy '[MOCK]' removal (older seed versions)
DELETE FROM reward_campaign_expenses WHERE organization_id=:target_org AND note LIKE '[MOCK]%';
DELETE FROM reward_expense_categories WHERE organization_id=:target_org AND name LIKE '[MOCK]%';
DELETE FROM reward_redemptions WHERE organization_id=:target_org AND note LIKE '[MOCK]%';
DELETE FROM reward_point_transactions WHERE organization_id=:target_org
   AND (reward_user_id IN (SELECT id FROM reward_users WHERE line_status_message='[MOCK]'||:target_org)
     OR reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%'));
DELETE FROM reward_stocks WHERE note LIKE '[MOCK]%' AND reward_catalog_id IN (SELECT id FROM reward_catalog WHERE organization_id=:target_org);
DELETE FROM reward_campaign_catalog WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%') OR catalog_id IN (SELECT id FROM reward_catalog WHERE organization_id=:target_org AND description LIKE '[MOCK]%');
DELETE FROM reward_campaign_targets WHERE reward_campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%');
DELETE FROM reward_campaign_droppoints WHERE campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%') OR droppoint_id IN (SELECT id FROM droppoints WHERE organization_id=:target_org AND name LIKE '[MOCK]%');
DELETE FROM reward_campaign_claims WHERE organization_id=:target_org AND campaign_id IN (SELECT id FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%');
DELETE FROM reward_campaigns WHERE organization_id=:target_org AND description LIKE '[MOCK]%';
DELETE FROM droppoints WHERE organization_id=:target_org AND name LIKE '[MOCK]%';
DELETE FROM reward_staff_invites WHERE organization_id=:target_org AND hash LIKE 'MOCK'||:target_org||'%';
DELETE FROM reward_catalog WHERE organization_id=:target_org AND description LIKE '[MOCK]%';
DELETE FROM reward_catalog_categories WHERE organization_id=:target_org AND description LIKE '[MOCK]%';
DELETE FROM reward_activity_materials WHERE organization_id=:target_org AND description LIKE '[MOCK]%';
DELETE FROM organization_reward_users WHERE organization_id=:target_org AND reward_user_id IN (SELECT id FROM reward_users WHERE line_status_message='[MOCK]'||:target_org);
DELETE FROM reward_users WHERE line_status_message='[MOCK]'||:target_org;

\echo 'Done. Remaining seeded rows for org (expect 0):'
SELECT COUNT(*) AS remaining_registry_rows FROM reward_mock_seed_ids WHERE organization_id=:target_org;

COMMIT;
