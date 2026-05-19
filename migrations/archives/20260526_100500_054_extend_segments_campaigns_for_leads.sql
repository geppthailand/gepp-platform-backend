-- Migration 054: Extend segments and campaigns to support leads
-- Sprint 9 — allow scope='lead' and target_type='lead'

-- ── crm_segments: allow 'lead' as scope ──────────────────────────────────────
ALTER TABLE crm_segments DROP CONSTRAINT IF EXISTS chk_crm_segment_scope;
ALTER TABLE crm_segments ADD CONSTRAINT chk_crm_segment_scope
    CHECK (scope IN ('user', 'organization', 'lead'));

-- ── crm_segment_members: allow 'lead' as member_type ─────────────────────────
ALTER TABLE crm_segment_members DROP CONSTRAINT IF EXISTS chk_crm_segment_member_type;
ALTER TABLE crm_segment_members ADD CONSTRAINT chk_crm_segment_member_type
    CHECK (member_type IN ('user', 'organization', 'lead'));

-- ── crm_campaigns: add target_type column (default 'user' for backward compat) ─
ALTER TABLE crm_campaigns ADD COLUMN IF NOT EXISTS target_type VARCHAR(16) NOT NULL DEFAULT 'user';
ALTER TABLE crm_campaigns DROP CONSTRAINT IF EXISTS chk_crm_campaign_target_type;
ALTER TABLE crm_campaigns ADD CONSTRAINT chk_crm_campaign_target_type
    CHECK (target_type IN ('user', 'lead', 'mixed'));
CREATE INDEX IF NOT EXISTS idx_crm_campaigns_target_status
    ON crm_campaigns (target_type, status) WHERE deleted_date IS NULL;

-- ── crm_campaign_deliveries: add lead_id column ───────────────────────────────
ALTER TABLE crm_campaign_deliveries ADD COLUMN IF NOT EXISTS lead_id BIGINT REFERENCES crm_leads(id);
CREATE INDEX IF NOT EXISTS idx_crm_deliveries_lead
    ON crm_campaign_deliveries (lead_id) WHERE lead_id IS NOT NULL;
