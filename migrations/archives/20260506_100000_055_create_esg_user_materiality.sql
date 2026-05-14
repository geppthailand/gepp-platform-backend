-- Migration 055 — Per-user Carbon Scope 3 materiality assessment
-- Date: 2026-05-06
--
-- Creates the table that stores each LIFF user's answers to the materiality
-- filter wizard. The wizard runs once per new LINE-registered user and
-- decides which of the 15 GHG-Protocol Scope 3 categories are material for
-- their business. Output `derived_categories` is also set-union'd into the
-- org-level whitelist on `esg_organization_settings.enabled_scope3_categories`
-- (see migration 056) which is what the LLM prompt and Data Warehouse read
-- from.
--
-- Resume-friendly: `last_question_id` lets the wizard pick up where the user
-- closed the LIFF mini-app. Autosave PATCHes overwrite `answers` after every
-- step.

CREATE TABLE IF NOT EXISTS esg_user_materiality (
    id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL,
    organization_id BIGINT NOT NULL,

    -- Schema version of the questions YAML at the time of save. Bumping
    -- questions.yaml `version:` allows us to detect outdated answers and
    -- prompt the user to retake.
    questions_version INTEGER NOT NULL DEFAULT 1,

    -- Full answers JSON: { q1_industry: { kind: 'single', selected, freeText? },
    --                     q2_offering: { kind: 'multi', selected: [...] }, ... }
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Derived after `complete()`: array of int category IDs (1..15).
    derived_categories JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Full per-category score map for analytics: { "1": 1.4, "5": 0.8, ... }
    category_scores JSONB,

    -- Free text from Q1 "Other" path so the user's input is preserved across
    -- sessions even if it doesn't map to a known industry id.
    industry_other_text VARCHAR(200),

    -- Resume bookmark: the last question id the user saw (so we can skip
    -- forward to it on next entry).
    last_question_id VARCHAR(64),

    -- Null until the user submits the final step. Once set, the gate stops
    -- redirecting them to the wizard.
    completed_at TIMESTAMPTZ,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMPTZ
);

-- One materiality record per (user, org). Re-takes update in place.
CREATE UNIQUE INDEX IF NOT EXISTS esg_user_materiality_user_org
    ON esg_user_materiality (user_id, organization_id)
    WHERE deleted_date IS NULL;

-- For the org-level set-union on completion + analytics queries.
CREATE INDEX IF NOT EXISTS esg_user_materiality_org_completed
    ON esg_user_materiality (organization_id, completed_at);

COMMENT ON TABLE esg_user_materiality IS 'Per-user Scope 3 materiality wizard state. Drives the LIFF first-run gate, the For You page, and (via union into org settings) the platform-wide Scope 3 category whitelist.';
COMMENT ON COLUMN esg_user_materiality.derived_categories IS 'Array of GHG Protocol Scope 3 category IDs (1..15) flagged "material" for this user after server-side scoring.';
COMMENT ON COLUMN esg_user_materiality.questions_version IS 'questions.yaml version at the time of save. Bumping causes users to be re-prompted.';
