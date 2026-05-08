-- CRM: campaigns (both trigger + blast types in one table)

CREATE TABLE IF NOT EXISTS crm_campaigns (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    campaign_type VARCHAR(16) NOT NULL,
    trigger_event VARCHAR(64),
    trigger_config JSONB,
    segment_id BIGINT REFERENCES crm_segments(id),
    template_id BIGINT NOT NULL REFERENCES crm_email_templates(id),
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    send_from_name VARCHAR(255),
    send_from_email VARCHAR(255),
    reply_to VARCHAR(255),
    cc_list_id BIGINT,
    metrics_cache JSONB,
    last_trigger_eval_at TIMESTAMP WITH TIME ZONE,
    created_by BIGINT REFERENCES user_locations(id),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_crm_campaign_type CHECK (campaign_type IN ('trigger', 'blast')),
    CONSTRAINT chk_crm_campaign_status CHECK (status IN (
        'draft', 'scheduled', 'running', 'paused', 'completed', 'archived', 'failed'
    ))
);

CREATE INDEX IF NOT EXISTS idx_crm_campaigns_status
    ON crm_campaigns (status)
    WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_crm_campaigns_org
    ON crm_campaigns (organization_id)
    WHERE deleted_date IS NULL;
CREATE INDEX IF NOT EXISTS idx_crm_campaigns_trigger_eval
    ON crm_campaigns (last_trigger_eval_at ASC NULLS FIRST)
    WHERE status = 'running' AND campaign_type = 'trigger' AND deleted_date IS NULL;

COMMENT ON TABLE crm_campaigns IS
    'CRM campaigns. campaign_type=blast uses segment_id snapshot at start; trigger re-evaluates every scheduler tick';
