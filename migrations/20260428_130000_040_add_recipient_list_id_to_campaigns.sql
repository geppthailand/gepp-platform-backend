-- Description: Add recipient_list_id to crm_campaigns for blast campaign TO-address fan-out
-- Sprint 1 BE Sonnet 1 — D1 resolved: email lists are the primary recipient set for blast campaigns

ALTER TABLE crm_campaigns
    ADD COLUMN IF NOT EXISTS recipient_list_id BIGINT
        REFERENCES crm_email_lists(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_crm_campaigns_recipient_list
    ON crm_campaigns(recipient_list_id);

COMMENT ON COLUMN crm_campaigns.recipient_list_id IS
    'Points to a crm_email_lists row. When set, the campaign blast fans out to each address in the list (TO). cc_list_id remains the CC set.';
