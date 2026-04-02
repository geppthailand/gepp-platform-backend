-- ============================================================================
-- Migration: Assign free subscription plan to all organizations
-- Date: 2026-03-30
-- Description:
--   1. Updates the active "free" plan to include ALL system_permission IDs
--   2. Creates an active subscription for every organization that lacks one
-- ============================================================================

-- 1. Populate the free plan's permission_ids with every active system_permission
UPDATE subscription_plans
SET    permission_ids = (
           SELECT COALESCE(jsonb_agg(id ORDER BY id), '[]'::jsonb)
           FROM   system_permissions
           WHERE  is_active = TRUE
       ),
       updated_date = NOW()
WHERE  name = 'free'
  AND  is_active = TRUE;

-- 2. Create an active subscription for every organization that does not have one
INSERT INTO subscriptions (
    organization_id,
    plan_id,
    status,
    is_active,
    created_date,
    updated_date
)
SELECT
    o.id,
    fp.id,
    'active',
    TRUE,
    NOW(),
    NOW()
FROM       organizations o
CROSS JOIN subscription_plans fp
WHERE  fp.name = 'free'
  AND  fp.is_active = TRUE
  AND  NOT EXISTS (
           SELECT 1
           FROM   subscriptions s
           WHERE  s.organization_id = o.id
             AND  s.status = 'active'
             AND  s.is_active = TRUE
       );
