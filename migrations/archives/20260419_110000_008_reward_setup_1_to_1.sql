-- Migration: enforce 1 RewardSetup per Organization (hard constraint)
-- Context: reward_setup has been used as 1:1 per org in practice (setup_service.get_setup() auto-creates),
--          but there was no DB-level constraint. Adding a partial unique index locks the invariant
--          while respecting soft-delete semantics.

BEGIN;

-- Safety check: refuse to proceed if any org currently has >1 active setup row.
DO $$
DECLARE
    offenders INT;
BEGIN
    SELECT COUNT(*) INTO offenders FROM (
        SELECT organization_id
        FROM reward_setup
        WHERE deleted_date IS NULL
        GROUP BY organization_id
        HAVING COUNT(*) > 1
    ) t;

    IF offenders > 0 THEN
        RAISE EXCEPTION
            'Migration blocked: % organizations have >1 active reward_setup row. Clean up duplicates first.',
            offenders;
    END IF;
END $$;

-- Partial unique index respects soft-delete: a new row can be created after soft-deleting the old one.
CREATE UNIQUE INDEX IF NOT EXISTS reward_setup_org_unique
    ON reward_setup (organization_id)
    WHERE deleted_date IS NULL;

COMMIT;
