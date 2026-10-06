-- ============================================================================
-- Migration: Rewards "Admin tools" — admin-attached claims, non-staff self-submit,
--            pending review synced with waste transactions
-- Date: 2026-09-30
-- Description:
--   reward_setup.admin_tools_enabled      — master switch (OFF = today's behaviour).
--   organization_reward_users.claim_mode  — 'staff' (a staff member records for the
--                                           user, default) | 'non_staff' (the user
--                                           may submit claims themselves in the LIFF).
--   reward_point_transactions: source ('staff' | 'admin' | 'self'), the admin who
--                                           added it, and links to the waste
--                                           transaction/record it created.
--   reward_claim_requests                 — self-submitted claim items awaiting review.
--                                           A reward_point_transactions row exists only
--                                           while a request is approved, so balances,
--                                           GHG and every other aggregate never see
--                                           pending or rejected points.
-- ============================================================================

BEGIN;

ALTER TABLE reward_setup
    ADD COLUMN IF NOT EXISTS admin_tools_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE organization_reward_users
    ADD COLUMN IF NOT EXISTS claim_mode VARCHAR(16) NOT NULL DEFAULT 'staff';

ALTER TABLE reward_point_transactions
    ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'staff',
    ADD COLUMN IF NOT EXISTS created_by_user_location_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS transaction_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS transaction_record_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS note TEXT NULL;

CREATE TABLE IF NOT EXISTS reward_claim_requests (
    id                            BIGSERIAL PRIMARY KEY,
    organization_id               BIGINT NOT NULL REFERENCES organizations(id),
    reward_user_id                BIGINT NOT NULL REFERENCES reward_users(id),
    organization_reward_user_id   BIGINT NULL REFERENCES organization_reward_users(id),
    reward_campaign_id            BIGINT NOT NULL REFERENCES reward_campaigns(id),
    reward_activity_materials_id  BIGINT NOT NULL REFERENCES reward_activity_materials(id),
    droppoint_id                  BIGINT NULL REFERENCES droppoints(id),
    submission_uid                VARCHAR(36) NOT NULL,          -- groups the items of one submit
    value                         DECIMAL(10, 4) NOT NULL,
    unit                          VARCHAR(50) NULL,              -- 'kg' | 'times'
    requested_points              DECIMAL(10, 2) NOT NULL DEFAULT 0,
    status                        VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    image_ids                     JSONB NULL,
    note                          TEXT NULL,
    transaction_id                BIGINT NULL REFERENCES transactions(id),
    transaction_record_id         BIGINT NULL REFERENCES transaction_records(id),
    reward_point_transaction_id   BIGINT NULL,                   -- reward_point_transactions.id while approved (no FK: written in the same flush)
    reviewed_by_id                BIGINT NULL,                   -- user_locations.id
    reviewed_date                 TIMESTAMPTZ NULL,
    review_note                   TEXT NULL,
    submitted_date                TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active                     BOOLEAN NOT NULL DEFAULT TRUE,
    created_date                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_date                  TIMESTAMP NOT NULL DEFAULT now(),
    deleted_date                  TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_reward_claim_requests_campaign_status
    ON reward_claim_requests (reward_campaign_id, status) WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_reward_claim_requests_user
    ON reward_claim_requests (reward_user_id, organization_id) WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_reward_claim_requests_record
    ON reward_claim_requests (transaction_record_id) WHERE transaction_record_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_reward_claim_requests_transaction
    ON reward_claim_requests (transaction_id) WHERE transaction_id IS NOT NULL;

COMMIT;
