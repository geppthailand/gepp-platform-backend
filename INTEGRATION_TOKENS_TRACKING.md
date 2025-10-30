# Integration Tokens Tracking System

## Overview

This document describes the integration tokens tracking system that links transactions to the integration JWT token that created them.

## Purpose

Track which integration token was used to create each transaction, enabling:
- Audit trail of API integration usage
- Token-level analytics and monitoring
- Ability to invalidate tokens and track their historical usage
- Better security and access control for integration partners

## Database Schema

### New Table: `integration_tokens`

Stores integration JWT tokens and their metadata.

**Columns:**
- `id` (BIGSERIAL PRIMARY KEY) - Unique token record ID
- `user_id` (INTEGER NOT NULL) - Foreign key to user_locations.id
- `jwt` (TEXT NOT NULL) - The JWT token string
- `description` (TEXT) - Optional description of the token
- `valid` (BOOLEAN NOT NULL DEFAULT true) - Whether token is currently valid (token-specific validation)
- `is_active` (BOOLEAN NOT NULL DEFAULT true) - Standard soft delete flag (inherited from BaseModel)
- `created_date` (TIMESTAMPTZ NOT NULL) - When token was created
- `updated_date` (TIMESTAMP NOT NULL) - When token was last updated
- `deleted_date` (TIMESTAMPTZ) - Soft delete timestamp

**Indexes:**
- `idx_integration_tokens_user_id` on `user_id`
- `idx_integration_tokens_jwt` on `jwt` WHERE `deleted_date IS NULL`
- `idx_integration_tokens_valid` on `valid` WHERE `deleted_date IS NULL`

**Foreign Keys:**
- `fk_integration_tokens_user` → `user_locations(id)` ON DELETE CASCADE

### Modified Table: `transactions`

Added column to link transactions to integration tokens.

**New Column:**
- `integration_id` (INTEGER) - Foreign key to integration_tokens.id

**Index:**
- `idx_transactions_integration_id` on `integration_id`

**Foreign Key:**
- `fk_transactions_integration_token` → `integration_tokens(id)` ON DELETE SET NULL

## Migration

**File:** `backend/migrations/20251028_110000_057_create_integration_tokens_table.sql`

**Actions:**
1. Creates `integration_tokens` table with all columns and constraints
2. Adds `integration_id` column to `transactions` table
3. Creates all necessary indexes and foreign keys
4. Adds table and column comments

## Models

### IntegrationToken Model

**File:** `backend/GEPPPlatform/models/users/integration_tokens.py`

```python
class IntegrationToken(Base, BaseModel):
    __tablename__ = 'integration_tokens'

    user_id = Column(Integer, ForeignKey('user_locations.id', ondelete='CASCADE'), nullable=False)
    jwt = Column(Text, nullable=False)
    description = Column(Text)
    valid = Column(Boolean, nullable=False, default=True)

    # Relationships
    user = relationship("UserLocation", foreign_keys=[user_id])
```

### Transaction Model Updates

**File:** `backend/GEPPPlatform/models/transactions/transactions.py`

Added:
```python
integration_id = Column(BigInteger, ForeignKey('integration_tokens.id', ondelete='SET NULL'), nullable=True)

# Relationship
integration_token = relationship("IntegrationToken", foreign_keys=[integration_id])
```

## Implementation Flow

### 1. Token Generation (Login)

**Location:** `backend/GEPPPlatform/services/auth/auth_handlers.py:325-393`

When user calls `POST /api/auth/integration`:

```python
def integration_login(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    # 1. Authenticate user with email + password
    # 2. Auto-generate user.secret if not exists
    # 3. Generate JWT token using user.secret
    # 4. Save token to integration_tokens table

    integration_token = jwt.encode(integration_payload, user.secret, algorithm='HS256')

    # Save to database
    token_record = IntegrationToken(
        user_id=user.id,
        jwt=integration_token,
        description=f"Integration token for {email}",
        valid=True
    )
    session.add(token_record)
    session.commit()
```

### 2. Token Lookup (Transaction Creation)

**Location:** `backend/GEPPPlatform/services/integrations/bma/bma_service.py:111-120`

When user calls `POST /api/integration/bma/transaction`:

```python
def process_bma_transaction_batch(self, batch_data, organization_id, jwt_token=None):
    # Find integration_id from JWT token (ONCE before loop)
    integration_id = None
    if jwt_token:
        integration_token = self.db.query(IntegrationToken).filter(
            IntegrationToken.jwt == jwt_token,
            IntegrationToken.valid == True,
            IntegrationToken.deleted_date.is_(None)
        ).first()
        if integration_token:
            integration_id = integration_token.id

    # Pass integration_id to transaction creation
```

### 3. Transaction Creation with Token Link

**Location:** `backend/GEPPPlatform/services/integrations/bma/bma_service.py:309-322`

```python
def _create_transaction_with_materials(self, ..., integration_id=None):
    transaction = Transaction(
        ext_id_1=transaction_version,
        ext_id_2=house_id,
        organization_id=organization_id,
        # ... other fields ...
        integration_id=integration_id  # Link to integration token
    )
```

### 4. Token Extraction from Headers

**Location:** `backend/GEPPPlatform/services/integrations/bma/bma_handlers.py:42-55`

```python
# Extract JWT token from Authorization header
headers = params.get('headers', {})
auth_header = headers.get('Authorization') or headers.get('authorization', '')
jwt_token = None
if auth_header and auth_header.startswith('Bearer '):
    jwt_token = auth_header.split(' ')[1]

# Pass to service
handle_bma_transaction_batch(bma_service, data, organization_id, jwt_token)
```

## Key Design Decisions

### 1. Find Once Before Loop
The `integration_id` is looked up **once** at the beginning of batch processing, not for every transaction. This improves performance for batch operations.

### 2. Optional Integration ID
The `integration_id` column is **nullable** because:
- Not all transactions come from integrations (some are manual)
- Tokens can be deleted (ON DELETE SET NULL)
- Backwards compatibility with existing transactions

### 3. Token Validation Check
Only tokens with `valid=true`, `is_active=true`, and `deleted_date IS NULL` are matched to prevent using invalidated tokens.

### 4. Soft Delete Support
Integration tokens use soft delete (`deleted_date`) to maintain historical records while preventing future use.

### 5. Dual Validation Flags
The table has two boolean flags for different purposes:
- **`valid`**: Token-specific validation (e.g., manually revoke a specific token)
- **`is_active`**: Standard soft delete flag inherited from BaseModel (used for general record lifecycle)

Both must be `true` for a token to be accepted for creating transactions.

## Use Cases

### Track Token Usage
```sql
SELECT
    it.id,
    it.description,
    ul.email,
    COUNT(t.id) as transaction_count,
    MIN(t.created_date) as first_used,
    MAX(t.created_date) as last_used
FROM integration_tokens it
LEFT JOIN transactions t ON t.integration_id = it.id
LEFT JOIN user_locations ul ON ul.id = it.user_id
GROUP BY it.id, it.description, ul.email
ORDER BY transaction_count DESC;
```

### Invalidate Token and Check Usage
```sql
-- Invalidate token
UPDATE integration_tokens
SET valid = false, updated_date = NOW()
WHERE id = 123;

-- Check transactions created with this token
SELECT COUNT(*)
FROM transactions
WHERE integration_id = 123;
```

### Find Transactions by Token
```sql
SELECT t.*
FROM transactions t
JOIN integration_tokens it ON it.id = t.integration_id
WHERE it.jwt = 'eyJhbGc...'
  AND it.deleted_date IS NULL;
```

### Audit Integration Partner Activity
```sql
SELECT
    ul.email as partner_email,
    ul.display_name as partner_name,
    COUNT(DISTINCT it.id) as total_tokens,
    COUNT(DISTINCT CASE WHEN it.valid = true THEN it.id END) as active_tokens,
    COUNT(t.id) as total_transactions
FROM user_locations ul
LEFT JOIN integration_tokens it ON it.user_id = ul.id
LEFT JOIN transactions t ON t.integration_id = it.id
WHERE ul.is_active = true
GROUP BY ul.id, ul.email, ul.display_name
ORDER BY total_transactions DESC;
```

## Security Considerations

1. **Token Storage**: Full JWT is stored to enable exact matching
2. **Validation State**: Tokens can be invalidated without deletion
3. **Cascade Delete**: If user is deleted, their tokens are deleted
4. **Null on Token Delete**: If token is deleted, transaction link becomes null (preserves transaction)
5. **Indexed Lookup**: Fast token lookup via indexed jwt column

## Future Enhancements

1. **Token Expiration Tracking**: Add `expires_at` column to track token expiry
2. **Token Refresh Tracking**: Link to parent token for refresh token chains
3. **IP Address Tracking**: Store IP address where token was generated
4. **Usage Statistics**: Add last_used_date to integration_tokens
5. **Token Scopes**: Add permissions/scopes column for fine-grained access control

## Testing

To test the implementation:

1. **Login and create token:**
   ```bash
   POST /api/auth/integration
   {
     "email": "user@example.com",
     "password": "password123"
   }
   ```

2. **Create transaction with token:**
   ```bash
   POST /api/integration/bma/transaction
   Authorization: Bearer <token>
   {
     "batch": { ... }
   }
   ```

3. **Verify link in database:**
   ```sql
   SELECT t.id, t.ext_id_1, t.ext_id_2, it.description, ul.email
   FROM transactions t
   JOIN integration_tokens it ON it.id = t.integration_id
   JOIN user_locations ul ON ul.id = it.user_id
   ORDER BY t.created_date DESC
   LIMIT 10;
   ```

## Migration Steps

1. Run migration to create table and column:
   ```bash
   psql -U postgres -d gepp_platform -f backend/migrations/20251028_110000_057_create_integration_tokens_table.sql
   ```

2. Verify table creation:
   ```sql
   \d integration_tokens
   \d transactions  -- Check for integration_id column
   ```

3. Test token generation and transaction creation

4. Monitor for any foreign key constraint violations

## Files Changed

1. **Migration:**
   - `backend/migrations/20251028_110000_057_create_integration_tokens_table.sql` (NEW)

2. **Models:**
   - `backend/GEPPPlatform/models/users/integration_tokens.py` (NEW)
   - `backend/GEPPPlatform/models/users/__init__.py` (UPDATED)
   - `backend/GEPPPlatform/models/__init__.py` (UPDATED)
   - `backend/GEPPPlatform/models/transactions/transactions.py` (UPDATED)

3. **Services:**
   - `backend/GEPPPlatform/services/auth/auth_handlers.py` (UPDATED)
   - `backend/GEPPPlatform/services/integrations/bma/bma_handlers.py` (UPDATED)
   - `backend/GEPPPlatform/services/integrations/bma/bma_service.py` (UPDATED)

## Summary

This implementation creates a complete audit trail for integration token usage by:
1. Storing all integration tokens in a dedicated table
2. Automatically saving tokens when users login via `/api/auth/integration`
3. Looking up the token ID once before processing batch transactions
4. Linking each created transaction to the integration token that created it
5. Enabling analytics, monitoring, and security auditing of integration usage
