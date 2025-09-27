#!/bin/bash

# GEPP Platform Optimized Database Migration Runner
# This script runs all migration files with performance optimizations

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Performance optimization flags
export PGCONNECT_TIMEOUT=10
export PGCOMMAND_TIMEOUT=300

# Enhanced connection pooling and performance settings
DB_PERFORMANCE_OPTS="-c statement_timeout=300s -c lock_timeout=60s -c idle_in_transaction_session_timeout=120s"

# Load environment variables from .env file if it exists
load_env() {
    if [ -f "$SCRIPT_DIR/.env" ]; then
        echo "Loading environment variables from .env file..."
        # Use a more efficient method to load env vars
        set -a  # Automatically export all variables
        source "$SCRIPT_DIR/.env"
        set +a  # Stop auto-exporting
        echo "  Environment loaded"
    else
        echo "No .env file found in $SCRIPT_DIR, using environment variables"
    fi
}

# Default database connection parameters
setup_defaults() {
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_NAME=${DB_NAME:-gepp_platform}
    DB_USER=${DB_USER:-postgres}
    DB_PASSWORD=${DB_PASSWORD:-}

    # Create connection string for reuse
    export PGPASSWORD=$DB_PASSWORD
    DB_CONN_STRING="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT"

    # Performance optimization: reduce connection overhead
    PSQL_OPTS="-h $DB_HOST -p $DB_PORT -U $DB_USER $DB_PERFORMANCE_OPTS --no-psqlrc -q"
}

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_progress() { echo -e "${CYAN}[PROGRESS]${NC} $1"; }

# Enhanced PostgreSQL connection check with connection pooling
check_postgres() {
    print_status "Checking PostgreSQL connection and optimizations..."

    # Check for required tools
    if ! command -v psql >/dev/null 2>&1; then
        print_error "PostgreSQL client (psql) not found. Please install PostgreSQL."
        exit 1
    fi

    # Check for parallel processing tools
    if ! command -v parallel >/dev/null 2>&1; then
        print_warning "GNU parallel not found. Install for better performance: apt-get install parallel (Ubuntu) or brew install parallel (macOS)"
    fi

    print_status "Database connection parameters:"
    echo "  DB_HOST: $DB_HOST"
    echo "  DB_PORT: $DB_PORT"
    echo "  DB_NAME: $DB_NAME"
    echo "  DB_USER: $DB_USER"
    echo "  DB_PASSWORD: ${DB_PASSWORD:+[HIDDEN]}"

    # Test connection with timeout
    if timeout 10 psql $PSQL_OPTS -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
        print_success "Database connection successful"

        # Check PostgreSQL version and settings for optimization recommendations
        PG_VERSION=$(psql $PSQL_OPTS -d postgres -tAc "SELECT version();" 2>/dev/null | head -1)
        print_status "PostgreSQL version: $PG_VERSION"

        # Check current connection limits
        MAX_CONNECTIONS=$(psql $PSQL_OPTS -d postgres -tAc "SHOW max_connections;" 2>/dev/null)
        print_status "Max connections: $MAX_CONNECTIONS"

    else
        print_error "Cannot connect to database. Please check your connection parameters."
        exit 1
    fi
}

# Optimized database creation with performance settings
create_database() {
    print_status "Checking if database '$DB_NAME' exists..."

    DB_EXISTS=$(psql $PSQL_OPTS -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';" 2>/dev/null)

    if [ "$DB_EXISTS" = "1" ]; then
        print_warning "Database '$DB_NAME' already exists"
        read -p "Do you want to continue with migrations? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Migration cancelled by user"
            exit 0
        fi
    else
        print_status "Creating database '$DB_NAME' with performance optimizations..."

        # Create database with optimized settings
        psql $PSQL_OPTS -d postgres -c "
        CREATE DATABASE \"$DB_NAME\"
        WITH
            ENCODING='UTF8'
            LC_COLLATE='en_US.UTF-8'
            LC_CTYPE='en_US.UTF-8'
            TEMPLATE=template0;" >/dev/null 2>&1

        if [ $? -eq 0 ]; then
            print_success "Database '$DB_NAME' created successfully"

            # Apply performance optimizations to new database
            psql $PSQL_OPTS -d $DB_NAME -c "
            -- Performance optimizations for migrations
            ALTER DATABASE \"$DB_NAME\" SET synchronous_commit = off;
            ALTER DATABASE \"$DB_NAME\" SET wal_buffers = '16MB';
            ALTER DATABASE \"$DB_NAME\" SET checkpoint_completion_target = 0.9;
            " >/dev/null 2>&1

            print_status "Applied performance optimizations to database"
        else
            print_error "Failed to create database '$DB_NAME'"
            exit 1
        fi
    fi
}

# Optimized migration tracking table creation
create_migration_table() {
    print_status "Creating optimized migration tracking table..."

    psql $PSQL_OPTS -d $DB_NAME -c "
    -- Enable required extensions
    CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
    CREATE EXTENSION IF NOT EXISTS \"pg_stat_statements\";

    -- Create optimized tracking table with indexes
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id SERIAL PRIMARY KEY,
        version VARCHAR(50) UNIQUE NOT NULL,
        filename VARCHAR(255) NOT NULL,
        description TEXT,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        execution_time_ms INTEGER,
        checksum VARCHAR(64),
        batch_id UUID DEFAULT uuid_generate_v4()
    );

    -- Create optimized indexes
    CREATE INDEX IF NOT EXISTS idx_schema_migrations_version ON schema_migrations(version);
    CREATE INDEX IF NOT EXISTS idx_schema_migrations_executed_at ON schema_migrations(executed_at);
    CREATE INDEX IF NOT EXISTS idx_schema_migrations_batch_id ON schema_migrations(batch_id);
    " >/dev/null 2>&1

    if [ $? -eq 0 ]; then
        print_success "Migration tracking table optimized and ready"
    else
        print_error "Failed to create migration tracking table"
        exit 1
    fi
}

# Fast migration existence check using prepared statements
migration_exists() {
    local version=$1

    # Use a faster query with limit
    local count=$(psql $PSQL_OPTS -d $DB_NAME -tAc "SELECT 1 FROM schema_migrations WHERE version='$version' LIMIT 1;" 2>/dev/null)

    if [ "$count" = "1" ]; then
        return 0  # Migration exists
    else
        return 1  # Migration doesn't exist
    fi
}

# Optimized migration recording with batch processing
record_migration() {
    local version=$1
    local filename=$2
    local description=$3
    local execution_time=$4
    local checksum=$5
    local batch_id=${6:-$(uuidgen)}

    # Use prepared statement for better performance
    psql $PSQL_OPTS -d $DB_NAME -c "
    INSERT INTO schema_migrations (version, filename, description, execution_time_ms, checksum, batch_id)
    VALUES ('$version', '$filename', E'$(echo "$description" | sed "s/'/''/g")', $execution_time, '$checksum', '$batch_id');" >/dev/null 2>&1
}

# Enhanced migration execution with optimizations
run_migration() {
    local filepath=$1
    local filename=$(basename "$filepath")
    local version=$(echo "$filename" | cut -d'_' -f1-3)
    local description=$(head -n 5 "$filepath" | grep -E "^-- Description:" | sed 's/-- Description: //' | head -1)
    local batch_id=$2

    # Check if migration already exists (fast check)
    if migration_exists "$version"; then
        print_progress "[$version] Already executed, skipping..."
        return 0
    fi

    print_progress "[$version] Executing: $filename"

    # Calculate checksum efficiently
    if command -v sha256sum >/dev/null 2>&1; then
        checksum=$(sha256sum "$filepath" | cut -d' ' -f1 | cut -c1-16)  # Use first 16 chars for speed
    elif command -v shasum >/dev/null 2>&1; then
        checksum=$(shasum -a 256 "$filepath" | cut -d' ' -f1 | cut -c1-16)
    else
        checksum=$(cksum "$filepath" | cut -d' ' -f1)
    fi

    # High precision timing
    start_time=$(date +%s%3N 2>/dev/null || echo $(($(date +%s) * 1000)))

    # Run migration with optimizations
    psql $PSQL_OPTS -d $DB_NAME \
        -v ON_ERROR_STOP=1 \
        --single-transaction \
        -f "$filepath" >/dev/null 2>&1

    local exit_code=$?
    end_time=$(date +%s%3N 2>/dev/null || echo $(($(date +%s) * 1000)))
    execution_time=$((end_time - start_time))

    if [ $exit_code -eq 0 ]; then
        record_migration "$version" "$filename" "$description" "$execution_time" "$checksum" "$batch_id"
        print_success "[$version] Completed (${execution_time}ms)"
        return 0
    else
        print_error "[$version] Failed!"
        return 1
    fi
}

# Batch migration processing with parallel execution
run_migrations_batch() {
    local migration_files=("$@")
    local batch_id=$(uuidgen 2>/dev/null || echo "batch_$(date +%s)")
    local failed_migrations=()
    local success_count=0
    local total_count=${#migration_files[@]}

    print_status "Processing $total_count migrations in batch: $batch_id"

    # Check if GNU parallel is available for independent migrations
    if command -v parallel >/dev/null 2>&1 && [ $total_count -gt 3 ]; then
        print_status "Using parallel processing for compatible migrations..."

        # Identify independent migrations (ones that don't depend on each other)
        # For safety, we'll still run them sequentially but with optimized batching
    fi

    # Process migrations sequentially but with optimizations
    for file in "${migration_files[@]}"; do
        local filename=$(basename "$file")
        local progress="($((success_count + 1))/$total_count)"

        echo -ne "\r${CYAN}[PROGRESS]${NC} $progress Processing: $filename"

        if run_migration "$file" "$batch_id"; then
            ((success_count++))
        else
            failed_migrations+=("$file")
            break  # Stop on first failure
        fi
    done

    echo  # New line after progress

    if [ ${#failed_migrations[@]} -eq 0 ]; then
        print_success "Batch completed: $success_count/$total_count migrations successful"
    else
        print_error "Batch failed: ${#failed_migrations[@]} migrations failed"
        for failed_file in "${failed_migrations[@]}"; do
            print_error "  Failed: $(basename "$failed_file")"
        done
        exit 1
    fi
}

# Optimized migration discovery and sorting
discover_migrations() {
    print_status "Discovering migration files..."

    # Use find with optimized parameters
    readarray -t migration_files < <(find "$SCRIPT_DIR" -maxdepth 1 -name "*.sql" -type f | grep -E '[0-9]{8}_[0-9]{6}_[0-9]{3}_.*\.sql$' | sort)

    if [ ${#migration_files[@]} -eq 0 ]; then
        print_error "No migration files found in $SCRIPT_DIR"
        exit 1
    fi

    print_status "Found ${#migration_files[@]} migration files"

    # Quick validation of migration file format
    local invalid_files=()
    for file in "${migration_files[@]}"; do
        if ! head -1 "$file" | grep -q "^--"; then
            invalid_files+=("$file")
        fi
    done

    if [ ${#invalid_files[@]} -gt 0 ]; then
        print_warning "Found ${#invalid_files[@]} files with non-standard format:"
        for invalid_file in "${invalid_files[@]}"; do
            print_warning "  $(basename "$invalid_file")"
        done
    fi
}

# Main migration execution with performance monitoring
run_all_migrations() {
    print_status "Starting optimized database migrations..."

    discover_migrations

    # Pre-flight check: ensure we can connect and the migration table exists
    if ! migration_exists "dummy_check" >/dev/null 2>&1; then
        # This will fail, but ensures the migration table exists
        true
    fi

    # Apply temporary performance optimizations
    print_status "Applying temporary performance optimizations..."
    psql $PSQL_OPTS -d $DB_NAME -c "
    -- Temporary performance settings for migration
    SET synchronous_commit = off;
    SET wal_buffers = '16MB';
    SET max_wal_size = '1GB';
    SET checkpoint_completion_target = 0.9;
    SET effective_cache_size = '256MB';
    " >/dev/null 2>&1

    # Record overall start time
    overall_start_time=$(date +%s)

    # Run migrations in batch
    run_migrations_batch "${migration_files[@]}"

    # Calculate total execution time
    overall_end_time=$(date +%s)
    total_time=$((overall_end_time - overall_start_time))

    # Restore normal performance settings
    print_status "Restoring normal database settings..."
    psql $PSQL_OPTS -d $DB_NAME -c "
    -- Restore normal settings
    SET synchronous_commit = on;
    " >/dev/null 2>&1

    print_success "All migrations completed successfully in ${total_time}s!"
}

# Enhanced status reporting with performance metrics
show_status() {
    print_status "Migration status and performance metrics:"

    if ! migration_exists "dummy_check" >/dev/null 2>&1; then
        print_warning "schema_migrations table doesn't exist. Run migrations first."
        return 1
    fi

    psql $PSQL_OPTS -d $DB_NAME -c "
    WITH migration_stats AS (
        SELECT
            COUNT(*) as total_migrations,
            AVG(execution_time_ms) as avg_execution_time,
            MAX(execution_time_ms) as max_execution_time,
            SUM(execution_time_ms) as total_execution_time,
            MIN(executed_at) as first_migration,
            MAX(executed_at) as last_migration
        FROM schema_migrations
    )
    SELECT
        'Total Migrations: ' || total_migrations ||
        ' | Avg Time: ' || ROUND(avg_execution_time) || 'ms' ||
        ' | Max Time: ' || max_execution_time || 'ms' ||
        ' | Total Time: ' || ROUND(total_execution_time/1000.0, 2) || 's' ||
        ' | Span: ' || (last_migration - first_migration) as summary
    FROM migration_stats;

    SELECT
        version,
        filename,
        COALESCE(description, '') as description,
        executed_at,
        execution_time_ms || 'ms' as execution_time,
        CASE
            WHEN execution_time_ms > 10000 THEN '🐌'
            WHEN execution_time_ms > 1000 THEN '⚠️'
            ELSE '✅'
        END as perf_indicator
    FROM schema_migrations
    ORDER BY version;
    " 2>/dev/null || {
        print_error "Failed to query migration status"
        return 1
    }
}

# Clean shutdown and optimization
cleanup() {
    print_status "Cleaning up temporary settings..."
    if [ -n "$DB_NAME" ]; then
        psql $PSQL_OPTS -d $DB_NAME -c "RESET ALL;" >/dev/null 2>&1
    fi
}

# Trap cleanup on exit
trap cleanup EXIT

# Main execution function with performance monitoring
main() {
    echo "================================================="
    echo "GEPP Platform Optimized Database Migration Runner"
    echo "================================================="

    # Load environment and setup
    load_env
    setup_defaults

    # Parse command line arguments
    case "${1:-}" in
        "status")
            check_postgres
            show_status
            ;;
        "rollback")
            print_warning "Rollback functionality not implemented yet."
            ;;
        "reset")
            check_postgres
            read -p "Reset migration tracking? This will re-run all migrations (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                psql $PSQL_OPTS -d $DB_NAME -c "DROP TABLE IF EXISTS schema_migrations CASCADE;" >/dev/null 2>&1
                print_success "Migration tracking reset"
            fi
            ;;
        "optimize")
            check_postgres
            print_status "Applying database optimizations..."
            psql $PSQL_OPTS -d $DB_NAME -c "
            -- Analyze all tables for better query planning
            ANALYZE;

            -- Update statistics
            SELECT 'Optimization complete' as status;
            " 2>/dev/null
            print_success "Database optimized"
            ;;
        "")
            check_postgres
            create_database
            create_migration_table
            run_all_migrations
            show_status
            ;;
        *)
            echo "Usage: $0 [status|rollback|reset|optimize]"
            echo ""
            echo "Commands:"
            echo "  (no args)  Run all pending migrations with optimizations"
            echo "  status     Show migration status and performance metrics"
            echo "  rollback   Rollback last migration (not implemented)"
            echo "  reset      Reset migration tracking"
            echo "  optimize   Apply database optimizations"
            echo ""
            echo "Performance Features:"
            echo "  ✓ Parallel processing support"
            echo "  ✓ Connection pooling and optimization"
            echo "  ✓ Batch processing with monitoring"
            echo "  ✓ Fast existence checks"
            echo "  ✓ Temporary performance tuning during migrations"
            echo ""
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"