-- ============================================================================
-- Migration: Create EPR AI Audit tables
-- Date: 2026-08-06
-- Description: Backfills the schema for GEPPPlatform/services/cores/epr_ai_audit.
--              The tables were created by hand on the dev server when the service
--              was ported from gepp-v2-backend, but never captured as a migration,
--              so production is missing them entirely (UndefinedTable on
--              epr_transactions_embeded).
--
--              This file is transcribed from the live dev schema (18.141.42.198)
--              so applying it reproduces dev exactly — same types, defaults,
--              nullability, index names and FK names.
--
--              epr_transactions_embeded / _records_embeded hold the embedded copy
--              of an EPR transaction (raw_data = the API payload verbatim). The
--              image tables hold per-file vision-LLM extractions plus a 1536-dim
--              description embedding used for dedup ANN search. epr_dedup_jobs is
--              the worker queue; epr_project_import_state is the per-project
--              legacy-MySQL import checkpoint.
--
--              epr_project_id references the LEGACY MySQL project — no FK.
--              All idempotent (IF NOT EXISTS).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ─── epr_transactions_embeded ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS epr_transactions_embeded (
    id              BIGSERIAL       PRIMARY KEY,
    -- FALSE marks a row pulled in by the legacy importer, TRUE a live API submission.
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    -- The inbound payload verbatim. Legacy imports also carry `_legacy_id`,
    -- `_source` and `_extraction_complete` markers.
    raw_data        JSONB           NOT NULL,
    -- Legacy MySQL epr_project_id. No FK — that table lives in another database.
    epr_project_id  BIGINT          NOT NULL,
    ai_score        NUMERIC(5,2),
    -- pending → passed | flagged | skipped, then approved | rejected once a human reviews.
    status          TEXT            NOT NULL DEFAULT 'pending',
    -- Worker output: {duplicates, integrity, review, dedup_at, reason}.
    flags           JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    deleted_date    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_epr_transactions_embeded_ai_score
    ON epr_transactions_embeded (ai_score);
CREATE INDEX IF NOT EXISTS idx_epr_transactions_embeded_is_active
    ON epr_transactions_embeded (is_active);
CREATE INDEX IF NOT EXISTS idx_epr_transactions_embeded_project_id
    ON epr_transactions_embeded (epr_project_id);
CREATE INDEX IF NOT EXISTS idx_epr_transactions_embeded_status
    ON epr_transactions_embeded (status);

-- ─── epr_transaction_records_embeded ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS epr_transaction_records_embeded (
    id              BIGSERIAL       PRIMARY KEY,
    transaction_id  BIGINT          NOT NULL
                                    REFERENCES epr_transactions_embeded(id)
                                    ON DELETE CASCADE,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    -- One material line from the payload's eprMaterials[].
    raw_data        JSONB           NOT NULL,
    ai_score        NUMERIC(5,2),
    status          TEXT            NOT NULL DEFAULT 'pending',
    flags           JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    deleted_date    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_epr_transaction_records_embeded_ai_score
    ON epr_transaction_records_embeded (ai_score);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_records_embeded_is_active
    ON epr_transaction_records_embeded (is_active);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_records_embeded_status
    ON epr_transaction_records_embeded (status);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_records_embeded_transaction_id
    ON epr_transaction_records_embeded (transaction_id);

-- ─── epr_transaction_image ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS epr_transaction_image (
    id                      BIGSERIAL       PRIMARY KEY,
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    name                    TEXT,
    image_url               TEXT            NOT NULL,
    transaction_id          BIGINT          NOT NULL
                                            REFERENCES epr_transactions_embeded(id)
                                            ON DELETE CASCADE,
    -- Image type name, copied from the payload's images[].type.name.
    type                    TEXT,
    -- Vision-LLM output. NULL means "not yet processed" — the worker's work queue.
    extracted_data          JSONB,
    -- openai/text-embedding-3-small over extracted_data->>'visual_description'.
    description_embedding   vector(1536),
    created_date            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_date            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    deleted_date            TIMESTAMPTZ,
    -- Added after the original table; stays last to match dev's column order.
    type_id                 BIGINT
);

-- Cosine ANN for the dedup description-similarity signal (duplicates.py).
CREATE INDEX IF NOT EXISTS idx_epr_transaction_image_desc_vec
    ON epr_transaction_image
    USING hnsw (description_embedding vector_cosine_ops);
-- Exact document-number match, the strongest dedup signal.
CREATE INDEX IF NOT EXISTS idx_epr_transaction_image_doc_no
    ON epr_transaction_image ((extracted_data ->> 'document_number'));
CREATE INDEX IF NOT EXISTS idx_epr_transaction_image_is_active
    ON epr_transaction_image (is_active);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_image_transaction_id
    ON epr_transaction_image (transaction_id);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_image_type_id
    ON epr_transaction_image (type_id);

-- ─── epr_transaction_record_image ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS epr_transaction_record_image (
    id                          BIGSERIAL       PRIMARY KEY,
    is_active                   BOOLEAN         NOT NULL DEFAULT TRUE,
    name                        TEXT,
    image_url                   TEXT            NOT NULL,
    epr_transaction_record_id   BIGINT          NOT NULL
                                                REFERENCES epr_transaction_records_embeded(id)
                                                ON DELETE CASCADE,
    type                        TEXT,
    extracted_data              JSONB,
    description_embedding       vector(1536),
    created_date                TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_date                TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    deleted_date                TIMESTAMPTZ,
    type_id                     BIGINT
);

CREATE INDEX IF NOT EXISTS idx_epr_transaction_record_image_desc_vec
    ON epr_transaction_record_image
    USING hnsw (description_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_record_image_doc_no
    ON epr_transaction_record_image ((extracted_data ->> 'document_number'));
CREATE INDEX IF NOT EXISTS idx_epr_transaction_record_image_is_active
    ON epr_transaction_record_image (is_active);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_record_image_record_id
    ON epr_transaction_record_image (epr_transaction_record_id);
CREATE INDEX IF NOT EXISTS idx_epr_transaction_record_image_type_id
    ON epr_transaction_record_image (type_id);

-- ─── epr_dedup_jobs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS epr_dedup_jobs (
    id              BIGSERIAL       PRIMARY KEY,
    transaction_id  BIGINT          NOT NULL
                                    REFERENCES epr_transactions_embeded(id)
                                    ON DELETE CASCADE,
    -- 'embedding' when queued; relabelled 'dedup_done' once processed.
    stage           TEXT            NOT NULL,
    -- pending → processing → done | failed.
    status          TEXT            NOT NULL DEFAULT 'pending',
    -- Bumped on claim; 3 strikes and mark_failed stops re-queueing.
    attempts        INTEGER         NOT NULL DEFAULT 0,
    last_error      TEXT,
    result          JSONB,
    created_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    started_date    TIMESTAMPTZ,
    completed_date  TIMESTAMPTZ,
    -- enqueue_job relies on this for its ON CONFLICT DO NOTHING.
    UNIQUE (transaction_id, stage)
);

-- Drives claim_next_jobs (WHERE status/stage ORDER BY created_date SKIP LOCKED).
CREATE INDEX IF NOT EXISTS idx_epr_dedup_jobs_status_stage
    ON epr_dedup_jobs (status, stage);
CREATE INDEX IF NOT EXISTS idx_epr_dedup_jobs_transaction_id
    ON epr_dedup_jobs (transaction_id);

-- ─── epr_project_import_state ───────────────────────────────────────────────
-- One row per legacy project. Note the _at column naming — this table uses
-- started_at/updated_at/completed_at, not the _date convention used above.
CREATE TABLE IF NOT EXISTS epr_project_import_state (
    epr_project_id          BIGINT          PRIMARY KEY,
    status                  TEXT            NOT NULL DEFAULT 'in_progress',
    -- Checkpoint so a timed-out Lambda resumes mid-project instead of restarting.
    last_imported_legacy_id BIGINT          NOT NULL DEFAULT 0,
    imported_count          INTEGER         NOT NULL DEFAULT 0,
    started_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_epr_project_import_state_status
    ON epr_project_import_state (status);
