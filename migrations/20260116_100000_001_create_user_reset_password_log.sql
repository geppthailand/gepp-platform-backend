-- Migration: Create user_reset_password_log table
-- Date: 2026-01-16
-- Description: Track password reset requests with JWT tokens, user info, and device information

-- Create user_reset_password_log table
CREATE TABLE IF NOT EXISTS user_reset_password_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    user_agent TEXT,
    jwt TEXT NOT NULL,
    device_type TEXT,
    ip_address TEXT,
    user_identification TEXT NOT NULL,
    expires TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMPTZ,

    -- Foreign key
    CONSTRAINT fk_user_reset_password_log_user
        FOREIGN KEY (user_id)
        REFERENCES user_locations(id)
        ON DELETE CASCADE
);

-- Add indexes
CREATE INDEX idx_user_reset_password_log_user_id ON user_reset_password_log(user_id) WHERE deleted_date IS NULL;
CREATE INDEX idx_user_reset_password_log_jwt ON user_reset_password_log(jwt) WHERE deleted_date IS NULL;
CREATE INDEX idx_user_reset_password_log_user_jwt ON user_reset_password_log(user_id, jwt) WHERE deleted_date IS NULL;
CREATE INDEX idx_user_reset_password_log_expires ON user_reset_password_log(expires) WHERE deleted_date IS NULL;

-- Add comments
COMMENT ON TABLE user_reset_password_log IS 'Stores password reset request logs with JWT tokens and device information';
COMMENT ON COLUMN user_reset_password_log.user_id IS 'Foreign key to user_locations.id';
COMMENT ON COLUMN user_reset_password_log.user_agent IS 'User browser or client user agent string';
COMMENT ON COLUMN user_reset_password_log.jwt IS 'JWT token used for password reset';
COMMENT ON COLUMN user_reset_password_log.device_type IS 'Device information of the user';
COMMENT ON COLUMN user_reset_password_log.ip_address IS 'IP address of the user making the request';
COMMENT ON COLUMN user_reset_password_log.user_identification IS 'User email address';
COMMENT ON COLUMN user_reset_password_log.expires IS 'Token expiration timestamp';
