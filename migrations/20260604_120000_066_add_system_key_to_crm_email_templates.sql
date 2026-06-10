-- Migration 066 — add `system_key` to crm_email_templates.
--
-- `system_key` ties a system template (is_system = TRUE, organization_id NULL)
-- to a specific business-v3 email trigger so the sender code can deterministically
-- fetch "the template for this email" at send time. Examples:
--   TXN_CREATED | TXN_UPDATED | TXN_DELETED | RPT_TXN_SCHEDULED
--
-- The actual template ROWS are seeded by the Python companion
-- (`migrations/seed_business_email_templates_066.py`) which holds the large
-- HTML bodies as triple-quoted strings and upserts them with parameterised
-- queries — far safer than hand-escaping E'...' blobs here.

ALTER TABLE crm_email_templates
    ADD COLUMN IF NOT EXISTS system_key VARCHAR(64);

-- At most one CURRENT live system template per key. The template versioning
-- model (update_crm_template) retires the old row with is_current = FALSE and
-- inserts a new is_current = TRUE row carrying the same is_system + system_key,
-- so the index must scope to is_current = TRUE — otherwise the retired version
-- and the new version would both match and the insert would collide.
-- Per-org clones (is_system = FALSE) and soft-deleted rows are excluded.
CREATE UNIQUE INDEX IF NOT EXISTS uq_crm_templates_system_key
    ON crm_email_templates (system_key)
    WHERE system_key IS NOT NULL
      AND is_system = TRUE
      AND deleted_date IS NULL
      AND COALESCE(is_current, TRUE) = TRUE;

COMMENT ON COLUMN crm_email_templates.system_key IS
    'Stable key linking a system template to a business-v3 email trigger '
    '(TXN_CREATED, TXN_UPDATED, TXN_DELETED, RPT_TXN_SCHEDULED). NULL for '
    'ordinary CRM/marketing templates. Sender code resolves the template by '
    'this key. Rows seeded by seed_business_email_templates_066.py.';
