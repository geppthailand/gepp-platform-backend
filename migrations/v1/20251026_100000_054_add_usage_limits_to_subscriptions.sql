-- Migration: Add transaction and AI audit usage limits to subscriptions
-- Version: 054
-- Date: 2025-10-26
-- Description: Add create_transaction_limit, create_transaction_usage, ai_audit_limit, ai_audit_usage columns to subscriptions table

-- Add create_transaction_limit column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'subscriptions'
        AND column_name = 'create_transaction_limit'
    ) THEN
        ALTER TABLE subscriptions
        ADD COLUMN create_transaction_limit INTEGER DEFAULT 100;

        RAISE NOTICE 'Added create_transaction_limit column to subscriptions';
    ELSE
        RAISE NOTICE 'Column create_transaction_limit already exists in subscriptions';
    END IF;
END $$;

-- Add create_transaction_usage column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'subscriptions'
        AND column_name = 'create_transaction_usage'
    ) THEN
        ALTER TABLE subscriptions
        ADD COLUMN create_transaction_usage INTEGER DEFAULT 0;

        RAISE NOTICE 'Added create_transaction_usage column to subscriptions';
    ELSE
        RAISE NOTICE 'Column create_transaction_usage already exists in subscriptions';
    END IF;
END $$;

-- Add ai_audit_limit column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'subscriptions'
        AND column_name = 'ai_audit_limit'
    ) THEN
        ALTER TABLE subscriptions
        ADD COLUMN ai_audit_limit INTEGER DEFAULT 10;

        RAISE NOTICE 'Added ai_audit_limit column to subscriptions';
    ELSE
        RAISE NOTICE 'Column ai_audit_limit already exists in subscriptions';
    END IF;
END $$;

-- Add ai_audit_usage column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'subscriptions'
        AND column_name = 'ai_audit_usage'
    ) THEN
        ALTER TABLE subscriptions
        ADD COLUMN ai_audit_usage INTEGER DEFAULT 0;

        RAISE NOTICE 'Added ai_audit_usage column to subscriptions';
    ELSE
        RAISE NOTICE 'Column ai_audit_usage already exists in subscriptions';
    END IF;
END $$;

-- Create index for faster queries on usage columns
CREATE INDEX IF NOT EXISTS idx_subscriptions_usage
ON subscriptions(organization_id, create_transaction_usage, create_transaction_limit);

-- Verify the columns were added
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_name = 'subscriptions'
    AND column_name IN ('create_transaction_limit', 'create_transaction_usage', 'ai_audit_limit', 'ai_audit_usage');

    IF v_count = 4 THEN
        RAISE NOTICE 'Migration completed successfully. All 4 columns added to subscriptions table.';
    ELSE
        RAISE WARNING 'Migration incomplete. Expected 4 columns, found %', v_count;
    END IF;
END $$;
