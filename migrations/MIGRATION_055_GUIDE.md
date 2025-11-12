# Migration 055 - BMA Integration Files Compatibility Guide

## Overview
This migration ensures the `files` table has all required columns for BMA integration to work properly. It is **idempotent** and can be safely run multiple times.

## Issue Being Resolved
The BMA integration (`/api/integration/bma/transaction`) was failing with error:
```
column files.source does not exist
```

This migration ensures both `observation` and `source` columns exist in the files table.

## Files Involved
1. **Migration File**: `20251107_120000_055_ensure_files_bma_compatibility.sql`
2. **Verification Script**: `verify_files_schema.sql`

## Step-by-Step Execution

### Step 1: Run the Migration

**Using psql directly:**
```bash
psql -h your-database-host \
     -U your-database-user \
     -d your-database-name \
     -f backend/migrations/20251107_120000_055_ensure_files_bma_compatibility.sql
```

**Using migration runner:**
```bash
cd backend/migrations
./run_migrations.sh
```

### Step 2: Verify the Migration

**Run verification script:**
```bash
psql -h your-database-host \
     -U your-database-user \
     -d your-database-name \
     -f backend/migrations/verify_files_schema.sql
```

**Expected Output:**
```
enum_check
--------------------------------
✓ file_source ENUM exists

column_name  | data_type | is_nullable | column_default
-------------+-----------+-------------+---------------
url          | text      | YES         | NULL
s3_key       | text      | YES         | NULL
s3_bucket    | text      | YES         | NULL
source       | USER-DEFINED | YES      | 's3'::file_source
observation  | jsonb     | YES         | NULL

indexname              | indexdef
-----------------------+--------------------------------------------
idx_files_observation  | CREATE INDEX idx_files_observation ON ...
idx_files_source       | CREATE INDEX idx_files_source ON ...
```

### Step 3: Redeploy Lambda Function (CRITICAL)

After running the migration, you **MUST** redeploy the Lambda function to pick up the database changes:

```bash
cd backend
./update_function.sh
```

**Why this is necessary:**
- Lambda may cache database connections
- Lambda may be using old code that doesn't reference new columns
- Connection pooling may need to refresh

### Step 4: Test BMA Integration

**Run the mock BMA API test:**
```bash
cd Audit
python mock_bma_api.py
```

**Expected behavior:**
1. Images uploaded to S3 successfully
2. Transactions created via `/api/integration/bma/transaction`
3. Transaction records created with file IDs (not raw URLs)
4. No errors about missing `files.source` column

### Step 5: Verify in Database

**Check that file records were created:**
```sql
SELECT
    f.id,
    f.source,
    f.file_type,
    LEFT(f.url, 80) AS url,
    tr.id AS transaction_record_id,
    t.id AS transaction_id
FROM files f
LEFT JOIN transaction_records tr ON f.related_entity_id = tr.id
    AND f.related_entity_type = 'transaction_record'
LEFT JOIN transactions t ON tr.transaction_id = t.id
WHERE f.file_type = 'transaction_record_image'
ORDER BY f.created_at DESC
LIMIT 10;
```

**Check that transaction records exist:**
```sql
SELECT
    t.id AS transaction_id,
    t.external_transaction_id,
    COUNT(tr.id) AS record_count
FROM transactions t
LEFT JOIN transaction_records tr ON tr.transaction_id = t.id
WHERE t.created_at > NOW() - INTERVAL '1 hour'
GROUP BY t.id, t.external_transaction_id
ORDER BY t.created_at DESC;
```

## Troubleshooting

### Issue: Migration runs but columns still missing

**Diagnosis:**
```sql
SELECT * FROM information_schema.columns
WHERE table_name = 'files' AND column_name IN ('source', 'observation');
```

**If empty:** Database user may not have ALTER TABLE permissions.

**Solution:** Grant permissions:
```sql
GRANT ALL PRIVILEGES ON TABLE files TO your_database_user;
```

### Issue: Column exists but Lambda still gets error

**Diagnosis:** Lambda is using cached code or connected to wrong database.

**Solution:**
1. Check Lambda environment variables for database connection
2. Redeploy Lambda function: `./update_function.sh`
3. Restart Lambda by updating environment variable (triggers fresh deployment)
4. Check CloudWatch logs for actual database being used

### Issue: Migration runs but enum type fails

**Diagnosis:**
```sql
SELECT typname FROM pg_type WHERE typname = 'file_source';
```

**If empty:** Need to create enum manually:
```sql
CREATE TYPE file_source AS ENUM ('s3', 'ext');
```

### Issue: Files created but source is NULL

**Diagnosis:**
```sql
SELECT id, source, url FROM files WHERE source IS NULL LIMIT 5;
```

**Solution:** Update existing records:
```sql
UPDATE files
SET source = CASE
    WHEN url LIKE '%s3.amazonaws.com%' THEN 's3'::file_source
    ELSE 'ext'::file_source
END
WHERE source IS NULL;
```

## Migration Success Indicators

✅ **All of these should be true:**
1. Migration script completes with "SUCCESS" message
2. Verification script shows both columns exist
3. `file_source` enum exists with values 's3' and 'ext'
4. Indexes `idx_files_observation` and `idx_files_source` exist
5. Lambda function redeployed successfully
6. Mock BMA API test creates transactions with records
7. No errors in CloudWatch logs about missing columns

## Rollback (If Needed)

This migration is **additive only** - it doesn't modify or delete existing data. Rolling back is generally not necessary, but if required:

```sql
-- Remove indexes
DROP INDEX IF EXISTS idx_files_observation;
DROP INDEX IF EXISTS idx_files_source;

-- Remove columns
ALTER TABLE files DROP COLUMN IF EXISTS observation;
ALTER TABLE files DROP COLUMN IF EXISTS source;

-- Remove enum type (only if no other tables use it)
DROP TYPE IF EXISTS file_source;
```

⚠️ **WARNING:** Only rollback if absolutely necessary. This will break BMA integration.

## Post-Migration Checklist

- [ ] Migration 055 executed successfully
- [ ] Verification script confirms columns exist
- [ ] Lambda function redeployed
- [ ] Mock BMA API test passes
- [ ] Production BMA transactions working
- [ ] No errors in CloudWatch logs
- [ ] Transaction records being created
- [ ] File IDs being stored (not raw URLs)
- [ ] Documentation updated

## Support

If issues persist after following this guide:

1. **Check database connection:** Verify Lambda is connecting to the correct database
2. **Check permissions:** Ensure database user has ALTER TABLE rights
3. **Check deployment:** Verify Lambda code is latest version
4. **Check logs:** Review CloudWatch logs for actual error messages
5. **Check migration history:** Verify migration 055 is recorded in migrations table

## Related Files

- **BMA Service**: `backend/GEPPPlatform/services/integrations/bma/bma_service.py`
- **File Model**: `backend/GEPPPlatform/models/km/files.py`
- **Migration 053**: `backend/migrations/20251106_180000_053_add_observation_to_files.sql`
- **Documentation**: `backend/docs/versions/v0.0.7_20251106.md`
