-- CRM: global unsubscribe registry. Enforced pre-send.

CREATE TABLE IF NOT EXISTS crm_unsubscribes (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    user_location_id BIGINT REFERENCES user_locations(id),
    organization_id BIGINT REFERENCES organizations(id),
    reason VARCHAR(255),
    unsubscribed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    source VARCHAR(32) NOT NULL DEFAULT 'manual',
    CONSTRAINT chk_crm_unsub_source CHECK (source IN (
        'email_link', 'manual', 'bounce', 'complaint', 'mailchimp_webhook'
    ))
);

CREATE INDEX IF NOT EXISTS idx_crm_unsubscribes_email ON crm_unsubscribes (email);
CREATE INDEX IF NOT EXISTS idx_crm_unsubscribes_user ON crm_unsubscribes (user_location_id) WHERE user_location_id IS NOT NULL;

COMMENT ON TABLE crm_unsubscribes IS
    'Global opt-out registry. Campaign sender MUST check this before sending. Webhook handler inserts on Mailchimp unsub/hard_bounce/spam events.';
