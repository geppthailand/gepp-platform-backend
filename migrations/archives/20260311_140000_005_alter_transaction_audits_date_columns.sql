-- Migration: Convert transaction_audits date columns from BIGINT to TIMESTAMPTZ
-- Date: 2026-03-11
-- Description: Change created_date, updated_date, deleted_date from BIGINT (epoch ms) to TIMESTAMPTZ

-- Convert existing BIGINT values (milliseconds since epoch) to TIMESTAMPTZ
ALTER TABLE transaction_audits
    ALTER COLUMN created_date TYPE TIMESTAMPTZ USING
        CASE WHEN created_date IS NOT NULL THEN to_timestamp(created_date::double precision / 1000.0) ELSE NULL END,
    ALTER COLUMN updated_date TYPE TIMESTAMPTZ USING
        CASE WHEN updated_date IS NOT NULL THEN to_timestamp(updated_date::double precision / 1000.0) ELSE NULL END,
    ALTER COLUMN deleted_date TYPE TIMESTAMPTZ USING
        CASE WHEN deleted_date IS NOT NULL THEN to_timestamp(deleted_date::double precision / 1000.0) ELSE NULL END;

-- Set default values for new records
ALTER TABLE transaction_audits
    ALTER COLUMN created_date SET DEFAULT NOW(),
    ALTER COLUMN updated_date SET DEFAULT NOW();
