-- ============================================================================
-- Migration: Report advice snapshots + like / dislike feedback (B5, 2 Oct review)
-- Date: 2026-10-04
-- Description:
--   report_advice_snapshots — what the advice engine saw when it produced the cards: the
--     full metric set (`num` of report_insights), every rule that matched with its priority
--     and whether it was shown, the rule-set fingerprint, period, mode and filters.
--     Saved server-side when the comparison is computed (deduplicated by content hash), so
--     feedback never relies on numbers sent back by the browser.
--   report_advice_feedback — one opinion per user × rule × snapshot (different filters or
--     periods are different samples). `sample` is self-contained: the rule definition, the
--     inputs it read with their values, condition / priority and the rendered text. With
--     `vote` as the label these rows are the training / fine-tuning set for the rules.
-- Idempotent.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS report_advice_snapshots (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT NOT NULL REFERENCES organizations(id),
    content_hash     CHAR(64) NOT NULL,       -- sha256 of org + mode + periods + filters + rules + metrics
    rules_version    VARCHAR(40) NOT NULL,    -- 'v<version>-<sha12>' of report_rules.json
    report_mode      VARCHAR(16),             -- location / tag / tenant
    compare_mode     VARCHAR(16),             -- yearly / monthly
    period_from      DATE,
    period_to        DATE,
    prev_from        DATE,
    prev_to          DATE,
    filters          JSONB,                   -- location / tag / tenant / material / destination ids
    metrics          JSONB NOT NULL,          -- every metric the rules can read
    labels           JSONB,                   -- text values used in templates (period labels, top stream...)
    evaluated        JSONB,                   -- [{id, section, group, priority, shown, dropped}]
    created_by_id    BIGINT,                  -- user_locations.id who first triggered it
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_date     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date     TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date     TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_report_advice_snapshots_hash
    ON report_advice_snapshots (organization_id, content_hash);

CREATE TABLE IF NOT EXISTS report_advice_feedback (
    id                BIGSERIAL PRIMARY KEY,
    organization_id   BIGINT NOT NULL REFERENCES organizations(id),
    user_location_id  BIGINT NOT NULL REFERENCES user_locations(id),
    rule_id           VARCHAR(64) NOT NULL,
    section           VARCHAR(16),            -- risk / opportunity / quickwin
    report_mode       VARCHAR(16),
    period_from       DATE,
    period_to         DATE,
    vote              VARCHAR(8),             -- like / dislike / NULL (comment only)
    comment           TEXT,
    snapshot_id       BIGINT REFERENCES report_advice_snapshots(id),
    rules_version     VARCHAR(40),
    sample            JSONB,                  -- {rule, inputs, labels, condition_holds, priority, rendered, shown, rules_version_matches}
    filters           JSONB,
    advice_text       TEXT,                   -- title as the user saw it
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_date      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date      TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date      TIMESTAMPTZ,
    CONSTRAINT report_advice_feedback_vote_check CHECK (vote IS NULL OR vote IN ('like', 'dislike'))
);

-- One opinion per user × rule × snapshot; feedback without a snapshot (older clients) falls
-- back to user × rule × period.
CREATE UNIQUE INDEX IF NOT EXISTS uq_report_advice_feedback_snapshot
    ON report_advice_feedback (user_location_id, rule_id, snapshot_id)
    WHERE deleted_date IS NULL AND snapshot_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_report_advice_feedback_period
    ON report_advice_feedback (user_location_id, rule_id, COALESCE(period_from, '1900-01-01'), COALESCE(period_to, '1900-01-01'))
    WHERE deleted_date IS NULL AND snapshot_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_report_advice_feedback_rule ON report_advice_feedback (rule_id, vote);

COMMIT;
