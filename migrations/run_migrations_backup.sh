#!/bin/bash

# GEPP Platform Database Migration Runner
# This script runs all migration files in order to set up the complete database structure

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env file if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "Loading environment variables from .env file..."
    # Read .env file line by line
    while IFS='=' read -r key value || [ -n "$key" ]; do
        # Skip comments and empty lines
        if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]]; then
            # Remove any trailing carriage return
            value="${value%$'\r'}"
            # Remove surrounding quotes if present
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"
            # Export the variable
            export "$key=$value"
            echo "  Loaded: $key=${value:+[HIDDEN]}"
        fi
    done < "$SCRIPT_DIR/.env"
else
    echo "No .env file found in $SCRIPT_DIR, using defaults or environment variables"
fi

# Default database connection parameters (can be overridden by .env)
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-gepp_platform}
DB_USER=${DB_USER:-postgres}
DB_PASSWORD=${DB_PASSWORD:-}

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if PostgreSQL is available
check_postgres() {
    print_status "Checking PostgreSQL connection..."
    
    if command -v psql >/dev/null 2>&1; then
        print_success "PostgreSQL client found"
    else
        print_error "PostgreSQL client (psql) not found. Please install PostgreSQL."
        exit 1
    fi
    
    # Check for better tooling on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if ! command -v gdate >/dev/null 2>&1; then
            print_warning "For better timing precision, install GNU coreutils: brew install coreutils"
        fi
        if ! command -v md5sum >/dev/null 2>&1 && ! command -v md5 >/dev/null 2>&1; then
            print_warning "No MD5 utility found. Consider installing coreutils: brew install coreutils"
        fi
    fi


    print_status "Database connection parameters:"
    echo "  DB_HOST: $DB_HOST"
    echo "  DB_PORT: $DB_PORT"
    echo "  DB_NAME: $DB_NAME"
    echo "  DB_USER: $DB_USER"
    echo "  DB_PASSWORD: ${DB_PASSWORD:+[HIDDEN]}"
    
    # Test connection
    if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
        print_success "Database connection successful"
    else
        print_error "Cannot connect to database. Please check your connection parameters."
        exit 1
    fi
}

# Function to create database if it doesn't exist
create_database() {
    print_status "Checking if database '$DB_NAME' exists..."
    
    DB_EXISTS=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';")
    
    if [ "$DB_EXISTS" = "1" ]; then
        print_warning "Database '$DB_NAME' already exists"
        read -p "Do you want to continue with migrations? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Migration cancelled by user"
            exit 0
        fi
    else
        print_status "Creating database '$DB_NAME'..."
        PGPASSWORD=$DB_PASSWORD createdb -h $DB_HOST -p $DB_PORT -U $DB_USER $DB_NAME
        if [ $? -eq 0 ]; then
            print_success "Database '$DB_NAME' created successfully"
        else
            print_error "Failed to create database '$DB_NAME'"
            exit 1
        fi
    fi
}

# Function to create migration tracking table
create_migration_table() {
    print_status "Creating migration tracking table..."
    
    # Create tracking table (try UUID extension but continue if it fails)
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
    -- Try to enable UUID extension (ignore if it fails)
    DO \$\$ BEGIN
        CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
    EXCEPTION
        WHEN OTHERS THEN 
            RAISE NOTICE 'uuid-ossp extension not available, UUIDs will be generated differently';
    END \$\$;
    
    -- Create tracking table
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id SERIAL PRIMARY KEY,
        version VARCHAR(50) UNIQUE NOT NULL,
        filename VARCHAR(255) NOT NULL,
        description TEXT,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        execution_time_ms INTEGER,
        checksum VARCHAR(64)
    );"
    
    if [ $? -eq 0 ]; then
        print_success "Migration tracking table ready"
    else
        print_error "Failed to create migration tracking table"
        exit 1
    fi
}

# Function to check if migration has already been run
migration_exists() {
    local version=$1
    
    # First check if schema_migrations table exists
    local table_exists=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='schema_migrations';" 2>/dev/null)
    
    if [ "$table_exists" -eq 0 ]; then
        print_status "schema_migrations table doesn't exist yet"
        return 1  # Table doesn't exist, migration hasn't run
    fi
    
    local count=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM schema_migrations WHERE version='$version';" 2>/dev/null)
    
    # Return 0 if migration exists (count > 0), 1 if it doesn't exist
    if [ "$count" -gt 0 ]; then
        return 0  # Migration exists
    else
        return 1  # Migration doesn't exist
    fi
}

# Function to record migration
record_migration() {
    local version=$1
    local filename=$2
    local description=$3
    local execution_time=$4
    local checksum=$5
    
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
    INSERT INTO schema_migrations (version, filename, description, execution_time_ms, checksum) 
    VALUES ('$version', '$filename', '$description', $execution_time, '$checksum');"
}

# Function to run a single migration file
run_migration() {
    local filepath=$1
    local filename=$(basename "$filepath")
    # Extract version as date_time_number (first 3 parts)
    local version=$(echo "$filename" | cut -d'_' -f1-3)
    local description=$(head -n 3 "$filepath" | tail -n 1 | sed 's/-- Description: //')
    
    print_status "Checking migration: $filename"
    
    # Check if migration already exists
    if migration_exists "$version"; then
        print_warning "Migration $version already executed, skipping..."
        return 0
    fi
    
    print_status "Running migration: $filename"
    echo "Description: $description"
    
    # Calculate checksum (compatible with both macOS and Linux)
    if command -v md5sum >/dev/null 2>&1; then
        checksum=$(md5sum "$filepath" | cut -d' ' -f1)
    elif command -v md5 >/dev/null 2>&1; then
        checksum=$(md5 -q "$filepath")
    else
        # Fallback to a simple checksum
        checksum=$(cksum "$filepath" | cut -d' ' -f1)
    fi
    
    # Record start time (compatible with both macOS and Linux)
    if command -v gdate >/dev/null 2>&1; then
        # Use GNU date if available (brew install coreutils)
        start_time=$(gdate +%s%3N)
        use_gdate=true
    else
        # Fallback to seconds only for macOS BSD date
        start_time=$(date +%s)
        use_gdate=false
    fi
    
    # Run the migration
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$filepath"
    
    if [ $? -eq 0 ]; then
        # Calculate execution time
        if [ "$use_gdate" = true ]; then
            end_time=$(gdate +%s%3N)
            execution_time=$((end_time - start_time))
        else
            end_time=$(date +%s)
            execution_time=$(((end_time - start_time) * 1000)) # Convert to milliseconds
        fi
        
        # Record successful migration
        record_migration "$version" "$filename" "$description" "$execution_time" "$checksum"
        print_success "Migration $version completed successfully (${execution_time}ms)"
    else
        print_error "Migration $version failed!"
        exit 1
    fi
}

run_all_migrations() {
    print_status "Starting database migrations..."
    
    # Find and sort migration files
    migration_files=($(find "$SCRIPT_DIR" -name "*.sql" | grep -E '^.*[0-9]{8}_[0-9]{6}_[0-9]{3}_.*\.sql$' | sort))
    
    if [ ${#migration_files[@]} -eq 0 ]; then
        print_error "No migration files found in $SCRIPT_DIR"
        exit 1
    fi
    
    print_status "Found ${#migration_files[@]} migration files"
    
    # Run each migration
    for file in "${migration_files[@]}"; do
        run_migration "$file"
    done
    
    print_success "All migrations completed successfully!"
}

# Function to show migration status
show_status() {
    print_status "Migration status:"
    
    # Check if schema_migrations table exists
    local table_exists=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='schema_migrations';" 2>/dev/null)
    
    if [ "$table_exists" -eq 0 ]; then
        print_warning "schema_migrations table doesn't exist. Run migrations first."
        return 1
    fi
    
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
    SELECT 
        version,
        filename,
        description,
        executed_at,
        execution_time_ms || 'ms' as execution_time
    FROM schema_migrations 
    ORDER BY version;"
}

# Function to rollback last migration (if supported)
rollback_last() {
    print_warning "Rollback functionality not implemented yet."
    print_warning "Manual rollback required if needed."
}

# Function to reset migration tracking (for troubleshooting)
reset_migrations() {
    print_warning "This will clear the migration tracking table and force re-run of all migrations."
    read -p "Are you sure? This won't drop your data but will re-run all migrations (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Clearing migration tracking table..."
        PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "DROP TABLE IF EXISTS schema_migrations CASCADE;"
        if [ $? -eq 0 ]; then
            print_success "Migration tracking table cleared. Run migrations again."
        else
            print_error "Failed to clear migration tracking table"
            exit 1
        fi
    else
        print_status "Reset cancelled"
    fi
}

# Main execution
main() {
    echo "========================================="
    echo "GEPP Platform Database Migration Runner"
    echo "========================================="

    # Parse command line arguments
    case "${1:-}" in
        "status")
            check_postgres
            show_status
            ;;
        "rollback")
            rollback_last
            ;;
        "reset")
            check_postgres
            reset_migrations
            ;;
        "")
            check_postgres
            create_database
            create_migration_table
            run_all_migrations
            show_status
            ;;
        *)
            echo "Usage: $0 [status|rollback|reset]"
            echo ""
            echo "Commands:"
            echo "  (no args)  Run all pending migrations"
            echo "  status     Show migration status"
            echo "  rollback   Rollback last migration (not implemented)"
            echo "  reset      Reset migration tracking (for troubleshooting)"
            echo ""
            echo "Environment Variables (can be set in .env file):"
            echo "  DB_HOST     Database host (default: localhost)"
            echo "  DB_PORT     Database port (default: 5432)"
            echo "  DB_NAME     Database name (default: gepp_platform)"
            echo "  DB_USER     Database user (default: postgres)"
            echo "  DB_PASSWORD Database password (default: empty)"
            echo ""
            echo "Note: Create a .env file in the migrations directory to set these variables"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"