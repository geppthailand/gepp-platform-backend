-- CRM: lean event log optimized for per-org / per-user aggregation
-- Scope: captures user actions (login, transaction, qr, reward, iot, gri, traceability) + email events
-- Instrumentation calls: crm_service.emit_event(db, org_id, user_id, event_type, category, properties)

CREATE TABLE IF NOT EXISTS crm_events (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id),
    user_location_id BIGINT REFERENCES user_locations(id),
    event_type VARCHAR(64) NOT NULL,
    event_category VARCHAR(32) NOT NULL,
    event_source VARCHAR(32) NOT NULL DEFAULT 'server',
    properties JSONB,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    session_id VARCHAR(128),
    ip_address INET,
    user_agent TEXT,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_crm_event_category CHECK (event_category IN (
        'auth', 'transaction', 'traceability', 'gri', 'reward', 'iot', 'page', 'email', 'system'
    )),
    CONSTRAINT chk_crm_event_source CHECK (event_source IN (
        'server', 'client', 'system', 'email_provider'
    ))
);

CREATE INDEX IF NOT EXISTS idx_crm_events_org_occurred
    ON crm_events (organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_crm_events_user_occurred
    ON crm_events (user_location_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_crm_events_type_occurred
    ON crm_events (event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_crm_events_org_type_occurred
    ON crm_events (organization_id, event_type, occurred_at DESC);

COMMENT ON TABLE crm_events IS
    'Lean event log for CRM analytics — denormalized per-event, optimized for time-range + org/user aggregation queries';
