-- CRM Lead Activities — append-only activity log for crm_leads.
-- Sprint 9 Phase 2. CASCADE delete on lead removal.

CREATE TABLE IF NOT EXISTS crm_lead_activities (
    id              BIGSERIAL PRIMARY KEY,
    lead_id         BIGINT      NOT NULL REFERENCES crm_leads(id) ON DELETE CASCADE,
    activity_type   VARCHAR(64) NOT NULL,
    properties      JSONB,
    performed_by    BIGINT      REFERENCES user_locations(id),
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_lead_activities_lead
    ON crm_lead_activities (lead_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_crm_lead_activities_type
    ON crm_lead_activities (activity_type);

COMMENT ON TABLE crm_lead_activities IS
    'Append-only activity log for crm_leads. '
    'One row per action: status_changed, owner_assigned, converted, note_added, '
    'call_logged, meeting_logged, email_sent, email_opened, csv_imported, score_updated.';

COMMENT ON COLUMN crm_lead_activities.activity_type IS
    'One of: status_changed, owner_assigned, converted, note_added, call_logged, '
    'meeting_logged, email_sent, email_opened, csv_imported, score_updated, manual.';
