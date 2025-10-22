-- Migration: Create transaction_audit_history table
-- Description: Create table to store AI audit batch history for tracking and review
-- Date: 2025-10-09
-- Version: 047

-- Create transaction_audit_history table
CREATE TABLE IF NOT EXISTS transaction_audit_history (
    id SERIAL PRIMARY KEY,

    -- Organization and user tracking
    organization_id INTEGER NOT NULL,
    triggered_by_user_id INTEGER,

    -- Transaction batch information
    transactions INTEGER[] NOT NULL DEFAULT '{}',
    audit_info JSONB,

    -- Batch statistics
    total_transactions INTEGER DEFAULT 0,
    processed_transactions INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,

    -- Batch status and error tracking
    status VARCHAR(50) DEFAULT 'completed',
    error_message TEXT,

    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Soft delete
    deleted_date TIMESTAMP WITH TIME ZONE,

    -- Indexes for performance
    CONSTRAINT transaction_audit_history_organization_fk
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,
    CONSTRAINT transaction_audit_history_user_fk
        FOREIGN KEY (triggered_by_user_id)
        REFERENCES user_locations(id)
        ON DELETE SET NULL
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_transaction_audit_history_organization
    ON transaction_audit_history(organization_id);

CREATE INDEX IF NOT EXISTS idx_transaction_audit_history_created_date
    ON transaction_audit_history(created_date DESC);

CREATE INDEX IF NOT EXISTS idx_transaction_audit_history_status
    ON transaction_audit_history(status);

CREATE INDEX IF NOT EXISTS idx_transaction_audit_history_deleted
    ON transaction_audit_history(deleted_date)
    WHERE deleted_date IS NULL;

-- Add comment to table
COMMENT ON TABLE transaction_audit_history IS 'Stores batch audit history for AI-powered transaction auditing';
COMMENT ON COLUMN transaction_audit_history.transactions IS 'Array of transaction IDs included in this audit batch';
COMMENT ON COLUMN transaction_audit_history.audit_info IS 'Complete audit results and summary data in JSON format';
COMMENT ON COLUMN transaction_audit_history.status IS 'Batch status: completed, failed, or partial';
