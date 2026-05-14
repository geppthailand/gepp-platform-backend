-- ============================================================
-- esg_materiality_submissions — append-only tracking log
-- ============================================================
-- The existing `esg_user_materiality` row holds the user's CURRENT
-- (latest) state and is upserted on every assessment. This new table
-- is the immutable history: one row per submission, with the
-- `submitter_name` (LIFF "ชื่อ/ชื่อบริษัท" textbox), the LINE user id
-- ref, the answers/derived/scores at the moment of submit, and a
-- timestamp. We never UPDATE these rows — re-running the wizard
-- inserts a new row.
-- ============================================================

CREATE TABLE IF NOT EXISTS esg_materiality_submissions (
    id                    BIGSERIAL PRIMARY KEY,
    user_id               BIGINT,                                    -- EsgUser.id at the time of submit (nullable: web-only)
    organization_id       BIGINT REFERENCES organizations(id) ON DELETE SET NULL,

    -- Identity captured by the wizard's pre-assessment textbox
    submitter_name        VARCHAR(255) NOT NULL,                     -- "ชื่อ/ชื่อบริษัท" entered by the user

    -- Refs to LINE / LIFF identity. Same email can answer from
    -- different LINE accounts; both are captured.
    line_user_id          VARCHAR(64),                               -- LINE platform user id (Uxxx...)
    line_display_name     VARCHAR(255),                              -- LIFF profile.displayName (best-effort)

    -- Snapshot of the answers + derived output at submission time.
    questions_version     VARCHAR(32),
    answers               JSONB NOT NULL DEFAULT '{}'::jsonb,
    derived_categories    JSONB NOT NULL DEFAULT '[]'::jsonb,         -- e.g. [1,4,5,6]
    category_scores       JSONB NOT NULL DEFAULT '{}'::jsonb,         -- { "1": 0.82, ... }
    industry_other_text   VARCHAR(255),

    submitted_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Bookkeeping (BaseModel parity)
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_date          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_esg_mat_subs_org             ON esg_materiality_submissions(organization_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_mat_subs_user            ON esg_materiality_submissions(user_id)         WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_mat_subs_line_user       ON esg_materiality_submissions(line_user_id)    WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_esg_mat_subs_submitted_at    ON esg_materiality_submissions(submitted_at DESC);
