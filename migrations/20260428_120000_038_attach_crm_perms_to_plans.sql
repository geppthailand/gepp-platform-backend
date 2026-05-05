-- ──────────────────────────────────────────────────────────────────────────────
-- 038 — Attach CRM / Marketing permissions to subscription_plans.permission_ids
--
-- Sprint 0 quick-fix from CRM gap analysis (docs/stories/crm-marketing-gap-analysis/).
--
-- Why: CRM permission codes (sidebar.marketing + 7 feature.marketing.*) were
--      seeded by migration 037 into `system_permissions`, but never attached to
--      any subscription_plans.permission_ids JSONB array. Without this, any
--      frontend gating that checks plan-derived permissions would hide the
--      Marketing tab even for plan holders.
--
-- What: Idempotently appends each missing CRM permission ID to every plan row.
--       Super-admin / gepp-admin login bypasses plan permissions, so this is
--       only relevant for org-user access (currently unused; future-proofing).
--
-- Idempotency: Each ID is added only if not already present in the JSONB array.
--              Safe to re-run.
-- ──────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    perm_ids INT[];
    pid INT;
BEGIN
    -- Resolve the 8 CRM permission IDs by code so the migration is robust to
    -- ID drift between environments.
    SELECT ARRAY_AGG(id ORDER BY id)
      INTO perm_ids
      FROM system_permissions
     WHERE code IN (
         'sidebar.marketing',
         'feature.marketing.view',
         'feature.marketing.analytics.view',
         'feature.marketing.segments.manage',
         'feature.marketing.templates.manage',
         'feature.marketing.campaigns.manage',
         'feature.marketing.email_lists.manage',
         'feature.marketing.ai.generate'
     );

    IF perm_ids IS NULL OR array_length(perm_ids, 1) = 0 THEN
        RAISE NOTICE 'No CRM permissions found in system_permissions; skipping.';
        RETURN;
    END IF;

    RAISE NOTICE 'Attaching CRM permission IDs % to all subscription_plans rows', perm_ids;

    -- For each permission ID, append to every plan that doesn't already have it.
    FOREACH pid IN ARRAY perm_ids LOOP
        UPDATE subscription_plans
           SET permission_ids = COALESCE(permission_ids, '[]'::jsonb) || to_jsonb(pid)
         WHERE NOT (COALESCE(permission_ids, '[]'::jsonb) @> to_jsonb(pid));
    END LOOP;
END $$;

-- Sanity check (logged by run_local.sh): every plan should now include all 8 perms.
-- Uncomment locally to verify:
--   SELECT id, name, jsonb_array_length(permission_ids) AS perm_count
--     FROM subscription_plans ORDER BY id;
