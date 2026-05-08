-- Description: Fix missing primary keys on pre-existing tables (dedup + PK constraints)
-- This migration is idempotent: it skips dedup/PK if the table already has a PK.

DO $$
BEGIN
    -- 1. organizations: dedup + add PK (only if missing)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'organizations'::regclass AND contype = 'p'
    ) THEN
        DELETE FROM organizations a USING organizations b
            WHERE a.id = b.id AND a.ctid < b.ctid;
        ALTER TABLE organizations ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);
        RAISE NOTICE 'Added PK to organizations';
    ELSE
        RAISE NOTICE 'organizations already has PK, skipping';
    END IF;

    -- 2. esg_data_entries: dedup + add PK (only if missing)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'esg_data_entries'::regclass AND contype = 'p'
    ) THEN
        DELETE FROM esg_data_entries a USING esg_data_entries b
            WHERE a.id = b.id AND a.ctid < b.ctid;
        ALTER TABLE esg_data_entries ADD CONSTRAINT esg_data_entries_pkey PRIMARY KEY (id);
        RAISE NOTICE 'Added PK to esg_data_entries';
    ELSE
        RAISE NOTICE 'esg_data_entries already has PK, skipping';
    END IF;

    -- 3. esg_datapoint: dedup + add PK (only if missing)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'esg_datapoint'::regclass AND contype = 'p'
    ) THEN
        DELETE FROM esg_datapoint a USING esg_datapoint b
            WHERE a.id = b.id AND a.ctid < b.ctid;
        ALTER TABLE esg_datapoint ADD CONSTRAINT esg_datapoint_pkey PRIMARY KEY (id);
        RAISE NOTICE 'Added PK to esg_datapoint';
    ELSE
        RAISE NOTICE 'esg_datapoint already has PK, skipping';
    END IF;

    -- 4. esg_data_category: dedup + add PK (only if missing)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'esg_data_category'::regclass AND contype = 'p'
    ) THEN
        DELETE FROM esg_data_category a USING esg_data_category b
            WHERE a.id = b.id AND a.ctid < b.ctid;
        ALTER TABLE esg_data_category ADD CONSTRAINT esg_data_category_pkey PRIMARY KEY (id);
        RAISE NOTICE 'Added PK to esg_data_category';
    ELSE
        RAISE NOTICE 'esg_data_category already has PK, skipping';
    END IF;
END $$;
