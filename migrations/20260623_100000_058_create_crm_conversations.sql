-- Sprint 10 P1 — Conversation Inbox
-- Stores email threads (outbound deliveries + inbound replies arriving via
-- Mailchimp inbound webhook at /api/webhooks/mailchimp/inbound).
--
-- Thread matching: each outbound campaign delivery has a unique reply_to suffix
-- (reply+<thread_token>@gepp.me). When the recipient replies, the inbound
-- webhook extracts thread_token from the To: address and routes the message
-- into the corresponding conversation row.

CREATE TABLE IF NOT EXISTS crm_conversations (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    lead_id BIGINT REFERENCES crm_leads(id) ON DELETE SET NULL,
    user_location_id BIGINT REFERENCES user_locations(id) ON DELETE SET NULL,
    subject VARCHAR(500),
    thread_token VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    last_message_at TIMESTAMP WITH TIME ZONE,
    unread_count INT NOT NULL DEFAULT 0,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crm_conversation_status CHECK (status IN ('open', 'closed', 'spam'))
);

CREATE INDEX IF NOT EXISTS idx_crm_conversations_org_status
    ON crm_conversations (organization_id, status, last_message_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_crm_conversations_lead
    ON crm_conversations (lead_id) WHERE lead_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crm_conversations_user
    ON crm_conversations (user_location_id) WHERE user_location_id IS NOT NULL;

COMMENT ON TABLE crm_conversations IS
    'Email conversation threads. One row per outbound-thread; replies attach via thread_token.';


CREATE TABLE IF NOT EXISTS crm_conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES crm_conversations(id) ON DELETE CASCADE,
    direction VARCHAR(8) NOT NULL,
    delivery_id BIGINT REFERENCES crm_campaign_deliveries(id) ON DELETE SET NULL,
    from_email VARCHAR(255),
    to_email VARCHAR(255),
    subject VARCHAR(500),
    body_html TEXT,
    body_plain TEXT,
    mandrill_message_id VARCHAR(255),
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crm_conversation_msg_dir CHECK (direction IN ('outbound', 'inbound'))
);

CREATE INDEX IF NOT EXISTS idx_crm_conversation_msgs_thread
    ON crm_conversation_messages (conversation_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_crm_conversation_msgs_mandrill
    ON crm_conversation_messages (mandrill_message_id) WHERE mandrill_message_id IS NOT NULL;

COMMENT ON TABLE crm_conversation_messages IS
    'Individual messages in a conversation. direction=outbound for sent emails, inbound for replies.';


-- Permissions for the Inbox tab
INSERT INTO system_permissions (code, name, description, category, is_active, created_date, updated_date)
VALUES
    ('sidebar.marketing.inbox',         'Inbox',         'Access to conversation inbox', 'sidebar', TRUE, NOW(), NOW()),
    ('feature.marketing.inbox.view',    'View Inbox',    'Read conversations', 'accessibility', TRUE, NOW(), NOW()),
    ('feature.marketing.inbox.reply',   'Reply in Inbox','Send replies via the inbox', 'accessibility', TRUE, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;
