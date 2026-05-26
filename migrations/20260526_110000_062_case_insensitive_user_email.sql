-- Normalize case-insensitive user email identity for login and registration.
-- If active duplicate emails already exist, keep the migration non-blocking:
-- create a diagnostic view plus lookup index, then add the unique index only
-- after duplicate rows have been resolved.

UPDATE user_locations
SET
    email = lower(trim(email)),
    username = CASE
        WHEN username IS NULL THEN username
        WHEN position('@' IN username) > 0 THEN lower(trim(username))
        ELSE username
    END,
    company_email = lower(trim(company_email)),
    updated_date = NOW()
WHERE is_user = TRUE
  AND deleted_date IS NULL
  AND (
      email IS DISTINCT FROM lower(trim(email))
      OR (
          username IS NOT NULL
          AND position('@' IN username) > 0
          AND username IS DISTINCT FROM lower(trim(username))
      )
      OR company_email IS DISTINCT FROM lower(trim(company_email))
  );

CREATE OR REPLACE VIEW user_locations_case_insensitive_email_duplicates AS
SELECT
    lower(email) AS email_key,
    count(*) AS active_user_count,
    array_agg(id ORDER BY id) AS user_location_ids,
    array_agg(display_name ORDER BY id) AS display_names,
    min(created_date) AS first_created_date,
    max(created_date) AS last_created_date
FROM user_locations
WHERE is_user = TRUE
  AND deleted_date IS NULL
  AND email IS NOT NULL
GROUP BY lower(email)
HAVING count(*) > 1;

CREATE INDEX IF NOT EXISTS idx_user_locations_email_ci_user_active_lookup
    ON user_locations (lower(email))
    WHERE is_user = TRUE
      AND deleted_date IS NULL
      AND email IS NOT NULL;

DO $$
DECLARE
    duplicate_key_count integer;
BEGIN
    SELECT count(*)
    INTO duplicate_key_count
    FROM user_locations_case_insensitive_email_duplicates;

    IF duplicate_key_count = 0 THEN
        EXECUTE 'DROP INDEX IF EXISTS idx_user_locations_email_ci_user_active_lookup';

        EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS idx_user_locations_email_ci_user_active
            ON user_locations (lower(email))
            WHERE is_user = TRUE
              AND deleted_date IS NULL
              AND email IS NOT NULL';
    ELSE
        RAISE NOTICE
            'Skipped idx_user_locations_email_ci_user_active because % duplicate lowercase email key(s) exist. Inspect user_locations_case_insensitive_email_duplicates, resolve duplicates, then create the unique index.',
            duplicate_key_count;
    END IF;
END $$;
