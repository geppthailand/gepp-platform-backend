-- CRM: per-organization email lists (CC/BCC recipients outside the org's user_locations)

CREATE TABLE IF NOT EXISTS crm_email_lists (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    emails JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT REFERENCES user_locations(id),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_crm_email_lists_org
    ON crm_email_lists (organization_id)
    WHERE deleted_date IS NULL;

COMMENT ON TABLE crm_email_lists IS
    'Per-org email lists for CC/BCC. emails column is JSON array: [{"email":"x@y.com","name":"X","role":"CC"}]';


-- Add FK from campaigns.cc_list_id now that lists table exists
ALTER TABLE crm_campaigns
    ADD CONSTRAINT fk_crm_campaigns_cc_list
    FOREIGN KEY (cc_list_id) REFERENCES crm_email_lists(id)
    ON DELETE SET NULL;
