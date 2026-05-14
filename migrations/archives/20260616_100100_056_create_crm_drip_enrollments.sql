-- Sprint 10: CRM Drip Enrollments
-- Migration: 20260616_100100_056_create_crm_drip_enrollments.sql

CREATE TABLE IF NOT EXISTS crm_drip_enrollments (
    id                 BIGSERIAL PRIMARY KEY,
    sequence_id        BIGINT NOT NULL REFERENCES crm_drip_sequences(id),
    lead_id            BIGINT REFERENCES crm_leads(id),
    user_location_id   BIGINT REFERENCES user_locations(id),
    current_step       INT NOT NULL DEFAULT 0,
    next_step_at       TIMESTAMPTZ NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'active',
    enrolled_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at       TIMESTAMPTZ,
    CONSTRAINT crm_drip_enrollments_status_check
        CHECK (status IN ('active', 'completed', 'stopped', 'errored')),
    CONSTRAINT crm_drip_enrollments_recipient_check
        CHECK (lead_id IS NOT NULL OR user_location_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_crm_drip_enrollments_tick
    ON crm_drip_enrollments (status, next_step_at)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_crm_drip_enrollments_sequence_lead
    ON crm_drip_enrollments (sequence_id, lead_id)
    WHERE lead_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_crm_drip_enrollments_sequence_user
    ON crm_drip_enrollments (sequence_id, user_location_id)
    WHERE user_location_id IS NOT NULL;
