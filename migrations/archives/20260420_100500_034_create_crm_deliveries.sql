-- CRM: one row per recipient send; tracks full lifecycle via Mailchimp webhooks

CREATE TABLE IF NOT EXISTS crm_campaign_deliveries (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES crm_campaigns(id) ON DELETE CASCADE,
    user_location_id BIGINT REFERENCES user_locations(id),
    organization_id BIGINT REFERENCES organizations(id),
    recipient_email VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    opened_at TIMESTAMP WITH TIME ZONE,
    first_clicked_at TIMESTAMP WITH TIME ZONE,
    open_count INT NOT NULL DEFAULT 0,
    click_count INT NOT NULL DEFAULT 0,
    mandrill_message_id VARCHAR(255) UNIQUE,
    mandrill_response JSONB,
    error_message TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    rendered_subject VARCHAR(500),
    rendered_body_hash VARCHAR(64),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crm_delivery_status CHECK (status IN (
        'pending', 'sending', 'sent', 'delivered', 'opened', 'clicked',
        'soft_bounced', 'hard_bounced', 'rejected', 'failed', 'unsubscribed'
    ))
);

CREATE INDEX IF NOT EXISTS idx_crm_deliveries_campaign_status
    ON crm_campaign_deliveries (campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_crm_deliveries_user_sent
    ON crm_campaign_deliveries (user_location_id, sent_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_crm_deliveries_org_sent
    ON crm_campaign_deliveries (organization_id, sent_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_crm_deliveries_pending_retry
    ON crm_campaign_deliveries (next_retry_at ASC)
    WHERE status = 'pending' OR (status = 'failed' AND retry_count < 5);

COMMENT ON TABLE crm_campaign_deliveries IS
    'One row per recipient per campaign send. mandrill_message_id correlates with Mailchimp webhook events.';
