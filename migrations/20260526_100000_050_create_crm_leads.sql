-- CRM Leads — Sprint 9 Phase 2 Lead Management System
-- Creates crm_leads, crm_public_rate_limits, and adds public_form_key to organizations.
-- All idempotent (IF NOT EXISTS / DO NOTHING / DO UPDATE).

-- ─── 1. public_form_key on organizations ─────────────────────────────────────
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS public_form_key VARCHAR(32);

-- Backfill existing rows with a unique random key (32 hex chars).
-- Uses a loop-free approach: gen_random_bytes needs pgcrypto or pg >= 13 + gen_random_uuid.
-- We use md5(random()::text || id::text) which is portable to all PG versions.
UPDATE organizations
   SET public_form_key = SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT || NOW()::TEXT), 1, 32)
 WHERE public_form_key IS NULL;

-- Now enforce NOT NULL + unique.
ALTER TABLE organizations
    ALTER COLUMN public_form_key SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'organizations_public_form_key_unique'
           AND conrelid = 'organizations'::regclass
    ) THEN
        ALTER TABLE organizations
            ADD CONSTRAINT organizations_public_form_key_unique UNIQUE (public_form_key);
    END IF;
END $$;

-- ─── 2. crm_leads ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crm_leads (
    id                  BIGSERIAL PRIMARY KEY,
    organization_id     BIGINT      NOT NULL REFERENCES organizations(id),
    email               VARCHAR(255) NOT NULL,
    first_name          VARCHAR(128),
    last_name           VARCHAR(128),
    company             VARCHAR(255),
    job_title           VARCHAR(255),
    phone               VARCHAR(64),
    country             VARCHAR(64),
    language            VARCHAR(8),
    source              VARCHAR(64),
    source_metadata     JSONB,
    status              VARCHAR(16)  NOT NULL DEFAULT 'new',
    status_changed_at   TIMESTAMPTZ,
    lead_score          INT          NOT NULL DEFAULT 0,
    owner_user_id       BIGINT       REFERENCES user_locations(id),
    tags                JSONB,
    notes               TEXT,
    converted_user_id   BIGINT       REFERENCES user_locations(id),
    converted_at        TIMESTAMPTZ,
    last_activity_at    TIMESTAMPTZ,
    created_date        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_date        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_date        TIMESTAMPTZ,
    CONSTRAINT crm_leads_org_email_unique UNIQUE (organization_id, email),
    CONSTRAINT crm_leads_status_check CHECK (
        status IN ('new','contacted','qualified','negotiating','customer','lost')
    ),
    CONSTRAINT crm_leads_source_check CHECK (
        source IN ('web_form','csv_import','api','manual','event','referral') OR source IS NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_crm_leads_org_status
    ON crm_leads (organization_id, status)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_leads_org_owner
    ON crm_leads (organization_id, owner_user_id)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_leads_org_last_activity
    ON crm_leads (organization_id, last_activity_at DESC NULLS LAST)
    WHERE deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_leads_email
    ON crm_leads (email);

COMMENT ON TABLE crm_leads IS
    'CRM lead records — one row per (organization, email) prospect. '
    'Emails stored lowercase. Status lifecycle: new → contacted → qualified → negotiating → customer | lost.';

-- ─── 3. crm_public_rate_limits ────────────────────────────────────────────────
-- Simple PG-table-based rate limiter for the public lead-capture endpoint.
-- Buckets: "minute" (10/min) and "day" (100/day) per IP.
CREATE TABLE IF NOT EXISTS crm_public_rate_limits (
    ip           VARCHAR(64) NOT NULL,
    bucket       VARCHAR(32) NOT NULL,
    counter      INT         NOT NULL DEFAULT 1,
    window_start TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (ip, bucket)
);

CREATE INDEX IF NOT EXISTS idx_crm_pub_rate_limits_window
    ON crm_public_rate_limits (window_start);

COMMENT ON TABLE crm_public_rate_limits IS
    'Per-IP rate-limit buckets for POST /api/public/leads. '
    'Buckets: minute (10/min), day (100/day). Old rows pruned on each check.';
