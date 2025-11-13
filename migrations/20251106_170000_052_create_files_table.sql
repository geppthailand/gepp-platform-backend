-- Migration: Create files table for centralized file storage
-- Date: 2025-11-06 17:00:00
-- Description: Create files table to track all uploaded files with S3 URLs and metadata

-- Create file_type enum
CREATE TYPE file_type AS ENUM (
    'transaction_image',
    'transaction_record_image',
    'profile_image',
    'document',
    'other'
);

-- Create file_status enum
CREATE TYPE file_status AS ENUM (
    'pending',
    'uploaded',
    'processing',
    'failed',
    'deleted'
);

-- Create files table
CREATE TABLE files (
    id BIGSERIAL PRIMARY KEY,

    -- File identification
    file_type file_type NOT NULL DEFAULT 'other',
    status file_status NOT NULL DEFAULT 'pending',

    -- S3 storage information
    url TEXT NOT NULL,  -- Full S3 URL
    s3_key TEXT NOT NULL,  -- S3 key/path
    s3_bucket VARCHAR(255),  -- S3 bucket name

    -- File metadata
    original_filename VARCHAR(500),
    file_size BIGINT,  -- Size in bytes
    mime_type VARCHAR(100),

    -- Ownership and access control
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    uploader_id BIGINT NOT NULL REFERENCES user_locations(id),

    -- Related entity tracking (optional, for reporting and cleanup)
    related_entity_type VARCHAR(100),  -- e.g., 'transaction', 'transaction_record', 'user'
    related_entity_id BIGINT,  -- ID of the related entity

    -- Additional metadata (JSONB for flexibility)
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Processing information
    processing_error TEXT,
    upload_completed_at BIGINT,  -- Unix timestamp when upload was completed

    -- Standard BaseModel fields
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_date TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_date TIMESTAMP WITH TIME ZONE,

    -- Constraints
    CONSTRAINT chk_file_size_positive CHECK (file_size IS NULL OR file_size >= 0)
);

-- Create indexes for efficient queries
CREATE INDEX idx_files_org_type ON files(organization_id, file_type);
CREATE INDEX idx_files_status ON files(status);
CREATE INDEX idx_files_related_entity ON files(related_entity_type, related_entity_id);
CREATE INDEX idx_files_uploader ON files(uploader_id);
CREATE INDEX idx_files_created_date ON files(created_date);
CREATE INDEX idx_files_is_active ON files(is_active);
CREATE INDEX idx_files_s3_key ON files(s3_key);

-- Add trigger to automatically update updated_date
CREATE OR REPLACE FUNCTION update_files_updated_date()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_files_updated_date
    BEFORE UPDATE ON files
    FOR EACH ROW
    EXECUTE FUNCTION update_files_updated_date();

-- Add comments for documentation
COMMENT ON TABLE files IS 'Centralized file storage management - tracks all uploaded files with S3 URLs and metadata';
COMMENT ON COLUMN files.url IS 'Full S3 URL of the file';
COMMENT ON COLUMN files.s3_key IS 'S3 key/path within the bucket';
COMMENT ON COLUMN files.file_type IS 'Type of file (transaction_image, profile_image, document, etc.)';
COMMENT ON COLUMN files.status IS 'Current status of the file (pending, uploaded, processing, failed, deleted)';
COMMENT ON COLUMN files.organization_id IS 'Organization that owns this file';
COMMENT ON COLUMN files.uploader_id IS 'User location ID who uploaded this file';
COMMENT ON COLUMN files.related_entity_type IS 'Type of entity this file is related to (optional)';
COMMENT ON COLUMN files.related_entity_id IS 'ID of the related entity (optional)';
COMMENT ON COLUMN files.metadata IS 'Additional metadata in JSON format (dimensions, duration, etc.)';
COMMENT ON COLUMN files.upload_completed_at IS 'Unix timestamp when upload was completed';

-- Grant permissions (adjust as needed for your application)
-- GRANT SELECT, INSERT, UPDATE ON files TO your_app_user;
-- GRANT USAGE ON SEQUENCE files_id_seq TO your_app_user;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Migration 052: Files table created successfully with indexes and triggers';
END $$;
