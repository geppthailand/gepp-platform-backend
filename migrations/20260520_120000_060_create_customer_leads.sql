-- Migration: Create customer_leads table for marketing-site lead capture.
-- Date: 2026-05-20
-- Description:
--   Captures public lead submissions (e.g. gepp.me Contact form) without
--   needing org membership. Each row is tagged with a `source` column so we
--   can grow the channel mix later (landing-page, event, partner-referral...)
--   without schema changes.

CREATE TABLE IF NOT EXISTS customer_leads (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT        NOT NULL,
    email           TEXT        NOT NULL,
    company         TEXT        NOT NULL,
    lead_type       TEXT,
    message         TEXT,
    source          TEXT        NOT NULL DEFAULT 'landing-page',
    origin          TEXT,
    ip_address      TEXT,
    user_agent      TEXT,
    referrer        TEXT,
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_customer_leads_email      ON customer_leads(email);
CREATE INDEX IF NOT EXISTS idx_customer_leads_source     ON customer_leads(source);
CREATE INDEX IF NOT EXISTS idx_customer_leads_created_at ON customer_leads(created_at DESC);
