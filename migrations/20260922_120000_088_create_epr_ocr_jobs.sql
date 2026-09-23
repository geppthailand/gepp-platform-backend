-- Async OCR jobs.
--
-- Reading a stack of documents with a vision model takes 20-45s. API Gateway
-- HTTP APIs cut the connection at 30s and that ceiling cannot be raised, so the
-- synchronous endpoint returned 503 on anything but a small upload — while the
-- Lambda behind it had actually succeeded. The request now creates a row here,
-- hands the work to a second invocation of the same Lambda, and the caller
-- polls this table.
--
-- Not reusing epr_dedup_jobs: that table is keyed by transaction_id, and OCR
-- runs BEFORE a transaction exists — filling the form is what creates one.

CREATE TABLE IF NOT EXISTS epr_ocr_jobs (
    -- "ocr_" + 32 hex chars. The endpoint is public (routed before the auth
    -- gate), so the id is the only thing protecting a result — it is generated
    -- with secrets.token_hex, never a sequence.
    id              TEXT            PRIMARY KEY,

    -- 'transaction' (read_transaction) or 'audit' (read_audit).
    kind            TEXT            NOT NULL DEFAULT 'transaction',

    -- pending -> processing -> done | failed
    status          TEXT            NOT NULL DEFAULT 'pending',

    -- The request as submitted: {"files": [...], "fields": [...]}. Kept so a
    -- job can be re-run without the caller re-uploading anything.
    request         JSONB           NOT NULL,

    -- Exactly what the synchronous endpoint used to return. Null until done.
    result          JSONB,

    -- Null unless status = 'failed'.
    error           TEXT,

    created_date    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    started_date    TIMESTAMPTZ,
    completed_date  TIMESTAMPTZ
);

-- For the cleanup sweep below; nothing in the request path scans by date.
CREATE INDEX IF NOT EXISTS idx_epr_ocr_jobs_created
    ON epr_ocr_jobs (created_date);

COMMENT ON TABLE epr_ocr_jobs IS
    'Async OCR jobs for /api/epr/ai_audit/ocr/jobs. Rows are disposable — the '
    'result is copied into the form by the caller. Safe to delete anything '
    'older than a few days.';
