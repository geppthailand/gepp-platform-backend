-- ============================================================================
-- Migration: Create organization_setup_imports (back-office "Import Organization Setup")
-- Date: 2026-07-16
-- Description: One row per setup-import batch (a 5-tab xlsx: Users, Tags, Tenants,
--              Origins, Destinations). Tracks the extracted/edited preview and the
--              ids of everything the import created, so a whole import can be reverted:
--                - users / tags / tenants (INSERT)  → soft-deleted by id on revert
--                - origins / destinations (REPLACE) → soft-deleted + nodeIds stripped
--                  from organization_setup.root_nodes / hub_node (a new setup version).
--              Origins/destinations import is a REPLACE: the current tree's nodes are
--              dropped from the chart (they remain active rows → surface in the recycle
--              bin as orphans) and the imported nodes become the active tree.
--              Mirrors import_files (migration 072). Idempotent.
-- ============================================================================

CREATE TABLE IF NOT EXISTS organization_setup_imports (
    id                      BIGSERIAL PRIMARY KEY,
    organization_id         BIGINT NOT NULL REFERENCES organizations(id),
    -- Back-office admin (user_locations.id) who ran the import. Plain id (no FK), mirrors
    -- import_files.uploaded_by_id.
    uploaded_by_id          BIGINT,

    -- Lifecycle: uploaded → extracting → extracted → confirming → confirmed → reverted; or failed.
    status                  VARCHAR(30) NOT NULL DEFAULT 'uploaded',

    -- Uploaded file metadata + S3 location of the raw xlsx.
    original_filename       VARCHAR(512),
    s3_key                  TEXT,
    s3_bucket               VARCHAR(255),
    file_size               BIGINT,
    mime_type               VARCHAR(255),

    -- Extracted + validated, (possibly admin-edited) preview for the review step:
    -- { users:[], tags:[], tenants:[], origins:[], destinations:[], validation:{...} }.
    preview_payload         JSONB,
    -- Roll-up counts per section for the version list.
    summary                 JSONB,
    error                   TEXT,

    -- Ids created by this import (for revert). Arrays of user_locations.id / user_location_tags.id /
    -- user_tenants.id. created_location_ids covers both origins and hub/destinations.
    created_user_ids        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_tag_ids         JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_tenant_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_location_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- The organization_setup version this import created (origins/destinations replace).
    created_setup_version_id BIGINT,

    confirmed_date          TIMESTAMPTZ,
    reverted_date           TIMESTAMPTZ,

    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_date            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_date            TIMESTAMPTZ,
    deleted_date            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_org_setup_imports_org
    ON organization_setup_imports (organization_id);
CREATE INDEX IF NOT EXISTS idx_org_setup_imports_status
    ON organization_setup_imports (organization_id, status);
