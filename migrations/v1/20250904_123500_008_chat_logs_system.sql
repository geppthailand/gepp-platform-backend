-- Migration: Chat and Logging System
-- Date: 2025-01-09 12:35:00
-- Description: Creates chat system, meetings, and comprehensive logging tables

-- Chats
CREATE TABLE IF NOT EXISTS chats (
    id BIGSERIAL PRIMARY KEY,
    
    -- Chat participants
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    expert_id BIGINT REFERENCES experts(id),
    
    -- Chat details
    chat_type VARCHAR(50) DEFAULT 'support', -- 'support', 'consultation', 'expert', 'ai_assistant'
    subject VARCHAR(500),
    priority VARCHAR(20) DEFAULT 'medium', -- 'low', 'medium', 'high', 'urgent'
    
    -- Chat status
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'closed', 'archived'
    
    -- Session info
    session_id VARCHAR(255),
    platform VARCHAR(50), -- 'web', 'mobile', 'api'
    
    -- AI/Bot info (if applicable)
    ai_model VARCHAR(100),
    ai_context JSONB,
    
    -- Dates
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    tags JSONB,
    category VARCHAR(100),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Chat History
CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    
    chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    
    -- Message details
    message_type VARCHAR(50) DEFAULT 'text', -- 'text', 'image', 'file', 'system', 'ai_response'
    message_content TEXT,
    
    -- Sender information
    sender_type VARCHAR(50), -- 'user', 'expert', 'ai', 'system'
    sender_id BIGINT REFERENCES user_locations(id),
    sender_name VARCHAR(255),
    
    -- Message metadata
    message_length INTEGER,
    language VARCHAR(10) DEFAULT 'en',
    
    -- Attachments
    attachments JSONB, -- Array of file info
    
    -- AI-specific fields
    ai_confidence DECIMAL(5, 4), -- 0-1 confidence score
    ai_model VARCHAR(100),
    ai_tokens_used INTEGER,
    
    -- Message status
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    
    -- Feedback
    user_rating INTEGER, -- 1-5 rating for AI responses
    user_feedback TEXT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Meetings
CREATE TABLE IF NOT EXISTS meetings (
    id BIGSERIAL PRIMARY KEY,
    
    -- Meeting details
    title VARCHAR(500) NOT NULL,
    description TEXT,
    meeting_type VARCHAR(50), -- 'consultation', 'training', 'audit', 'review'
    
    -- Participants
    organizer_id BIGINT NOT NULL REFERENCES user_locations(id),
    expert_id BIGINT REFERENCES experts(id),
    
    -- Scheduling
    scheduled_start TIMESTAMP WITH TIME ZONE,
    scheduled_end TIMESTAMP WITH TIME ZONE,
    actual_start TIMESTAMP WITH TIME ZONE,
    actual_end TIMESTAMP WITH TIME ZONE,
    
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Meeting platform
    platform VARCHAR(50), -- 'zoom', 'teams', 'google_meet', 'in_person'
    meeting_url TEXT,
    meeting_id VARCHAR(255),
    passcode VARCHAR(100),
    
    -- Location (for in-person meetings)
    location TEXT,
    room VARCHAR(100),
    address TEXT,
    
    -- Status
    status VARCHAR(50) DEFAULT 'scheduled', -- 'scheduled', 'in_progress', 'completed', 'cancelled', 'no_show'
    
    -- Meeting content
    agenda JSONB,
    notes TEXT,
    action_items JSONB,
    decisions JSONB,
    
    -- Recordings and documents
    recording_url TEXT,
    presentation_urls JSONB,
    documents JSONB,
    
    -- Billing (for paid consultations)
    is_billable BOOLEAN DEFAULT FALSE,
    hourly_rate DECIMAL(10, 2),
    duration_minutes INTEGER,
    total_cost DECIMAL(10, 2),
    currency_id BIGINT REFERENCES currencies(id) DEFAULT 12,
    
    -- Feedback
    organizer_rating INTEGER, -- 1-5
    organizer_feedback TEXT,
    expert_rating INTEGER, -- 1-5
    expert_feedback TEXT,
    
    -- Reminders
    reminder_sent BOOLEAN DEFAULT FALSE,
    reminder_sent_at TIMESTAMP WITH TIME ZONE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Meeting Participants
CREATE TABLE IF NOT EXISTS meeting_participants (
    id BIGSERIAL PRIMARY KEY,
    
    meeting_id BIGINT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES user_locations(id) ON DELETE CASCADE,
    
    role VARCHAR(50), -- 'organizer', 'participant', 'observer'
    
    -- Participation status
    invitation_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'accepted', 'declined', 'tentative'
    attendance_status VARCHAR(50) DEFAULT 'unknown', -- 'unknown', 'present', 'absent', 'partial'
    
    -- Participation details
    joined_at TIMESTAMP WITH TIME ZONE,
    left_at TIMESTAMP WITH TIME ZONE,
    
    -- Notifications
    email_sent BOOLEAN DEFAULT FALSE,
    reminder_sent BOOLEAN DEFAULT FALSE,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    UNIQUE(meeting_id, user_id)
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    
    -- Who performed the action
    user_id BIGINT REFERENCES user_locations(id),
    organization_id BIGINT REFERENCES organizations(id),
    
    -- What action was performed
    action VARCHAR(100), -- 'create', 'update', 'delete', 'login', 'logout', 'view', 'export'
    resource_type VARCHAR(100), -- 'transaction', 'user', 'organization', 'report'
    resource_id BIGINT,
    
    -- Action details
    description TEXT,
    changes JSONB, -- Before/after values for updates
    metadata JSONB, -- Additional context
    
    -- Request details
    ip_address INET,
    user_agent TEXT,
    request_method VARCHAR(10),
    request_url TEXT,
    
    -- Session info
    session_id VARCHAR(255),
    
    -- Result
    status VARCHAR(50) DEFAULT 'success', -- 'success', 'failure', 'partial'
    error_message TEXT,
    
    -- Compliance
    compliance_category VARCHAR(100), -- 'data_access', 'financial', 'security', 'privacy'
    retention_period_days INTEGER DEFAULT 2555, -- 7 years default
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Platform Logs (System/application logs)
CREATE TABLE IF NOT EXISTS platform_logs (
    id BIGSERIAL PRIMARY KEY,
    
    -- Log classification
    log_level VARCHAR(20), -- 'debug', 'info', 'warn', 'error', 'fatal'
    category VARCHAR(100), -- 'authentication', 'database', 'api', 'payment', 'email'
    source VARCHAR(100), -- Service or module name
    
    -- Log content
    message TEXT,
    details JSONB,
    
    -- Context
    user_id BIGINT REFERENCES user_locations(id),
    organization_id BIGINT REFERENCES organizations(id),
    session_id VARCHAR(255),
    request_id VARCHAR(255),
    
    -- Technical details
    server_name VARCHAR(100),
    process_id INTEGER,
    thread_id INTEGER,
    
    -- Error details (for errors)
    error_code VARCHAR(50),
    error_type VARCHAR(100),
    stack_trace TEXT,
    
    -- Performance metrics
    execution_time_ms INTEGER,
    memory_usage_mb DECIMAL(10, 2),
    cpu_usage_percent DECIMAL(5, 2),
    
    -- Related resources
    related_resource_type VARCHAR(100),
    related_resource_id BIGINT,
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- System Events (for integration and workflow tracking)
CREATE TABLE IF NOT EXISTS system_events (
    id BIGSERIAL PRIMARY KEY,
    
    event_type VARCHAR(100), -- 'user_registered', 'transaction_completed', 'report_generated'
    event_source VARCHAR(100), -- 'web_app', 'mobile_app', 'api', 'cron_job'
    
    -- Event data
    event_data JSONB,
    correlation_id VARCHAR(255), -- For tracking related events
    
    -- Processing status
    processing_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'processed', 'failed', 'skipped'
    processed_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Error handling
    error_message TEXT,
    last_error_at TIMESTAMP WITH TIME ZONE,
    
    -- Priority and scheduling
    priority INTEGER DEFAULT 5, -- 1-10 scale
    scheduled_for TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    created_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_chats_user ON chats(user_id);
CREATE INDEX IF NOT EXISTS idx_chats_expert ON chats(expert_id);
CREATE INDEX IF NOT EXISTS idx_chats_type ON chats(chat_type);
CREATE INDEX IF NOT EXISTS idx_chats_status ON chats(status);
CREATE INDEX IF NOT EXISTS idx_chats_started_at ON chats(started_at);

CREATE INDEX IF NOT EXISTS idx_chat_history_chat ON chat_history(chat_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_sender ON chat_history(sender_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created ON chat_history(created_date);

CREATE INDEX IF NOT EXISTS idx_meetings_organizer ON meetings(organizer_id);
CREATE INDEX IF NOT EXISTS idx_meetings_expert ON meetings(expert_id);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_meetings_scheduled_start ON meetings(scheduled_start);

CREATE INDEX IF NOT EXISTS idx_meeting_participants_meeting ON meeting_participants(meeting_id);
CREATE INDEX IF NOT EXISTS idx_meeting_participants_user ON meeting_participants(user_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_organization ON audit_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_date);
CREATE INDEX IF NOT EXISTS idx_audit_logs_compliance ON audit_logs(compliance_category);

CREATE INDEX IF NOT EXISTS idx_platform_logs_level ON platform_logs(log_level);
CREATE INDEX IF NOT EXISTS idx_platform_logs_category ON platform_logs(category);
CREATE INDEX IF NOT EXISTS idx_platform_logs_created ON platform_logs(created_date);
CREATE INDEX IF NOT EXISTS idx_platform_logs_user ON platform_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_status ON system_events(processing_status);
CREATE INDEX IF NOT EXISTS idx_system_events_scheduled ON system_events(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_system_events_correlation ON system_events(correlation_id);

-- Create triggers for updated_date columns
CREATE TRIGGER update_chats_updated_date BEFORE UPDATE ON chats
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_meetings_updated_date BEFORE UPDATE ON meetings
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_meeting_participants_updated_date BEFORE UPDATE ON meeting_participants
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

CREATE TRIGGER update_system_events_updated_date BEFORE UPDATE ON system_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_date_column();

-- Insert some default data
INSERT INTO gri_standards (standard_code, standard_name, category, description) VALUES
    ('GRI-301', 'Materials', 'environmental', 'Materials used and waste generated'),
    ('GRI-302', 'Energy', 'environmental', 'Energy consumption and efficiency'),
    ('GRI-303', 'Water', 'environmental', 'Water usage and conservation'),
    ('GRI-305', 'Emissions', 'environmental', 'Greenhouse gas emissions'),
    ('GRI-306', 'Waste', 'environmental', 'Waste generation and disposal')
ON CONFLICT (standard_code) DO NOTHING;