-- CRM: email templates with manual + AI-generated provenance

CREATE TABLE IF NOT EXISTS crm_email_templates (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    preview_text VARCHAR(500),
    body_html TEXT NOT NULL,
    body_plain TEXT,
    variables JSONB,
    generated_by VARCHAR(16) NOT NULL DEFAULT 'human',
    ai_prompt TEXT,
    ai_model VARCHAR(128),
    ai_token_usage JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INT NOT NULL DEFAULT 1,
    created_by BIGINT REFERENCES user_locations(id),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_crm_template_generator CHECK (generated_by IN ('human', 'ai'))
);

CREATE INDEX IF NOT EXISTS idx_crm_templates_org
    ON crm_email_templates (organization_id)
    WHERE deleted_date IS NULL;

COMMENT ON TABLE crm_email_templates IS
    'Email templates for CRM campaigns. ai_* columns only populated when generated_by=''ai''. Model + token usage for cost audit.';
