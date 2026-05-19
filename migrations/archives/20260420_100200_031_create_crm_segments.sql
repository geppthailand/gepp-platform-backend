-- CRM: versioned rule-based cohorts + materialized membership

CREATE TABLE IF NOT EXISTS crm_segments (
    id BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rules JSONB NOT NULL,
    scope VARCHAR(16) NOT NULL,
    version INT NOT NULL DEFAULT 1,
    parent_segment_id BIGINT REFERENCES crm_segments(id),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    member_count INT NOT NULL DEFAULT 0,
    last_evaluated_at TIMESTAMP WITH TIME ZONE,
    created_by BIGINT REFERENCES user_locations(id),
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,
    CONSTRAINT chk_crm_segment_scope CHECK (scope IN ('user', 'organization'))
);

CREATE INDEX IF NOT EXISTS idx_crm_segments_org_current
    ON crm_segments (organization_id, is_current)
    WHERE deleted_date IS NULL;

COMMENT ON TABLE crm_segments IS
    'Versioned rule-based cohort definitions. New rules = new version row; previous marked is_current=false.';


CREATE TABLE IF NOT EXISTS crm_segment_members (
    segment_id BIGINT NOT NULL REFERENCES crm_segments(id) ON DELETE CASCADE,
    member_type VARCHAR(16) NOT NULL,
    member_id BIGINT NOT NULL,
    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (segment_id, member_type, member_id),
    CONSTRAINT chk_crm_segment_member_type CHECK (member_type IN ('user', 'organization'))
);

CREATE INDEX IF NOT EXISTS idx_crm_segment_members_member
    ON crm_segment_members (member_type, member_id);

COMMENT ON TABLE crm_segment_members IS
    'Materialized membership snapshot. Snapshot at campaign send time (for blast); refreshed per scheduler tick (for trigger).';
