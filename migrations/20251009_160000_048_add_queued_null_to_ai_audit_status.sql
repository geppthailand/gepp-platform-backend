-- Migration: Add 'queued' and 'null' values to ai_audit_status enum (Part 1)
-- Date: 2025-10-09 16:00:00
-- Description: Adds 'queued' and 'null' values to ai_audit_status_enum

-- Add new values to the enum
-- Note: ALTER TYPE ADD VALUE cannot be run inside a transaction block
-- If these values already exist, this migration will fail - that's okay, skip to next migration

-- Add 'null' value
ALTER TYPE ai_audit_status_enum ADD VALUE 'null';

-- Add 'queued' value
ALTER TYPE ai_audit_status_enum ADD VALUE 'queued';
