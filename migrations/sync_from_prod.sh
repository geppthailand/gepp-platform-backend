#!/bin/bash

# ──────────────────────────────────────────────────────────────
# GEPP Platform — Sync Production Data → Local Database
#
# Pulls table data from production (.env) into local DB (.env.local).
# Schema is NOT synced — only data. Run migrations locally first.
#
# Usage:
#   ./sync_from_prod.sh                     # Sync all tables
#   ./sync_from_prod.sh --tables t1,t2,t3   # Sync specific tables
#   ./sync_from_prod.sh --schema-only       # Sync schema only (no data)
#   ./sync_from_prod.sh --list              # List all prod tables
#   ./sync_from_prod.sh --diff              # Compare local vs prod schemas
# ──────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLUE}[SYNC]${NC} $1"; }
ok()   { echo -e "${GREEN}[SYNC]${NC} $1"; }
warn() { echo -e "${YELLOW}[SYNC]${NC} $1"; }
err()  { echo -e "${RED}[SYNC]${NC} $1"; }

# ── Load env files ────────────────────────────────────────────
load_env_file() {
    local file=$1 prefix=$2
    if [ ! -f "$file" ]; then
        err "Missing: $file"
        exit 1
    fi
    while IFS='=' read -r key value || [ -n "$key" ]; do
        if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]] && [[ ! "$key" =~ ^[[:space:]]*$ ]]; then
            value="${value%$'\r'}"
            value="${value%\"}"; value="${value#\"}"
            value="${value%\'}"; value="${value#\'}"
            eval "export ${prefix}_${key}=\"$value\""
        fi
    done < "$file"
}

# Load production connection from .env
load_env_file "$SCRIPT_DIR/.env" "PROD"
# Load local connection from .env.local
load_env_file "$SCRIPT_DIR/.env.local" "LOCAL"

PROD_HOST="${PROD_DB_HOST:-localhost}"
PROD_PORT="${PROD_DB_PORT:-5432}"
PROD_NAME="${PROD_DB_NAME:-postgres}"
PROD_USER="${PROD_DB_USER:-postgres}"
PROD_PASS="${PROD_DB_PASSWORD:-}"

LOCAL_HOST="${LOCAL_DB_HOST:-localhost}"
LOCAL_PORT="${LOCAL_DB_PORT:-5432}"
LOCAL_NAME="${LOCAL_DB_NAME:-gepp_platform}"
LOCAL_USER="${LOCAL_DB_USER:-postgres}"
LOCAL_PASS="${LOCAL_DB_PASSWORD:-}"

PROD_PSQL="PGPASSWORD=$PROD_PASS psql -h $PROD_HOST -p $PROD_PORT -U $PROD_USER -d $PROD_NAME --no-psqlrc -q"
LOCAL_PSQL="PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -q"

# Tables that should NEVER be synced (security / local-only)
SKIP_TABLES="schema_migrations"

# ── Functions ─────────────────────────────────────────────────

check_connections() {
    log "Checking production connection ($PROD_USER@$PROD_HOST:$PROD_PORT/$PROD_NAME)..."
    if ! PGPASSWORD=$PROD_PASS psql -h $PROD_HOST -p $PROD_PORT -U $PROD_USER -d $PROD_NAME --no-psqlrc -q -c "SELECT 1;" >/dev/null 2>&1; then
        err "Cannot connect to PRODUCTION database!"
        exit 1
    fi
    ok "Production: connected"

    log "Checking local connection ($LOCAL_USER@$LOCAL_HOST:$LOCAL_PORT/$LOCAL_NAME)..."
    if ! PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -q -c "SELECT 1;" >/dev/null 2>&1; then
        err "Cannot connect to LOCAL database!"
        err "Run ./run_local.sh first to create it."
        exit 1
    fi
    ok "Local: connected"
}

list_prod_tables() {
    PGPASSWORD=$PROD_PASS psql -h $PROD_HOST -p $PROD_PORT -U $PROD_USER -d $PROD_NAME --no-psqlrc -tAc "
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    " 2>/dev/null
}

list_local_tables() {
    PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -tAc "
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    " 2>/dev/null
}

is_skipped() {
    local table=$1
    for skip in $SKIP_TABLES; do
        if [ "$table" = "$skip" ]; then return 0; fi
    done
    return 1
}

sync_table() {
    local table=$1
    local tmp_file=$(mktemp /tmp/gepp_sync_XXXXXX.sql)

    # Dump data from production
    PGPASSWORD=$PROD_PASS pg_dump \
        -h $PROD_HOST -p $PROD_PORT -U $PROD_USER \
        -d $PROD_NAME \
        --data-only \
        --table="public.$table" \
        --no-owner \
        --no-privileges \
        --disable-triggers \
        -f "$tmp_file" 2>/dev/null

    if [ ! -s "$tmp_file" ]; then
        warn "  $table: empty or not found in prod, skipping"
        rm -f "$tmp_file"
        return 0
    fi

    # Count rows in dump
    local row_count=$(grep -c "^COPY\|^INSERT" "$tmp_file" 2>/dev/null || echo "?")

    # Clear local table and restore
    PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -q -c "
        SET session_replication_role = 'replica';
        TRUNCATE TABLE public.\"$table\" CASCADE;
    " 2>/dev/null

    PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -q -c "
        SET session_replication_role = 'replica';
    " -f "$tmp_file" 2>/dev/null

    local exit_code=$?
    rm -f "$tmp_file"

    # Reset sequences for this table
    PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -q -c "
        DO \$\$
        DECLARE seq_name TEXT; col_name TEXT; max_val BIGINT;
        BEGIN
            FOR seq_name, col_name IN
                SELECT pg_get_serial_sequence('public.\"$table\"', a.attname), a.attname
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = '$table' AND a.attnum > 0
                AND pg_get_serial_sequence('public.\"$table\"', a.attname) IS NOT NULL
            LOOP
                EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM public.\"$table\"', col_name) INTO max_val;
                EXECUTE format('SELECT setval(%L, %s)', seq_name, max_val + 1);
            END LOOP;
        END \$\$;
    " 2>/dev/null

    if [ $exit_code -eq 0 ]; then
        ok "  $table: synced"
    else
        err "  $table: FAILED"
    fi

    return $exit_code
}

sync_tables() {
    local specific_tables=("$@")

    if [ ${#specific_tables[@]} -gt 0 ]; then
        # Sync specific tables
        local tables=("${specific_tables[@]}")
    else
        # Sync all tables that exist in BOTH prod and local
        local prod_tables=($(list_prod_tables))
        local local_tables=($(list_local_tables))

        # Find intersection
        local tables=()
        for pt in "${prod_tables[@]}"; do
            for lt in "${local_tables[@]}"; do
                if [ "$pt" = "$lt" ]; then
                    tables+=("$pt")
                    break
                fi
            done
        done
    fi

    local total=${#tables[@]}
    local synced=0 failed=0 skipped=0

    log "Syncing $total tables from production → local..."
    echo ""

    for table in "${tables[@]}"; do
        if is_skipped "$table"; then
            warn "  $table: skipped (protected)"
            ((skipped++))
            continue
        fi

        if sync_table "$table"; then
            ((synced++))
        else
            ((failed++))
        fi
    done

    echo ""
    ok "Done: $synced synced, $skipped skipped, $failed failed (of $total)"
}

show_diff() {
    log "Comparing schemas: production vs local"
    echo ""

    local prod_tables=($(list_prod_tables))
    local local_tables=($(list_local_tables))

    # Tables only in prod
    log "Tables only in PRODUCTION (missing locally — need migration?):"
    local prod_only=0
    for pt in "${prod_tables[@]}"; do
        local found=false
        for lt in "${local_tables[@]}"; do
            if [ "$pt" = "$lt" ]; then found=true; break; fi
        done
        if [ "$found" = false ]; then
            echo -e "  ${RED}+ $pt${NC}"
            ((prod_only++))
        fi
    done
    [ $prod_only -eq 0 ] && echo "  (none)"

    echo ""

    # Tables only in local
    log "Tables only in LOCAL (not in production — new migration?):"
    local local_only=0
    for lt in "${local_tables[@]}"; do
        local found=false
        for pt in "${prod_tables[@]}"; do
            if [ "$pt" = "$lt" ]; then found=true; break; fi
        done
        if [ "$found" = false ]; then
            echo -e "  ${GREEN}+ $lt${NC}"
            ((local_only++))
        fi
    done
    [ $local_only -eq 0 ] && echo "  (none)"

    echo ""

    # Row count comparison for common tables
    log "Row counts (prod vs local) for common tables:"
    for pt in "${prod_tables[@]}"; do
        for lt in "${local_tables[@]}"; do
            if [ "$pt" = "$lt" ]; then
                local prod_count=$(PGPASSWORD=$PROD_PASS psql -h $PROD_HOST -p $PROD_PORT -U $PROD_USER -d $PROD_NAME --no-psqlrc -tAc "SELECT COUNT(*) FROM public.\"$pt\";" 2>/dev/null || echo "?")
                local local_count=$(PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -tAc "SELECT COUNT(*) FROM public.\"$pt\";" 2>/dev/null || echo "?")
                if [ "$prod_count" != "$local_count" ]; then
                    echo -e "  ${YELLOW}$pt${NC}: prod=$prod_count local=$local_count"
                fi
                break
            fi
        done
    done
}

# ── Main ──────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}=================================================${NC}"
echo -e "${CYAN}  GEPP Platform — Sync Production → Local${NC}"
echo -e "${CYAN}=================================================${NC}"
echo ""

SPECIFIC_TABLES=()
MODE="sync"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tables)
            IFS=',' read -ra SPECIFIC_TABLES <<< "$2"
            shift 2
            ;;
        --list)
            MODE="list"
            shift
            ;;
        --diff)
            MODE="diff"
            shift
            ;;
        --schema-only)
            MODE="schema"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  (no args)              Sync ALL common tables from prod → local"
            echo "  --tables t1,t2,t3      Sync specific tables only"
            echo "  --list                 List all production tables"
            echo "  --diff                 Compare prod vs local schemas + row counts"
            echo "  --schema-only          Sync schema (DDL) only, no data"
            echo ""
            echo "Config files:"
            echo "  .env        Production DB credentials"
            echo "  .env.local  Local DB credentials"
            echo ""
            echo "Protected tables (never synced):"
            echo "  $SKIP_TABLES"
            echo ""
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            exit 1
            ;;
    esac
done

check_connections

case "$MODE" in
    "list")
        log "Production tables:"
        list_prod_tables | while read -r t; do echo "  $t"; done
        echo ""
        log "Local tables:"
        list_local_tables | while read -r t; do echo "  $t"; done
        ;;
    "diff")
        show_diff
        ;;
    "schema")
        log "Dumping production schema → local..."
        tmp_schema=$(mktemp /tmp/gepp_schema_XXXXXX.sql)
        PGPASSWORD=$PROD_PASS pg_dump \
            -h $PROD_HOST -p $PROD_PORT -U $PROD_USER \
            -d $PROD_NAME \
            --schema-only \
            --no-owner \
            --no-privileges \
            -f "$tmp_schema" 2>/dev/null

        warn "This will REPLACE all local schema! Data will be lost."
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            PGPASSWORD=$LOCAL_PASS psql -h $LOCAL_HOST -p $LOCAL_PORT -U $LOCAL_USER -d $LOCAL_NAME --no-psqlrc -q -f "$tmp_schema" 2>/dev/null
            ok "Schema synced."
        fi
        rm -f "$tmp_schema"
        ;;
    "sync")
        warn "This will TRUNCATE local tables and replace with production data!"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [ ${#SPECIFIC_TABLES[@]} -gt 0 ]; then
                sync_tables "${SPECIFIC_TABLES[@]}"
            else
                sync_tables
            fi
        fi
        ;;
esac

echo ""
