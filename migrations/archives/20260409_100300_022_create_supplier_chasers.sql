-- Supplier Chaser / Reminder System
-- Tracks automated reminder schedules and delivery status for supplier data requests

CREATE TABLE IF NOT EXISTS esg_supplier_chasers (
    id BIGSERIAL PRIMARY KEY,
    supplier_id BIGINT NOT NULL REFERENCES esg_suppliers(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    chaser_type VARCHAR(20) NOT NULL DEFAULT 'email',
    scheduled_date DATE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    reminder_count INT NOT NULL DEFAULT 0,
    linked_submission_id BIGINT REFERENCES esg_supplier_submissions(id),
    message_template VARCHAR(50),
    response_received BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_chaser_type CHECK (chaser_type IN ('email', 'line', 'sms')),
    CONSTRAINT chk_chaser_status CHECK (status IN ('scheduled', 'sent', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_esg_chasers_org_status
    ON esg_supplier_chasers (organization_id, status, scheduled_date)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_esg_chasers_supplier
    ON esg_supplier_chasers (supplier_id)
    WHERE is_active = TRUE;

COMMENT ON TABLE esg_supplier_chasers IS 'Automated reminder system for supplier data collection with traffic-light status tracking';
