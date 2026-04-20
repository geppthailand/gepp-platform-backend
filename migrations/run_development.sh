#!/bin/bash

# ──────────────────────────────────────────────────────────────
# GEPP Platform — Development Server Migration Runner
#
# Same as run_migrations.sh but connects to the DEV server
# using .env.development instead of .env (production).
#
# Flow:
#   1. Dev on local    → run_local.sh          (.env.local)
#   2. Test migrations → run_development.sh    (.env.development)
#   3. Deploy to prod  → run_migrations.sh     (.env = production)
#
# Both scripts use the same SQL files and schema_migrations
# tracking table. Each DB tracks independently which migrations
# have been applied — no conflicts.
#
# Usage:
#   ./run_development.sh                    # Run pending migrations
#   ./run_development.sh status             # Show migration status
#   ./run_development.sh reset              # Reset tracking table
#   ./run_development.sh rerun <version>    # Re-run a specific migration
#   DEBUG_MODE=true ./run_development.sh    # Verbose output
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Override: force .env.development ─────────────────────────
ENV_FILE="$SCRIPT_DIR/.env.development"

if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "  .env.development not found. Creating from template..."
  echo ""
  cat > "$ENV_FILE" << 'EOF'
# Development Server Database Configuration for Migrations
# Edit these values to match your dev server PostgreSQL setup

DB_HOST=18.141.42.198
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=
EOF
  echo "  Created: $ENV_FILE"
  echo "  Please edit with your dev DB credentials, then re-run."
  echo ""
  exit 1
fi

# ── Source and patch the original migration runner ────────────

# Performance optimization flags
export PGCONNECT_TIMEOUT=10
export PGCOMMAND_TIMEOUT=300

# Debug mode flag
DEBUG_MODE=${DEBUG_MODE:-false}

DB_PERFORMANCE_OPTS="-c statement_timeout=300s -c lock_timeout=60s -c idle_in_transaction_session_timeout=120s"

# Load environment variables from .env.development
load_env() {
    echo "Loading environment variables from .env.development..."
    while IFS='=' read -r key value || [ -n "$key" ]; do
        if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]] && [[ ! "$key" =~ ^[[:space:]]*$ ]]; then
            value="${value%$'\r'}"
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"
            export "$key=$value"
            echo "  Loaded: $key=${value:+[SET]}"
        fi
    done < "$ENV_FILE"
    echo "  Environment loaded (DEVELOPMENT)"
}

# Default database connection parameters
setup_defaults() {
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_NAME=${DB_NAME:-v1}
    DB_USER=${DB_USER:-postgres}
    DB_PASSWORD=${DB_PASSWORD:-}

    export PGPASSWORD=$DB_PASSWORD
    DB_CONN_STRING="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT"
    PSQL_OPTS="-h $DB_HOST -p $DB_PORT -U $DB_USER --no-psqlrc -q"
    PSQL_MIGRATION_OPTS="-h $DB_HOST -p $DB_PORT -U $DB_USER --no-psqlrc"
}

# ── Color codes and helpers ──────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

print_status() { echo -e "${MAGENTA}[DEV]${NC} $1"; }
print_success() { echo -e "${GREEN}[DEV]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[DEV]${NC} $1"; }
print_error() { echo -e "${RED}[DEV]${NC} $1"; }
print_progress() { echo -e "${CYAN}[DEV]${NC} $1"; }
print_debug() {
    if [ "$DEBUG_MODE" = "true" ]; then
        echo -e "${CYAN}[DEBUG]${NC} $1";
    fi
}

show_sql_error() {
    local error_file=$1
    local context=$2
    if [ -s "$error_file" ]; then
        echo ""
        print_error "=== $context ERROR DETAILS ==="
        echo ""
        while IFS= read -r line; do
            if echo "$line" | grep -q "ERROR:"; then
                echo -e "${RED}  $line${NC}"
            elif echo "$line" | grep -q "DETAIL:"; then
                echo -e "${YELLOW}  $line${NC}"
            elif echo "$line" | grep -q "HINT:"; then
                echo -e "${CYAN}  $line${NC}"
            elif echo "$line" | grep -q "LINE"; then
                echo -e "${BLUE}  $line${NC}"
            else
                echo "  $line"
            fi
        done < "$error_file"
        echo ""
        print_error "=== END $context ERROR ==="
        echo ""
    else
        print_error "No detailed error message available for $context"
    fi
}

check_postgres() {
    print_status "Checking DEVELOPMENT server PostgreSQL connection..."

    if ! command -v psql >/dev/null 2>&1; then
        print_error "PostgreSQL client (psql) not found."
        print_error "  macOS: brew install postgresql@16"
        exit 1
    fi

    print_status "Connection: $DB_USER@$DB_HOST:$DB_PORT/$DB_NAME"

    local connection_error_file=$(mktemp)
    psql $PSQL_OPTS -d postgres -c "SELECT 1;" >/dev/null 2>"$connection_error_file"
    local connection_exit_code=$?

    if [ $connection_exit_code -eq 0 ]; then
        rm -f "$connection_error_file"
        print_success "Development server connection OK"
    else
        print_error "Cannot connect to development database!"
        show_sql_error "$connection_error_file" "DATABASE CONNECTION"
        rm -f "$connection_error_file"
        echo ""
        print_status "Check that the dev server at $DB_HOST:$DB_PORT is reachable."
        print_status "You may need VPN or network access to the dev environment."
        echo ""
        exit 1
    fi
}

create_database() {
    print_status "Checking if database '$DB_NAME' exists..."

    DB_EXISTS=$(psql $PSQL_OPTS -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME';" 2>/dev/null)

    if [ "$DB_EXISTS" = "1" ]; then
        print_success "Database '$DB_NAME' exists"
    else
        print_status "Creating database '$DB_NAME'..."

        local db_creation_error_file=$(mktemp)
        psql $PSQL_OPTS -d postgres -c "CREATE DATABASE \"$DB_NAME\" WITH ENCODING='UTF8' TEMPLATE=template0;" >/dev/null 2>"$db_creation_error_file"

        if [ $? -eq 0 ]; then
            rm -f "$db_creation_error_file"
            print_success "Database '$DB_NAME' created"
        else
            print_error "Failed to create database '$DB_NAME'"
            show_sql_error "$db_creation_error_file" "DATABASE CREATION"
            rm -f "$db_creation_error_file"
            exit 1
        fi
    fi
}

create_migration_table() {
    print_status "Ensuring migration tracking table exists..."

    local migration_table_error_file=$(mktemp)
    psql $PSQL_OPTS -d $DB_NAME -c "
    CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";
    " >/dev/null 2>>"$migration_table_error_file"

    psql $PSQL_OPTS -d $DB_NAME -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
        id SERIAL PRIMARY KEY,
        version VARCHAR(50) UNIQUE NOT NULL,
        filename VARCHAR(255) NOT NULL,
        description TEXT,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        execution_time_ms INTEGER,
        checksum VARCHAR(64)
    );
    " >/dev/null 2>>"$migration_table_error_file"

    psql $PSQL_OPTS -d $DB_NAME -c "
    DO \$\$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'schema_migrations' AND column_name = 'batch_id'
        ) THEN
            ALTER TABLE schema_migrations ADD COLUMN batch_id UUID DEFAULT uuid_generate_v4();
        END IF;
    END \$\$;
    " >/dev/null 2>>"$migration_table_error_file"

    psql $PSQL_OPTS -d $DB_NAME -c "
    CREATE INDEX IF NOT EXISTS idx_schema_migrations_version ON schema_migrations(version);
    CREATE INDEX IF NOT EXISTS idx_schema_migrations_executed_at ON schema_migrations(executed_at);
    " >/dev/null 2>>"$migration_table_error_file"

    if [ $? -eq 0 ]; then
        rm -f "$migration_table_error_file"
        print_success "Migration tracking table ready"
    else
        print_error "Failed to create migration tracking table"
        show_sql_error "$migration_table_error_file" "MIGRATION TABLE CREATION"
        rm -f "$migration_table_error_file"
        exit 1
    fi
}

migration_exists() {
    local version=$1
    local count=$(psql $PSQL_OPTS -d $DB_NAME -tAc "SELECT 1 FROM schema_migrations WHERE version='$version' LIMIT 1;" 2>/dev/null)
    if [ "$count" = "1" ]; then return 0; else return 1; fi
}

record_migration() {
    local version=$1 filename=$2 description=$3 execution_time=$4 checksum=$5
    local batch_id=${6:-$(uuidgen 2>/dev/null || echo "dev_$(date +%s)")}

    local record_error_file=$(mktemp)
    psql $PSQL_OPTS -d $DB_NAME -c "
    INSERT INTO schema_migrations (version, filename, description, execution_time_ms, checksum, batch_id)
    VALUES ('$version', '$filename', E'$(echo "$description" | sed "s/'/''/g")', $execution_time, '$checksum', '$batch_id');" >/dev/null 2>"$record_error_file"

    if [ $? -ne 0 ]; then
        print_warning "Failed to record migration $version"
        [ -s "$record_error_file" ] && print_warning "$(cat "$record_error_file")"
    fi
    rm -f "$record_error_file"
}

run_migration() {
    local filepath=$1
    local filename=$(basename "$filepath")
    local version=$(echo "$filename" | cut -d'_' -f1-3)
    local description=$(head -n 5 "$filepath" | grep -E "^-- Description:" | sed 's/-- Description: //' | head -1)
    local batch_id=$2

    if migration_exists "$version"; then
        print_progress "[$version] Already applied, skipping"
        return 0
    fi

    print_progress "[$version] Running: $filename"

    if command -v shasum >/dev/null 2>&1; then
        checksum=$(shasum -a 256 "$filepath" | cut -d' ' -f1 | cut -c1-16)
    elif command -v sha256sum >/dev/null 2>&1; then
        checksum=$(sha256sum "$filepath" | cut -d' ' -f1 | cut -c1-16)
    else
        checksum=$(cksum "$filepath" | cut -d' ' -f1)
    fi

    start_time=$(($(date +%s) * 1000))

    local temp_error_file=$(mktemp)
    psql $PSQL_MIGRATION_OPTS -d $DB_NAME \
        -v ON_ERROR_STOP=1 \
        --single-transaction \
        -f "$filepath" 2>"$temp_error_file"

    local exit_code=$?
    end_time=$(($(date +%s) * 1000))
    execution_time=$((end_time - start_time))

    if [ $exit_code -eq 0 ]; then
        rm -f "$temp_error_file"
        record_migration "$version" "$filename" "$description" "$execution_time" "$checksum" "$batch_id"
        print_success "[$version] Done (${execution_time}ms)"
        return 0
    else
        print_error "[$version] FAILED!"
        print_error "File: $filepath"
        show_sql_error "$temp_error_file" "MIGRATION $version"
        rm -f "$temp_error_file"
        return 1
    fi
}

discover_migrations() {
    print_status "Discovering migration files..."
    migration_files=($(find "$SCRIPT_DIR" -maxdepth 1 -name "*.sql" -type f | grep -E '[0-9]{8}_[0-9]{6}_[0-9]{3}_.*\.sql$' | sort))

    if [ ${#migration_files[@]} -eq 0 ]; then
        print_error "No migration files found in $SCRIPT_DIR"
        exit 1
    fi

    print_status "Found ${#migration_files[@]} migration files"
}

run_all_migrations() {
    print_status "Running development migrations..."
    discover_migrations

    local batch_id=$(uuidgen 2>/dev/null || echo "dev_$(date +%s)")
    local success_count=0 total_count=${#migration_files[@]}
    local overall_start=$(date +%s)

    for file in "${migration_files[@]}"; do
        if run_migration "$file" "$batch_id"; then
            ((success_count++))
        else
            print_error "Stopping at first failure."
            exit 1
        fi
    done

    local total_time=$(( $(date +%s) - overall_start ))
    print_success "All migrations complete ($success_count/$total_count) in ${total_time}s"
}

show_status() {
    print_status "Migration status:"

    local table_exists=$(psql $PSQL_OPTS -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='schema_migrations';" 2>/dev/null)

    if [ "$table_exists" -eq 0 ] 2>/dev/null; then
        print_warning "No schema_migrations table. Run migrations first."
        return 1
    fi

    psql $PSQL_OPTS -d $DB_NAME -c "
    SELECT version, filename, executed_at, execution_time_ms || 'ms' as time
    FROM schema_migrations ORDER BY version;
    " 2>/dev/null

    local count=$(psql $PSQL_OPTS -d $DB_NAME -tAc "SELECT COUNT(*) FROM schema_migrations;" 2>/dev/null)
    print_status "Total applied: $count migrations"
}

# ── Cleanup ───────────────────────────────────────────────────
cleanup() {
    if [ -n "$DB_NAME" ]; then
        psql $PSQL_OPTS -d $DB_NAME -c "RESET ALL;" >/dev/null 2>&1
    fi
}
trap cleanup EXIT

# ── Main ──────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${MAGENTA}=================================================${NC}"
    echo -e "${MAGENTA}  GEPP Platform — DEVELOPMENT Migration Runner${NC}"
    echo -e "${MAGENTA}  .env.development → Dev Server PostgreSQL${NC}"
    echo -e "${MAGENTA}=================================================${NC}"
    echo ""

    load_env
    setup_defaults

    case "${1:-}" in
        "status")
            check_postgres
            show_status
            ;;
        "reset")
            check_postgres
            print_warning "You are about to reset migration tracking on the DEVELOPMENT server!"
            read -p "Reset dev migration tracking? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                psql $PSQL_OPTS -d $DB_NAME -c "DROP TABLE IF EXISTS schema_migrations CASCADE;" >/dev/null 2>&1
                print_success "Migration tracking reset"
            fi
            ;;
        "rerun")
            if [ -z "${2:-}" ]; then
                print_error "Usage: $0 rerun <version>"
                exit 1
            fi
            check_postgres
            create_database
            create_migration_table
            local version="$2"
            psql $PSQL_OPTS -d $DB_NAME -c "DELETE FROM schema_migrations WHERE version = '$version';" 2>/dev/null || true
            print_success "Cleared version $version — re-running migrations..."
            run_all_migrations
            ;;
        "")
            check_postgres
            create_database
            create_migration_table
            run_all_migrations
            show_status
            ;;
        *)
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  (no args)    Run all pending migrations on dev server"
            echo "  status       Show applied migrations"
            echo "  reset        Reset migration tracking (re-run all next time)"
            echo "  rerun VER    Re-run a specific migration version"
            echo ""
            echo "Environment:"
            echo "  DEBUG_MODE=true  Enable verbose output"
            echo ""
            exit 1
            ;;
    esac
}

main "$@"
