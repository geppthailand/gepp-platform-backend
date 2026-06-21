-- Walk-in (non-LINE) member support.
-- Staff can register customers who have no LINE using their phone number as the
-- primary identifier. This adds the profile fields needed for walk-in registration
-- and PDPA consent tracking, plus a partial index for fast phone lookup.
--
-- NOTE: uniqueness on phone_number is enforced in application logic
-- (PublicRewardService), NOT a DB constraint. Existing rows may hold duplicate or
-- unnormalized phone values, so a hard UNIQUE constraint would risk breaking deploys.
-- Revisit a partial-unique index only after auditing existing data for duplicates.

ALTER TABLE reward_users
    ADD COLUMN IF NOT EXISTS date_of_birth       DATE,
    ADD COLUMN IF NOT EXISTS created_via         VARCHAR(20) NOT NULL DEFAULT 'line',
    ADD COLUMN IF NOT EXISTS created_by_staff_id BIGINT,
    ADD COLUMN IF NOT EXISTS pdpa_consent_at     TIMESTAMPTZ;

-- Fast phone lookup for walk-in resolve/register/merge-match (only live, phone-bearing rows).
CREATE INDEX IF NOT EXISTS idx_reward_users_phone
    ON reward_users (phone_number)
    WHERE phone_number IS NOT NULL AND deleted_date IS NULL;

COMMENT ON COLUMN reward_users.date_of_birth IS
    'Optional DOB for birthday campaigns; collected at registration / profile completion.';
COMMENT ON COLUMN reward_users.created_via IS
    'How the member was first created: line | staff_walkin | self_register. Existing rows default to line.';
COMMENT ON COLUMN reward_users.created_by_staff_id IS
    'organization_reward_users.id of the staff who registered a walk-in member (null for LINE self-registration).';
COMMENT ON COLUMN reward_users.pdpa_consent_at IS
    'Timestamp the member consented to PDPA; null = not yet consented.';
