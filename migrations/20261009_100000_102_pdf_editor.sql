-- ============================================================================
-- Migration: Back-office PDF Editor (Documents tab)
-- Date: 2026-10-09
-- Description:
--   GEPP staff edit PDFs in the back-office: upload a source PDF into a project,
--   place images / signatures / text / shapes on it, remove objects from the
--   original pages, keep a history, and export a PDF that still carries the
--   original vector content. Rendering, editing and export all happen in the
--   browser — these tables only hold what has to survive a reload.
--
--   pdf_editor_projects   one row per project. `source_*` is the uploaded PDF and
--                         is immutable once `source_status = 'ready'`: the editor
--                         addresses original-page objects by their operator index
--                         in that file, so swapping the file would silently point
--                         every saved deletion at a different object.
--                         `state` = the current document (overlay objects + removed
--                         original objects); `history` = the action list shown in
--                         the History panel. `version` is bumped on every save and
--                         checked on the next one (optimistic lock, 409 on mismatch).
--   pdf_editor_assets     images and signatures for the element bar. scope='project'
--                         is visible to every admin on that project; scope='library'
--                         belongs to one admin (their signatures) across projects.
--                         kind='thumbnail' is the project card preview.
--   pdf_editor_revisions  one row per save — the "Versions" list a project can be
--                         restored from after the in-session history is gone.
--
--   Not organization-scoped on purpose: this is GEPP's own tool, and the bytes do
--   not belong to a tenant (so `files`, whose organization_id is NOT NULL, is not
--   used). Admin-only via the /api/admin guard.
-- Idempotent.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS pdf_editor_projects (
    id                  BIGSERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    description         TEXT,
    source_status       VARCHAR(16)  NOT NULL DEFAULT 'none'
                        CHECK (source_status IN ('none', 'pending', 'ready')),
    source_s3_bucket    VARCHAR(255),
    source_s3_key       TEXT,
    source_file_name    VARCHAR(512),
    source_file_size    BIGINT,
    page_count          INTEGER,
    thumbnail_asset_id  BIGINT,
    state               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    history             JSONB,
    version             INTEGER      NOT NULL DEFAULT 0,
    created_by_id       BIGINT,
    updated_by_id       BIGINT,
    created_date        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_date        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_date        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pdf_editor_projects_updated
    ON pdf_editor_projects (updated_date DESC)
    WHERE deleted_date IS NULL;

CREATE TABLE IF NOT EXISTS pdf_editor_assets (
    id                  BIGSERIAL PRIMARY KEY,
    project_id          BIGINT REFERENCES pdf_editor_projects (id),
    scope               VARCHAR(16)  NOT NULL CHECK (scope IN ('project', 'library')),
    kind                VARCHAR(16)  NOT NULL CHECK (kind IN ('image', 'signature', 'thumbnail')),
    name                VARCHAR(255) NOT NULL,
    status              VARCHAR(16)  NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'ready')),
    s3_bucket           VARCHAR(255) NOT NULL,
    s3_key              TEXT         NOT NULL,
    mime_type           VARCHAR(64)  NOT NULL,
    file_size           BIGINT,
    width               INTEGER,
    height              INTEGER,
    created_by_id       BIGINT,
    created_date        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_date        TIMESTAMPTZ,
    -- a project asset needs its project; a library asset must not have one
    CHECK ((scope = 'project') = (project_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_pdf_editor_assets_project
    ON pdf_editor_assets (project_id)
    WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_pdf_editor_assets_library
    ON pdf_editor_assets (created_by_id)
    WHERE deleted_date IS NULL AND scope = 'library';

CREATE TABLE IF NOT EXISTS pdf_editor_revisions (
    id                  BIGSERIAL PRIMARY KEY,
    project_id          BIGINT       NOT NULL REFERENCES pdf_editor_projects (id),
    revision_no         INTEGER      NOT NULL,
    label               VARCHAR(255),
    -- a named revision is a deliberate snapshot and is never pruned
    is_named            BOOLEAN      NOT NULL DEFAULT FALSE,
    doc                 JSONB        NOT NULL,
    object_count        INTEGER      NOT NULL DEFAULT 0,
    removed_count       INTEGER      NOT NULL DEFAULT 0,
    created_by_id       BIGINT,
    created_date        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, revision_no)
);

COMMIT;
