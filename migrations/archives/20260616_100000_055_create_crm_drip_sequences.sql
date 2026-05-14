-- Sprint 10: CRM Drip Sequences + Steps
-- Migration: 20260616_100000_055_create_crm_drip_sequences.sql

CREATE TABLE IF NOT EXISTS crm_drip_sequences (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  BIGINT REFERENCES organizations(id),
    name             VARCHAR(255) NOT NULL,
    description      TEXT,
    trigger_event    VARCHAR(64),
    trigger_config   JSONB,
    status           VARCHAR(16) NOT NULL DEFAULT 'draft',
    created_by       BIGINT REFERENCES user_locations(id),
    created_date     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_date     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_date     TIMESTAMPTZ,
    CONSTRAINT crm_drip_sequences_status_check
        CHECK (status IN ('draft', 'active', 'paused', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_crm_drip_sequences_org_status
    ON crm_drip_sequences (organization_id, status)
    WHERE deleted_date IS NULL;

CREATE TABLE IF NOT EXISTS crm_drip_steps (
    id           BIGSERIAL PRIMARY KEY,
    sequence_id  BIGINT NOT NULL REFERENCES crm_drip_sequences(id) ON DELETE CASCADE,
    step_index   INT NOT NULL,
    template_id  BIGINT NOT NULL REFERENCES crm_email_templates(id),
    delay_days   INT NOT NULL DEFAULT 0,
    delay_hours  INT NOT NULL DEFAULT 0,
    skip_filter  JSONB,
    UNIQUE (sequence_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_crm_drip_steps_sequence
    ON crm_drip_steps (sequence_id, step_index);
