-- Migration: Create integration_tokens table and add integration_id to transactions
-- Date: 2025-10-28
-- Description: Track integration tokens used for API access and link transactions to their source tokens

-- Create integration_tokens table
CREATE TABLE IF NOT EXISTS integration_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    jwt TEXT NOT NULL,
    description TEXT,
    valid BOOLEAN NOT NULL DEFAULT true,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMPTZ,

    -- Foreign key
    CONSTRAINT fk_integration_tokens_user
        FOREIGN KEY (user_id)
        REFERENCES user_locations(id)
        ON DELETE CASCADE
);

-- Add indexes
CREATE INDEX idx_integration_tokens_user_id ON integration_tokens(user_id);
CREATE INDEX idx_integration_tokens_jwt ON integration_tokens(jwt) WHERE deleted_date IS NULL;
CREATE INDEX idx_integration_tokens_valid ON integration_tokens(valid) WHERE deleted_date IS NULL;

-- Add integration_id column to transactions table
ALTER TABLE transactions
ADD COLUMN integration_id INTEGER,
ADD CONSTRAINT fk_transactions_integration_token
    FOREIGN KEY (integration_id)
    REFERENCES integration_tokens(id)
    ON DELETE SET NULL;

-- Add index for integration_id
CREATE INDEX idx_transactions_integration_id ON transactions(integration_id);

-- Add comment
COMMENT ON TABLE integration_tokens IS 'Stores integration tokens for API access tracking';
COMMENT ON COLUMN integration_tokens.jwt IS 'The JWT token string used for authentication';
COMMENT ON COLUMN integration_tokens.description IS 'Optional description of the integration token';
COMMENT ON COLUMN integration_tokens.valid IS 'Whether the token is currently valid (separate from is_active for token-specific validation)';
COMMENT ON COLUMN integration_tokens.is_active IS 'Standard soft delete flag (inherited from BaseModel)';
COMMENT ON COLUMN transactions.integration_id IS 'Links transaction to the integration token that created it';
