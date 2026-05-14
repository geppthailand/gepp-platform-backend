-- Sprint 7: extend crm_email_templates to support gallery / category / EDM lift
-- Adds: category, icon, suggested_subject, is_system, block_tree (Sprint 8 ready)

ALTER TABLE crm_email_templates
    ADD COLUMN IF NOT EXISTS category VARCHAR(32),
    ADD COLUMN IF NOT EXISTS icon VARCHAR(32),
    ADD COLUMN IF NOT EXISTS suggested_subject VARCHAR(500),
    ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS block_tree JSONB;

-- Categories from gepp-edm-main: lead-lifecycle, client-engagement, marketing, admin, transactional
ALTER TABLE crm_email_templates
    DROP CONSTRAINT IF EXISTS chk_crm_template_category;
ALTER TABLE crm_email_templates
    ADD CONSTRAINT chk_crm_template_category CHECK (
        category IS NULL OR category IN (
            'lead-lifecycle', 'client-engagement', 'marketing', 'admin', 'transactional'
        )
    );

CREATE INDEX IF NOT EXISTS idx_crm_templates_category
    ON crm_email_templates (category)
    WHERE is_active = TRUE AND deleted_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_crm_templates_system
    ON crm_email_templates (is_system)
    WHERE is_active = TRUE AND deleted_date IS NULL;

COMMENT ON COLUMN crm_email_templates.category IS
    'Lifecycle stage taxonomy: lead-lifecycle | client-engagement | marketing | admin | transactional';
COMMENT ON COLUMN crm_email_templates.is_system IS
    'TRUE for templates lifted from gepp-edm-main (system-owned, organization_id NULL). Cloned to per-org rows when admin clones to gallery.';
COMMENT ON COLUMN crm_email_templates.block_tree IS
    'When the template was built via the block builder (Sprint 8), structured tree of {type, props, children}. body_html is regenerated from this on save.';
