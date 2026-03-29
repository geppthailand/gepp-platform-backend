-- ============================================================================
-- Migration: Seed super-admin user for backoffice login
-- Date: 2026-03-28
-- Description:
--   1. Ensures platform_role column exists on user_locations
--   2. Inserts super-admin user manager@gepp.me (or updates if email exists)
-- ============================================================================

BEGIN;

-- 1. Ensure platform_role column exists (idempotent)
ALTER TABLE user_locations ADD COLUMN IF NOT EXISTS platform_role VARCHAR(50) DEFAULT NULL;

-- 2. Insert super-admin user only if not already exists (no unique constraint on email)
-- Password: 1qaz!QAZ (bcrypt hashed)
INSERT INTO user_locations (
    is_user,
    is_location,
    display_name,
    first_name,
    last_name,
    email,
    is_email_active,
    password,
    platform,
    platform_role,
    country_id,
    currency_id,
    locale,
    is_active,
    created_date,
    updated_date
)
SELECT
    TRUE,
    FALSE,
    'GEPP Admin',
    'GEPP',
    'Admin',
    'manager@gepp.me',
    TRUE,
    '$2b$12$4OY69MuBoOAvm/e8gDsVw.GRWuipIb9XxTfiArTIn0efbIyRMG/KW',
    'NA',
    'super-admin',
    212,
    12,
    'TH',
    TRUE,
    NOW(),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM user_locations WHERE email = 'manager@gepp.me'
);

-- If user already exists, ensure it has the correct platform_role and password
UPDATE user_locations
SET
    password = '$2b$12$4OY69MuBoOAvm/e8gDsVw.GRWuipIb9XxTfiArTIn0efbIyRMG/KW',
    platform_role = 'super-admin',
    is_user = TRUE,
    is_active = TRUE,
    updated_date = NOW()
WHERE email = 'manager@gepp.me';

COMMIT;
