# GEPP Platform Database Migrations

This directory contains PostgreSQL migration scripts for the complete GEPP Platform database structure.

## Overview

The GEPP Platform uses a comprehensive database schema that supports multiple integrated modules for environmental compliance, sustainability reporting, AI-powered knowledge management, and user engagement.

## Migration Files

Migration files follow the naming pattern `{YYYYMMDD}_{HHMMSS}_{NNN}_{name}.sql` for chronological ordering.

| File | Description |
|------|-------------|
| `20250904_120000_001_core_foundation.sql` | Location hierarchy, currencies, materials, and reference data |
| `20250904_120500_002_user_management.sql` | User locations, authentication, roles, and sessions |
| `20250904_121000_003_organization_subscription.sql` | Organizations, subscription plans, billing, and permissions |
| `20250904_121500_004_add_foreign_keys.sql` | Foreign key constraints between core tables |
| `20250904_122000_005_transaction_system.sql` | Waste transactions, processing, payments, and analytics |
| `20250904_122500_006_epr_compliance.sql` | Extended Producer Responsibility compliance and reporting |
| `20250904_123000_007_gri_rewards_km.sql` | GRI reporting, rewards system, knowledge management, and experts |
| `20250904_123500_008_chat_logs_system.sql` | Chat system, meetings, audit logs, and platform logs |

## Prerequisites

- PostgreSQL 17.4+ with the following extensions:
  - `uuid-ossp` - UUID generation
  - `pgcrypto` - Cryptographic functions
  - `vector` - pgvector 0.8.0+ for AI embeddings (install from https://github.com/pgvector/pgvector)

## Quick Start

### 1. Install pgvector Extension

```bash
# Ubuntu/Debian (PostgreSQL 17)
sudo apt install postgresql-17-pgvector

# macOS with Homebrew
brew install pgvector

# Or build from source (recommended for latest version)
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# Enable extension in PostgreSQL
psql -d your_database -c "CREATE EXTENSION vector;"
```

### 2. Install Additional Tools (macOS only)

```bash
# For better timing precision and compatibility on macOS
brew install coreutils

# This provides gdate and md5sum commands
```

### 3. Configure Database Connection

Create a `.env` file in the migrations directory:

```bash
# Database connection settings
DB_HOST=localhost
DB_PORT=5432
DB_NAME=gepp_platform
DB_USER=postgres
DB_PASSWORD=your_password
```

### 4. Run Migrations

```bash
# Run all migrations (loads .env automatically)
./run_migrations.sh

# Alternative: Set environment variables manually
export DB_HOST=localhost DB_PORT=5432 DB_NAME=gepp_platform DB_USER=postgres DB_PASSWORD=your_password
./run_migrations.sh
```

### 5. Check Migration Status

```bash
# View completed migrations
./run_migrations.sh status
```

## Manual Migration

If you prefer to run migrations manually:

```bash
# Create database
createdb gepp_platform

# Run migrations in chronological order
psql -d gepp_platform -f 20250904_120000_001_core_foundation.sql
psql -d gepp_platform -f 20250904_120500_002_user_management.sql
psql -d gepp_platform -f 20250904_121000_003_organization_subscription.sql
psql -d gepp_platform -f 20250904_121500_004_add_foreign_keys.sql
psql -d gepp_platform -f 20250904_122000_005_transaction_system.sql
psql -d gepp_platform -f 20250904_122500_006_epr_compliance.sql
psql -d gepp_platform -f 20250904_123000_007_gri_rewards_km.sql
psql -d gepp_platform -f 20250904_123500_008_chat_logs_system.sql
```

## Database Schema Overview

### Core Architecture

- **Multi-tenant**: Organization-based data isolation
- **Audit-ready**: Comprehensive change tracking
- **AI-powered**: Vector embeddings for semantic search
- **Platform-agnostic**: Supports GEPP_360, GEPP_BUSINESS, GEPP_EPR

### Key Features

1. **Geographic Hierarchy**: Countries → Regions → Provinces → Districts → Subdistricts
2. **Material Classification**: Hierarchical waste and material categorization
3. **Multi-currency Support**: Global financial operations
4. **Vector Search**: pgvector integration for AI-powered document search
5. **Comprehensive Auditing**: Complete activity logging for compliance

### Module Integration

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│    Cores    │───▶│    Users     │───▶│Subscriptions│
│ Foundation  │    │Organization  │    │  Billing    │
└─────────────┘    └──────────────┘    └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│Transactions │    │     EPR      │    │     GRI     │
│   Waste     │    │ Compliance   │    │ Reporting   │
└─────────────┘    └──────────────┘    └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Rewards   │    │      KM      │    │    Chats    │
│Gamification │    │   AI Docs    │    │  AI Agents  │
└─────────────┘    └──────────────┘    └─────────────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                   ┌─────────────┐
                   │    Logs     │
                   │ Audit Trail │
                   └─────────────┘
```

## Performance Considerations

### Indexes

All tables include strategic indexes for:
- Primary and foreign key relationships
- Frequently queried columns (status, dates, UUIDs)
- Full-text search fields
- Vector similarity search (pgvector)

### Vector Search Optimization

```sql
-- Optimize vector search performance
ANALYZE km_chunks;

-- Monitor index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch 
FROM pg_stat_user_indexes 
WHERE indexname LIKE '%embedding%';

-- For pgvector 0.8.0+ with HNSW index
-- Adjust search parameters for better performance
SET hnsw.ef_search = 40; -- Default is 40, increase for better recall
```

### Connection Pooling

For production deployments, use connection pooling:
- **PgBouncer** for connection pooling
- **HAProxy** for load balancing
- **Read replicas** for analytics queries

## Security Features

- **Row Level Security**: Organization-based data access
- **Audit Logging**: Complete activity tracking
- **Encrypted Storage**: Sensitive data protection
- **Role-based Access**: Granular permissions

## Backup and Recovery

```bash
# Full database backup
pg_dump gepp_platform > gepp_platform_backup.sql

# Schema-only backup
pg_dump --schema-only gepp_platform > gepp_platform_schema.sql

# Data-only backup
pg_dump --data-only gepp_platform > gepp_platform_data.sql
```

## Monitoring and Maintenance

### Database Health Checks

```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('gepp_platform'));

-- Monitor connection usage
SELECT count(*) FROM pg_stat_activity WHERE datname = 'gepp_platform';

-- Check slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
```

### Regular Maintenance

```sql
-- Update table statistics
ANALYZE;

-- Vacuum unused space
VACUUM ANALYZE;

-- Reindex for optimal performance
REINDEX DATABASE gepp_platform;
```

## Troubleshooting

### Common Issues

1. **pgvector not found**
   ```bash
   # Install pgvector extension for PostgreSQL 17
   sudo apt install postgresql-17-pgvector
   
   # Or build from source for version 0.8.0
   git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
   cd pgvector && make && sudo make install
   ```

2. **Permission denied**
   ```bash
   # Check PostgreSQL user permissions
   psql -c "ALTER USER postgres CREATEDB;"
   ```

3. **Migration fails**
   ```bash
   # Check migration status
   ./run_migrations.sh status
   
   # View detailed error logs
   tail -f /var/log/postgresql/postgresql-12-main.log
   ```

### Performance Issues

1. **Slow vector searches**
   ```sql
   -- Rebuild vector index with HNSW (pgvector 0.8.0+)
   DROP INDEX idx_km_chunks_embedding;
   CREATE INDEX idx_km_chunks_embedding ON km_chunks 
   USING hnsw (embedding vector_cosine_ops) 
   WITH (m = 16, ef_construction = 64);
   
   -- For older pgvector versions, use IVFFlat
   -- CREATE INDEX idx_km_chunks_embedding ON km_chunks 
   -- USING ivfflat (embedding vector_cosine_ops) 
   -- WITH (lists = 100);
   ```

2. **High memory usage**
   ```sql
   -- Adjust PostgreSQL configuration
   -- shared_buffers = 256MB
   -- effective_cache_size = 1GB
   -- work_mem = 4MB
   ```

## Support

For technical support or questions about the database schema:

1. Check the [CONCEPT.md](../CONCEPT.md) for system architecture overview
2. Review module-specific documentation in each model directories
3. Consult PostgreSQL documentation for performance tuning
4. Contact the development team for schema modifications

## Migration History

- **20250904_123500_008**: Chat system, meetings, audit logs, and platform logs
- **20250904_123000_007**: GRI reporting, rewards system, knowledge management, and experts  
- **20250904_122500_006**: Extended Producer Responsibility compliance and reporting
- **20250904_122000_005**: Waste transactions, processing, payments, and analytics
- **20250904_121500_004**: Foreign key constraints between core tables
- **20250904_121000_003**: Organizations, subscription plans, billing, and permissions
- **20250904_120500_002**: User locations, authentication, roles, and sessions
- **20250904_120000_001**: Location hierarchy, currencies, materials, and reference data

## PostgreSQL 17.4 & pgvector 0.8.0 Features

### New in PostgreSQL 17.4
- Enhanced JSON performance and features
- Improved query optimization
- Better parallel processing capabilities
- Enhanced security features

### New in pgvector 0.8.0
- **HNSW Index Support**: Better performance than IVFFlat for most use cases
- **Improved Memory Usage**: More efficient memory management
- **Better Parallel Processing**: Enhanced parallel query support
- **New Distance Functions**: Additional similarity metrics
- **Performance Improvements**: Up to 3x faster similarity search

### HNSW vs IVFFlat Comparison

| Feature | HNSW | IVFFlat |
|---------|------|---------|
| Build Time | Slower | Faster |
| Query Speed | Faster | Slower |
| Memory Usage | Higher | Lower |
| Recall Quality | Better | Good |
| Best Use Case | Production queries | Rapid prototyping |

Use HNSW for production workloads where query performance is critical.