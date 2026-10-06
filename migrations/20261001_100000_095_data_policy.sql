-- ============================================================================
-- Migration: Data Policy — retention rules + per-organization diagnosis snapshots
-- Date: 2026-10-01
-- Description:
--   Back-office "Data Policy" tab (gepp-new-webapp → GEPP v3 → Data Policy).
--   The legal data unit on v3 is the organization. Four operational tables:
--     data_policy_rules         what must happen to each data category (purge after N, keep ≥ N, …)
--     data_policy_runs          one Diagnose run; resumable, time-budgeted (API Gateway 29 s cap)
--     data_policy_run_probes    per-category staging for a run in progress (deleted on finalize)
--     data_policy_unit_results  LATEST inventory + issues per organization (the list page reads this)
--   Not warehouse fact/dimension tables — operational state for the engine in
--   GEPPPlatform/services/admin/data_policy/. Docs: docs/Services/GEPP-Backoffice/features/data_policy.md
--   Seeds a recommended default rule set, only when no rule exists yet.
-- Idempotent: re-running changes nothing.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS data_policy_rules (
    id               BIGSERIAL PRIMARY KEY,
    category_key     VARCHAR(64)  NOT NULL,
    action           VARCHAR(32)  NOT NULL,
    retention_value  INTEGER      NULL,
    retention_unit   VARCHAR(8)   NULL,
    schedule_value   INTEGER      NULL,
    schedule_unit    VARCHAR(8)   NULL,
    severity         VARCHAR(16)  NULL,           -- NULL = derive from category sensitivity
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    exempt_unit_ids  JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- organizations on legal hold
    note             TEXT         NULL,
    created_by       BIGINT       NULL,
    updated_by       BIGINT       NULL,
    created_date     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_date     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_date     TIMESTAMPTZ  NULL,
    CONSTRAINT chk_data_policy_rules_action CHECK (action IN (
        'purge', 'anonymize', 'purge_soft_deleted', 'retain_min', 'inactive_unit_purge', 'review', 'backup', 'archive')),
    CONSTRAINT chk_data_policy_rules_retention_unit CHECK (retention_unit IS NULL OR retention_unit IN ('day', 'week', 'month', 'year')),
    CONSTRAINT chk_data_policy_rules_schedule_unit CHECK (schedule_unit IS NULL OR schedule_unit IN ('day', 'week', 'month', 'year')),
    CONSTRAINT chk_data_policy_rules_severity CHECK (severity IS NULL OR severity IN ('critical', 'high', 'medium', 'low', 'info'))
);
CREATE INDEX IF NOT EXISTS idx_data_policy_rules_category
    ON data_policy_rules (category_key) WHERE deleted_date IS NULL;

CREATE TABLE IF NOT EXISTS data_policy_runs (
    id                  BIGSERIAL PRIMARY KEY,
    status              VARCHAR(16)  NOT NULL DEFAULT 'running',   -- running | completed | failed | abandoned
    scope_unit_ids      JSONB        NULL,                          -- NULL = every organization
    plan_keys           JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- categories planned (tables exist)
    pending_keys        JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- not probed yet
    skipped_keys        JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- tables missing in this DB
    rules_snapshot      JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- active rules + absolute cutoffs
    probe_errors        JSONB        NOT NULL DEFAULT '[]'::jsonb,
    severity_counts     JSONB        NULL,
    started_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ  NULL,
    duration_ms         BIGINT       NULL,
    units_scanned       INTEGER      NULL,
    issues_found        INTEGER      NULL,
    unverifiable_rules  INTEGER      NOT NULL DEFAULT 0,
    engine_version      VARCHAR(32)  NULL,
    created_by          BIGINT       NULL,
    created_date        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_date        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_data_policy_runs_status_finished
    ON data_policy_runs (status, finished_at DESC);

CREATE TABLE IF NOT EXISTS data_policy_run_probes (
    id            BIGSERIAL PRIMARY KEY,
    run_id        BIGINT       NOT NULL REFERENCES data_policy_runs(id) ON DELETE CASCADE,
    category_key  VARCHAR(64)  NOT NULL,
    result        JSONB        NOT NULL DEFAULT '{}'::jsonb,   -- {unit_id: metrics}
    duration_ms   INTEGER      NULL,
    error         TEXT         NULL,
    created_date  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_data_policy_run_probes UNIQUE (run_id, category_key)
);

-- No FK to organizations on purpose: a snapshot is evidence of what was held,
-- and must survive the organization being hard-deleted.
CREATE TABLE IF NOT EXISTS data_policy_unit_results (
    unit_id           BIGINT       PRIMARY KEY,
    run_id            BIGINT       NULL REFERENCES data_policy_runs(id) ON DELETE SET NULL,
    diagnosed_at      TIMESTAMPTZ  NOT NULL,
    issue_count       INTEGER      NOT NULL DEFAULT 0,
    critical_count    INTEGER      NOT NULL DEFAULT 0,
    high_count        INTEGER      NOT NULL DEFAULT 0,
    medium_count      INTEGER      NOT NULL DEFAULT 0,
    low_count         INTEGER      NOT NULL DEFAULT 0,
    info_count        INTEGER      NOT NULL DEFAULT 0,
    total_records     BIGINT       NULL,
    oldest_record_at  TIMESTAMPTZ  NULL,
    inventory         JSONB        NOT NULL DEFAULT '[]'::jsonb,
    issues            JSONB        NOT NULL DEFAULT '[]'::jsonb,
    updated_date      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_data_policy_unit_results_issues
    ON data_policy_unit_results (critical_count DESC, high_count DESC, issue_count DESC);

-- Recommended defaults. Editable in the back office; seeded once.
INSERT INTO data_policy_rules (category_key, action, retention_value, retention_unit, schedule_value, schedule_unit, severity, note)
SELECT v.* FROM (VALUES
    ('transactions',            'review',              3,    'year',  NULL::int, NULL,    NULL, 'Default: transactions older than 3 years are due for a retention review.'),
    ('transactions',            'purge_soft_deleted',  1,    'year',  NULL::int, NULL,    NULL, 'Transactions deleted in the app must be hard-deleted after 1 year.'),
    ('transactions',            'backup',              NULL, NULL,    1,         'day',   NULL, 'Daily database backup (RDS snapshot). Recorded only — not verifiable from the database yet.'),
    ('transaction_images',      'purge',               3,    'year',  1,         'month', NULL, 'Default: transaction photos are kept 3 years; clean-up runs monthly.'),
    ('public_storage_files',    'purge',               30,   'day',   NULL::int, NULL,    'high', 'Photos on public-read buckets (gepp-app / gepp-prod / Drive) must be moved to the private bucket or removed (PDPA s.37(1)).'),
    ('identity_documents',      'anonymize',           3,    'year',  NULL::int, NULL,    NULL, 'National ID numbers / card images: blank after 3 years unless a contract requires them.'),
    ('identity_documents',      'inactive_unit_purge', 1,    'year',  NULL::int, NULL,    NULL, 'Remove ID data one year after the organization stops using GEPP.'),
    ('bank_accounts',           'inactive_unit_purge', 1,    'year',  NULL::int, NULL,    NULL, 'Remove bank details one year after the organization stops using GEPP.'),
    ('user_accounts',           'inactive_unit_purge', 2,    'year',  NULL::int, NULL,    NULL, 'Remove user accounts two years after the organization stops using GEPP.'),
    ('user_accounts',           'purge_soft_deleted',  90,   'day',   NULL::int, NULL,    NULL, 'Deleted / deactivated users must be hard-deleted after 90 days.'),
    ('login_history',           'purge',               1,    'year',  1,         'month', NULL, 'Keep ≥ 90 days (Computer Crime Act s.26); purge after 1 year.'),
    ('usage_events',            'purge',               2,    'year',  1,         'month', NULL, 'Analytics/telemetry events are not needed beyond 2 years.'),
    ('pending_uploads',         'purge',               30,   'day',   1,         'week',  NULL, 'Abandoned upload slots older than 30 days.'),
    ('import_files',            'anonymize',           90,   'day',   NULL::int, NULL,    NULL, 'Clear preview_payload (parsed rows) of imports after 90 days.'),
    ('integration_credentials', 'purge_soft_deleted',  30,   'day',   NULL::int, NULL,    NULL, 'Revoked credentials and tokens must not linger.'),
    ('reward_finance_docs',     'retain_min',          5,    'year',  NULL::int, NULL,    NULL, 'Accounting Act s.14 / Revenue Code s.87/3: keep accounting evidence ≥ 5 years.'),
    ('maintenance_backups',     'purge',               90,   'day',   NULL::int, NULL,    NULL, 'One-off maintenance copies must be dropped within 90 days.'),
    ('stored_files',            'purge_soft_deleted',  90,   'day',   NULL::int, NULL,    NULL, 'Deleted files must be removed (DB row and S3 object) after 90 days.'),
    ('iot_telemetry',           'purge',               30,   'day',   1,         'week',  NULL, 'Built-in clean-up keeps events 1 h / health 7 d — anything older than 30 days means it is not running.'),
    ('esg_chat_logs',           'purge',               1,    'year',  NULL::int, NULL,    NULL, 'LINE messages and AI chat transcripts are kept 1 year.')
) AS v(category_key, action, retention_value, retention_unit, schedule_value, schedule_unit, severity, note)
WHERE NOT EXISTS (SELECT 1 FROM data_policy_rules);

COMMIT;
