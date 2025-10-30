# Integration Tokens Migration Fix

## Issue

The initial migration `20251028_110000_057_create_integration_tokens_table.sql` was run without the `is_active` column, which is automatically included by SQLAlchemy's `BaseModel`.

### Error Encountered

```
column "is_active" of relation "integration_tokens" does not exist
```

This occurred because:
1. The `IntegrationToken` model inherits from `BaseModel`
2. `BaseModel` automatically adds: `id`, `is_active`, `created_date`, `updated_date`, `deleted_date`
3. The original migration didn't include `is_active` column

## Solution

Created a new migration to add the missing column:

**File:** `20251028_120000_058_add_is_active_to_integration_tokens.sql`

```sql
ALTER TABLE integration_tokens
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;
```

## Migration Order

Run migrations in this order:

1. ✅ `20251028_110000_057_create_integration_tokens_table.sql` (already run)
   - Created `integration_tokens` table (without `is_active`)
   - Added `integration_id` column to `transactions` table

2. 🔄 `20251028_120000_058_add_is_active_to_integration_tokens.sql` (needs to run)
   - Adds missing `is_active` column

## How to Apply

### Development Environment

```bash
psql -U postgres -d gepp_platform -f backend/migrations/20251028_120000_058_add_is_active_to_integration_tokens.sql
```

### Production/Staging

```bash
# Connect to database
psql -U <username> -d <database_name>

# Run migration
\i backend/migrations/20251028_120000_058_add_is_active_to_integration_tokens.sql

# Verify column exists
\d integration_tokens
```

## Verification

After running the migration, verify the table structure:

```sql
-- Check table structure
\d integration_tokens

-- Expected columns:
-- id              | bigint                      | not null default nextval('integration_tokens_id_seq'::regclass)
-- user_id         | integer                     | not null
-- jwt             | text                        | not null
-- description     | text                        |
-- valid           | boolean                     | not null default true
-- is_active       | boolean                     | not null default true  <-- NEW
-- created_date    | timestamp with time zone    | not null default CURRENT_TIMESTAMP
-- updated_date    | timestamp                   |
-- deleted_date    | timestamp with time zone    |
```

## Testing After Migration

1. **Login to get integration token:**
   ```bash
   POST /api/auth/integration
   {
     "email": "user@example.com",
     "password": "password123"
   }
   ```

2. **Verify token saved to database:**
   ```sql
   SELECT id, user_id, valid, is_active, description, created_date
   FROM integration_tokens
   ORDER BY created_date DESC
   LIMIT 5;
   ```

3. **Create transaction using token:**
   ```bash
   POST /api/integration/bma/transaction
   Authorization: Bearer <token>
   {
     "batch": { ... }
   }
   ```

4. **Verify integration_id is set:**
   ```sql
   SELECT t.id, t.ext_id_1, t.ext_id_2, t.integration_id, it.description
   FROM transactions t
   LEFT JOIN integration_tokens it ON it.id = t.integration_id
   WHERE t.integration_id IS NOT NULL
   ORDER BY t.created_date DESC
   LIMIT 10;
   ```

## Future Prevention

To prevent similar issues in the future:

1. **Always check BaseModel columns** when creating new tables that inherit from it:
   - `id` (BIGSERIAL)
   - `is_active` (BOOLEAN NOT NULL DEFAULT true)
   - `created_date` (TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)
   - `updated_date` (TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)
   - `deleted_date` (TIMESTAMPTZ)

2. **Test model creation** before deploying migration:
   ```python
   # Test that model can be instantiated and saved
   token = IntegrationToken(
       user_id=1,
       jwt="test_token",
       valid=True
   )
   session.add(token)
   session.commit()
   ```

3. **Review SQLAlchemy model** to ensure migration matches all columns

## Related Files

- Original migration: `backend/migrations/20251028_110000_057_create_integration_tokens_table.sql`
- Fix migration: `backend/migrations/20251028_120000_058_add_is_active_to_integration_tokens.sql`
- Model: `backend/GEPPPlatform/models/users/integration_tokens.py`
- BaseModel: `backend/GEPPPlatform/models/base.py`
- Documentation: `backend/INTEGRATION_TOKENS_TRACKING.md`

## Rollback (if needed)

If you need to rollback this migration:

```sql
ALTER TABLE integration_tokens DROP COLUMN IF EXISTS is_active;
```

**Note:** This should only be done if you also rollback the original migration and remove all IntegrationToken records.
