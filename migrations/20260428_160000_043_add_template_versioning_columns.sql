-- Sprint 2 BE2: Add versioning columns to crm_email_templates
-- Mirrors the crm_segments versioning pattern (parent_segment_id / is_current).
-- Safe to re-run: uses IF NOT EXISTS / DO $$ blocks.

ALTER TABLE crm_email_templates
    ADD COLUMN IF NOT EXISTS parent_template_id BIGINT REFERENCES crm_email_templates(id);

ALTER TABLE crm_email_templates
    ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE;

-- Mark all existing rows as current (idempotent — they already are single-version)
UPDATE crm_email_templates
SET is_current = TRUE
WHERE is_current IS NOT TRUE
  AND deleted_date IS NULL;

-- Partial index so list queries stay fast when filtering is_current = TRUE
CREATE INDEX IF NOT EXISTS idx_crm_templates_current
    ON crm_email_templates (is_current)
    WHERE deleted_date IS NULL;

COMMENT ON COLUMN crm_email_templates.parent_template_id IS
    'FK to the previous version row. NULL for v1. Forms a reverse-linked chain: '
    'most-recent row is_current=TRUE; older rows is_current=FALSE.';

COMMENT ON COLUMN crm_email_templates.is_current IS
    'TRUE for the active/latest version of a template family. '
    'Exactly one row per logical template should have is_current=TRUE and deleted_date IS NULL.';
