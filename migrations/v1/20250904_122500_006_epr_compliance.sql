-- Migration: EPR Compliance System
-- Date: 2025-01-09 12:25:00
-- Description: Creates Extended Producer Responsibility compliance and reporting tables

-- EPR Programs/Schemes
CREATE TABLE IF NOT EXISTS epr_programs (
    id BIGSERIAL PRIMARY KEY,
    
    name VARCHAR(255) NOT NULL,
    description TEXT,
    program_type VARCHAR(50), -- 'packaging', 'electronics', 'batteries', 'tyres'
    
    -- Regulatory info
    regulation_reference VARCHAR(100),
    authority VARCHAR(255),
    country_id BIGINT REFERENCES location_countries(id),
    
    -- Program details
    start_date DATE,
    end_date DATE,
    reporting_frequency VARCHAR(50), -- 'monthly', 'quarterly', 'annually'
    
    -- Targets and requirements
    collection_target_percent DECIMAL(5, 2),
    recycling_target_percent DECIMAL(5, 2),
    recovery_target_percent DECIMAL(5, 2),
    
    -- Fees and penalties
    fee_structure JSONB,
    penalty_structure JSONB,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- EPR Registrations (Organizations registered with EPR programs)
CREATE TABLE IF NOT EXISTS epr_registrations (
    id BIGSERIAL PRIMARY KEY,
    
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    program_id BIGINT NOT NULL REFERENCES epr_programs(id),
    
    registration_number VARCHAR(100),
    registration_date DATE,
    registration_status VARCHAR(50) DEFAULT 'active', -- 'pending', 'active', 'suspended', 'cancelled'
    
    -- Organization role in EPR
    participant_type VARCHAR(50), -- 'producer', 'importer', 'brand_owner', 'retailer', 'scheme_operator'
    responsibility_type VARCHAR(50), -- 'individual', 'collective'
    
    -- Product categories covered
    product_categories JSONB,
    material_types JSONB,
    
    -- Registration details
    annual_tonnage_estimate DECIMAL(12, 3),
    market_share_percent DECIMAL(5, 2),
    
    -- Compliance officer
    compliance_officer_name VARCHAR(255),
    compliance_officer_email VARCHAR(255),
    compliance_officer_phone VARCHAR(50),
    
    -- Dates
    renewal_date DATE,
    expiry_date DATE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    UNIQUE(organization_id, program_id)
);

-- EPR Targets (specific targets for organizations)
CREATE TABLE IF NOT EXISTS epr_targets (
    id BIGSERIAL PRIMARY KEY,
    
    registration_id BIGINT NOT NULL REFERENCES epr_registrations(id) ON DELETE CASCADE,
    
    target_year INTEGER,
    target_period VARCHAR(50), -- 'Q1', 'Q2', 'annual'
    
    -- Quantity targets
    collection_target_kg DECIMAL(12, 3),
    recycling_target_kg DECIMAL(12, 3),
    recovery_target_kg DECIMAL(12, 3),
    
    -- Percentage targets
    collection_rate_target DECIMAL(5, 2),
    recycling_rate_target DECIMAL(5, 2),
    recovery_rate_target DECIMAL(5, 2),
    
    -- Financial targets
    fee_target_amount DECIMAL(12, 2),
    investment_target_amount DECIMAL(12, 2),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- EPR Data Submissions
CREATE TABLE IF NOT EXISTS epr_data_submissions (
    id BIGSERIAL PRIMARY KEY,
    
    registration_id BIGINT NOT NULL REFERENCES epr_registrations(id) ON DELETE CASCADE,
    
    reporting_period VARCHAR(50),
    reporting_year INTEGER,
    submission_date DATE,
    submission_status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'submitted', 'under_review', 'approved', 'rejected'
    
    -- Submitted data
    products_placed_market_kg DECIMAL(12, 3),
    waste_collected_kg DECIMAL(12, 3),
    waste_recycled_kg DECIMAL(12, 3),
    waste_recovered_kg DECIMAL(12, 3),
    waste_disposed_kg DECIMAL(12, 3),
    
    -- Calculated rates
    collection_rate DECIMAL(5, 2),
    recycling_rate DECIMAL(5, 2),
    recovery_rate DECIMAL(5, 2),
    
    -- Financial data
    fees_paid DECIMAL(12, 2),
    investments_made DECIMAL(12, 2),
    
    -- Supporting data
    data_sources JSONB,
    methodology TEXT,
    assumptions TEXT,
    
    -- Submission details
    submitted_by_id BIGINT REFERENCES user_locations(id),
    reviewed_by VARCHAR(255),
    review_date DATE,
    review_comments TEXT,
    
    -- Documents
    submission_file_url TEXT,
    supporting_documents JSONB,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- EPR Reports (Generated compliance reports)
CREATE TABLE IF NOT EXISTS epr_reports (
    id BIGSERIAL PRIMARY KEY,
    
    registration_id BIGINT NOT NULL REFERENCES epr_registrations(id) ON DELETE CASCADE,
    
    report_type VARCHAR(50), -- 'compliance', 'performance', 'audit', 'annual'
    report_period VARCHAR(50),
    report_year INTEGER,
    
    report_title VARCHAR(255),
    report_description TEXT,
    
    -- Report status
    status VARCHAR(50) DEFAULT 'generating', -- 'generating', 'ready', 'published', 'archived'
    
    -- Report data
    executive_summary TEXT,
    key_findings TEXT,
    recommendations TEXT,
    
    -- Performance metrics
    compliance_score INTEGER, -- 0-100
    target_achievement_rate DECIMAL(5, 2),
    improvement_areas JSONB,
    
    -- Report files
    report_file_url TEXT,
    charts_data JSONB,
    
    generated_by_id BIGINT REFERENCES user_locations(id),
    generated_at TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- EPR Payments (Fee payments)
CREATE TABLE IF NOT EXISTS epr_payments (
    id BIGSERIAL PRIMARY KEY,
    
    registration_id BIGINT NOT NULL REFERENCES epr_registrations(id) ON DELETE CASCADE,
    
    payment_type VARCHAR(50), -- 'registration_fee', 'compliance_fee', 'penalty', 'administrative_fee'
    payment_period VARCHAR(50),
    payment_year INTEGER,
    
    -- Payment details
    base_amount DECIMAL(12, 2),
    fee_rate DECIMAL(8, 4), -- per kg or percentage
    calculated_amount DECIMAL(12, 2),
    penalty_amount DECIMAL(12, 2) DEFAULT 0,
    total_amount DECIMAL(12, 2),
    
    currency_id BIGINT REFERENCES currencies(id) DEFAULT 12,
    
    -- Payment status
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'paid', 'overdue', 'waived', 'disputed'
    due_date DATE,
    payment_date DATE,
    
    -- Payment method
    payment_method VARCHAR(50),
    payment_reference VARCHAR(100),
    bank_reference VARCHAR(100),
    
    -- Supporting info
    calculation_basis TEXT,
    notes TEXT,
    receipt_url TEXT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- EPR Auditing
CREATE TABLE IF NOT EXISTS epr_audits (
    id BIGSERIAL PRIMARY KEY,
    
    registration_id BIGINT NOT NULL REFERENCES epr_registrations(id) ON DELETE CASCADE,
    
    audit_type VARCHAR(50), -- 'compliance', 'data_verification', 'system', 'performance'
    audit_scope VARCHAR(100),
    
    -- Audit details
    audit_date_start DATE,
    audit_date_end DATE,
    auditor_name VARCHAR(255),
    auditor_organization VARCHAR(255),
    auditor_certification VARCHAR(100),
    
    -- Audit findings
    overall_rating VARCHAR(50), -- 'excellent', 'good', 'satisfactory', 'needs_improvement', 'unsatisfactory'
    compliance_level DECIMAL(5, 2), -- percentage
    
    findings JSONB,
    non_conformities JSONB,
    recommendations JSONB,
    
    -- Follow-up
    corrective_actions JSONB,
    follow_up_date DATE,
    follow_up_status VARCHAR(50),
    
    -- Documents
    audit_report_url TEXT,
    supporting_evidence JSONB,
    
    conducted_by_id BIGINT REFERENCES user_locations(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- EPR Notifications
CREATE TABLE IF NOT EXISTS epr_notifications (
    id BIGSERIAL PRIMARY KEY,
    
    registration_id BIGINT REFERENCES epr_registrations(id) ON DELETE CASCADE,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE,
    
    notification_type VARCHAR(50), -- 'deadline_reminder', 'compliance_alert', 'payment_due', 'audit_scheduled'
    priority VARCHAR(20) DEFAULT 'medium', -- 'low', 'medium', 'high', 'urgent'
    
    title VARCHAR(255),
    message TEXT,
    
    -- Notification details
    scheduled_date DATE,
    sent_date TIMESTAMP WITH TIME ZONE,
    read_date TIMESTAMP WITH TIME ZONE,
    
    -- Recipients
    recipient_emails JSONB,
    sent_to_users JSONB,
    
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'sent', 'delivered', 'read', 'failed'
    
    -- Related data
    related_submission_id BIGINT REFERENCES epr_data_submissions(id),
    related_payment_id BIGINT REFERENCES epr_payments(id),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_epr_programs_type ON epr_programs(program_type);
CREATE INDEX IF NOT EXISTS idx_epr_programs_country ON epr_programs(country_id);

CREATE INDEX IF NOT EXISTS idx_epr_registrations_organization ON epr_registrations(organization_id);
CREATE INDEX IF NOT EXISTS idx_epr_registrations_program ON epr_registrations(program_id);
CREATE INDEX IF NOT EXISTS idx_epr_registrations_status ON epr_registrations(registration_status);

CREATE INDEX IF NOT EXISTS idx_epr_targets_registration ON epr_targets(registration_id);
CREATE INDEX IF NOT EXISTS idx_epr_targets_year ON epr_targets(target_year);

CREATE INDEX IF NOT EXISTS idx_epr_data_submissions_registration ON epr_data_submissions(registration_id);
CREATE INDEX IF NOT EXISTS idx_epr_data_submissions_period ON epr_data_submissions(reporting_year, reporting_period);
CREATE INDEX IF NOT EXISTS idx_epr_data_submissions_status ON epr_data_submissions(submission_status);

CREATE INDEX IF NOT EXISTS idx_epr_reports_registration ON epr_reports(registration_id);
CREATE INDEX IF NOT EXISTS idx_epr_reports_type ON epr_reports(report_type);
CREATE INDEX IF NOT EXISTS idx_epr_reports_period ON epr_reports(report_year, report_period);

CREATE INDEX IF NOT EXISTS idx_epr_payments_registration ON epr_payments(registration_id);
CREATE INDEX IF NOT EXISTS idx_epr_payments_status ON epr_payments(status);
CREATE INDEX IF NOT EXISTS idx_epr_payments_due_date ON epr_payments(due_date);

CREATE INDEX IF NOT EXISTS idx_epr_audits_registration ON epr_audits(registration_id);
CREATE INDEX IF NOT EXISTS idx_epr_audits_date ON epr_audits(audit_date_start);

CREATE INDEX IF NOT EXISTS idx_epr_notifications_registration ON epr_notifications(registration_id);
CREATE INDEX IF NOT EXISTS idx_epr_notifications_organization ON epr_notifications(organization_id);
CREATE INDEX IF NOT EXISTS idx_epr_notifications_type ON epr_notifications(notification_type);

-- Create triggers for updated_date columns
CREATE TRIGGER update_epr_programs_updated_date BEFORE UPDATE ON epr_programs
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_registrations_updated_date BEFORE UPDATE ON epr_registrations
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_targets_updated_date BEFORE UPDATE ON epr_targets
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_data_submissions_updated_date BEFORE UPDATE ON epr_data_submissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_reports_updated_date BEFORE UPDATE ON epr_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_payments_updated_date BEFORE UPDATE ON epr_payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_audits_updated_date BEFORE UPDATE ON epr_audits
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_epr_notifications_updated_date BEFORE UPDATE ON epr_notifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();