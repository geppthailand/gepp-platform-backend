-- Bind active organizations with no current subscription to the Free Plan.
-- Backoffice /v3-organizations/show expects organizations.subscription_id to
-- point at the org's current subscription row.

DO $$
DECLARE
    free_plan_id BIGINT;
    rebound_count INTEGER := 0;
    created_count INTEGER := 0;
BEGIN
    SELECT id
      INTO free_plan_id
      FROM subscription_plans
     WHERE name = 'free'
       AND is_active = TRUE
     ORDER BY created_date DESC
     LIMIT 1;

    IF free_plan_id IS NULL THEN
        SELECT id
          INTO free_plan_id
          FROM subscription_plans
         WHERE is_default = TRUE
           AND is_active = TRUE
         ORDER BY created_date DESC
         LIMIT 1;
    END IF;

    IF free_plan_id IS NULL THEN
        UPDATE subscription_plans
           SET is_default = FALSE,
               updated_date = NOW()
         WHERE is_default = TRUE;

        INSERT INTO subscription_plans (
            name,
            display_name,
            description,
            price_monthly,
            price_yearly,
            max_users,
            max_transactions_monthly,
            max_storage_gb,
            max_api_calls_daily,
            features,
            permission_ids,
            is_default
        )
        VALUES (
            'free',
            'Free Plan',
            'Basic features for getting started',
            0,
            0,
            5,
            100,
            1,
            1000,
            '["Basic waste tracking", "Up to 5 users", "100 transactions/month", "1GB storage", "Basic reporting"]'::json,
            '[]'::json,
            TRUE
        )
        RETURNING id INTO free_plan_id;
    ELSE
        UPDATE subscription_plans
           SET is_default = FALSE,
               updated_date = NOW()
         WHERE is_default = TRUE
           AND id != free_plan_id;

        UPDATE subscription_plans
           SET is_default = TRUE,
               updated_date = NOW()
         WHERE id = free_plan_id
           AND is_default = FALSE;
    END IF;

    WITH latest_active_subscription AS (
        SELECT DISTINCT ON (organization_id)
               id,
               organization_id
          FROM subscriptions
         WHERE status = 'active'
           AND is_active = TRUE
         ORDER BY organization_id, id DESC
    )
    UPDATE organizations org
       SET subscription_id = latest_active_subscription.id,
           updated_date = NOW()
      FROM latest_active_subscription
     WHERE org.id = latest_active_subscription.organization_id
       AND org.is_active = TRUE
       AND (
           org.subscription_id IS NULL
           OR NOT EXISTS (
               SELECT 1
                 FROM subscriptions current_sub
                WHERE current_sub.id = org.subscription_id
                  AND current_sub.organization_id = org.id
           )
       );

    GET DIAGNOSTICS rebound_count = ROW_COUNT;

    WITH orgs_without_subscription AS (
        SELECT org.id AS organization_id,
               COUNT(active_users.id)::INTEGER AS users_count
          FROM organizations org
          LEFT JOIN subscriptions current_sub
                 ON current_sub.id = org.subscription_id
          LEFT JOIN user_locations active_users
                 ON active_users.organization_id = org.id
                AND active_users.is_user = TRUE
                AND active_users.is_active = TRUE
                AND active_users.deleted_date IS NULL
         WHERE org.is_active = TRUE
           AND (
               org.subscription_id IS NULL
               OR current_sub.id IS NULL
               OR current_sub.organization_id != org.id
           )
         GROUP BY org.id
    ),
    inserted_subscriptions AS (
        INSERT INTO subscriptions (
            organization_id,
            plan_id,
            status,
            current_period_starts_at,
            current_period_ends_at,
            users_count
        )
        SELECT organization_id,
               free_plan_id,
               'active',
               NOW(),
               NOW() + INTERVAL '30 days',
               users_count
          FROM orgs_without_subscription
        RETURNING id, organization_id
    )
    UPDATE organizations org
       SET subscription_id = inserted_subscriptions.id,
           updated_date = NOW()
      FROM inserted_subscriptions
     WHERE org.id = inserted_subscriptions.organization_id;

    GET DIAGNOSTICS created_count = ROW_COUNT;

    RAISE NOTICE
        'Bound organizations to Free Plan: reused active subscriptions %, created free subscriptions %',
        rebound_count,
        created_count;
END $$;
