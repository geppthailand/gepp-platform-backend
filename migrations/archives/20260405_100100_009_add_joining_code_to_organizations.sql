-- Add joining_code to organizations for LIFF onboarding flow
-- Users enter this 6-8 char code during first-time LIFF login to link to their company

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS joining_code VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_joining_code
    ON organizations (joining_code)
    WHERE joining_code IS NOT NULL;

COMMENT ON COLUMN organizations.joining_code IS 'Unique code users enter to join this organization (LIFF onboarding)';
