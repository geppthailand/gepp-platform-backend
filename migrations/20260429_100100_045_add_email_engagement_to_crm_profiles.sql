-- Migration 045 — Add email-engagement columns to crm_user_profiles and crm_org_profiles
-- Idempotent (ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS)
-- Sprint 4 / BE-2: drives the email rollup in profile_refresher.py and new
-- segment-evaluator fields (emails_received_30d, emails_opened_30d, etc.)

-- ─── crm_user_profiles ────────────────────────────────────────────────────────

ALTER TABLE crm_user_profiles
    ADD COLUMN IF NOT EXISTS emails_received_30d   INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS emails_opened_30d     INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS emails_clicked_30d    INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_email_received_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS last_email_opened_at  TIMESTAMPTZ NULL;

-- ─── crm_org_profiles ─────────────────────────────────────────────────────────

ALTER TABLE crm_org_profiles
    ADD COLUMN IF NOT EXISTS org_emails_received_30d   INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS org_emails_opened_30d     INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS org_emails_clicked_30d    INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS org_last_email_opened_at  TIMESTAMPTZ NULL;

-- ─── Indexes ──────────────────────────────────────────────────────────────────
-- Used by the segment evaluator for "last_email_opened_at IS NULL / > date" queries
-- and for sorting the user-profiles admin list by email engagement.

CREATE INDEX IF NOT EXISTS idx_user_profiles_last_email_opened
    ON crm_user_profiles (last_email_opened_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_user_profiles_email_engagement_30d
    ON crm_user_profiles (emails_opened_30d DESC);
