# Special Instructions for Migrations 048 and 049

## Issue

PostgreSQL's `ALTER TYPE ... ADD VALUE` cannot be executed inside a transaction block. Most migration runners wrap migrations in transactions, which causes this error:

```
ERROR: unsafe use of new value "null" of enum type ai_audit_status_enum
HINT: New enum values must be committed before they can be used.
```

## Solution: Run Manually

You need to run these migrations **manually** and **outside of the migration runner**.

### Step 1: Run Migration 048 (Add Enum Values)

```bash
# Connect to your database directly
psql $DATABASE_URL

# Run this SQL directly (NOT in a transaction)
ALTER TYPE ai_audit_status_enum ADD VALUE 'null';
ALTER TYPE ai_audit_status_enum ADD VALUE 'queued';

# Exit psql
\q
```

### Step 2: Mark Migration 048 as Complete

```bash
# Add a record to migrations table to mark it as complete
psql $DATABASE_URL -c "INSERT INTO migrations (migration_name, executed_at) VALUES ('20251009_160000_048_add_queued_null_to_ai_audit_status.sql', NOW()) ON CONFLICT DO NOTHING;"
```

### Step 3: Run Migration 049 (Use New Enum Values)

Now you can run migration 049 normally through your migration runner:

```bash
# Run your migration script
./run_migrations.sh
```

Or run it manually:

```bash
psql $DATABASE_URL -f /Users/tanawatgepp/Documents/Workspace/gepp-platform/backend/migrations/20251009_160100_049_update_ai_audit_status_default.sql
```

## Alternative: Modify Migration Runner

If you want to avoid manual steps in the future, modify your migration runner to detect `ALTER TYPE ... ADD VALUE` commands and execute those migrations without wrapping them in transactions.

Example bash script modification:

```bash
# In run_migrations.sh, detect enum migrations
if grep -q "ALTER TYPE.*ADD VALUE" "$migration_file"; then
    echo "Running enum migration without transaction..."
    psql $DATABASE_URL -f "$migration_file"
else
    echo "Running normal migration with transaction..."
    psql $DATABASE_URL <<EOF
BEGIN;
\i $migration_file
COMMIT;
EOF
fi
```

## Verification

After running both migrations, verify they worked:

```sql
-- Check enum values exist
SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'ai_audit_status_enum'::regtype
ORDER BY enumlabel;

-- Should show: approved, no_action, null, queued, rejected

-- Check default value is set
SELECT column_name, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'transactions'
  AND column_name = 'ai_audit_status';

-- Should show: column_default = 'null', is_nullable = 'NO'
```

## Quick Fix Script

Here's a complete script to run both migrations manually:

```bash
#!/bin/bash
set -e

echo "Adding enum values to ai_audit_status_enum..."
psql $DATABASE_URL <<EOF
-- Add enum values (no transaction)
ALTER TYPE ai_audit_status_enum ADD VALUE 'null';
ALTER TYPE ai_audit_status_enum ADD VALUE 'queued';
EOF

echo "Marking migration 048 as complete..."
psql $DATABASE_URL -c "INSERT INTO migrations (migration_name, executed_at) VALUES ('20251009_160000_048_add_queued_null_to_ai_audit_status.sql', NOW()) ON CONFLICT DO NOTHING;"

echo "Running migration 049..."
psql $DATABASE_URL -f backend/migrations/20251009_160100_049_update_ai_audit_status_default.sql

echo "Marking migration 049 as complete..."
psql $DATABASE_URL -c "INSERT INTO migrations (migration_name, executed_at) VALUES ('20251009_160100_049_update_ai_audit_status_default.sql', NOW()) ON CONFLICT DO NOTHING;"

echo "Verifying migrations..."
psql $DATABASE_URL <<EOF
SELECT 'Enum values:' as status;
SELECT enumlabel FROM pg_enum WHERE enumtypid = 'ai_audit_status_enum'::regtype ORDER BY enumlabel;

SELECT 'Column info:' as status;
SELECT column_default, is_nullable FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'ai_audit_status';
EOF

echo "Migrations 048 and 049 completed successfully!"
```

Save this as `run_migrations_048_049.sh` and execute it:

```bash
chmod +x run_migrations_048_049.sh
./run_migrations_048_049.sh
```
