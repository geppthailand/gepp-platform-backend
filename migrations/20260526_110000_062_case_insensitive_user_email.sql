-- Enforce case-insensitive user email identity for login and registration.
-- Existing active duplicates must be resolved before this migration can create
-- the unique index.

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_locations_email_ci_user_active
    ON user_locations (lower(email))
    WHERE is_user = TRUE
      AND deleted_date IS NULL
      AND email IS NOT NULL;
