#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Run migrations against the DEV database.
#
# There was no supported way to do this: run_local.sh is pinned to localhost and
# run_migrations.sh reads .env, which is PRODUCTION. Anyone wanting to test a
# migration on dev had to hand-edit env vars — and since the dev and production
# databases are BOTH named "postgres", the runner's own banner cannot tell you
# which one you reached. Only the host can, so this script puts the host in front
# of you and makes you confirm it.
#
# Usage:
#   ./run_dev.sh status      # what is applied on dev (read-only, always safe)
#   ./run_dev.sh             # apply pending migrations to dev
#   ./run_dev.sh rerun 081   # re-run one version on dev
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.development"

if [ ! -f "$ENV_FILE" ]; then
  echo "  .env.development not found in $SCRIPT_DIR" >&2
  echo "  It holds the DEV database connection; copy .env.example and fill it in." >&2
  exit 1
fi

DEV_HOST="$(grep -E '^DB_HOST=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'\''')"
DEV_NAME="$(grep -E '^DB_NAME=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'\''')"

# Refuse if this file is somehow pointed at whatever .env points at. The two are
# meant to be different machines; if they ever match, someone has copied the
# wrong credentials in and this script would quietly migrate production.
if [ -f "$SCRIPT_DIR/.env" ]; then
  PROD_HOST="$(grep -E '^DB_HOST=' "$SCRIPT_DIR/.env" | head -1 | cut -d= -f2- | tr -d '"'\''')"
  if [ -n "$PROD_HOST" ] && [ "$DEV_HOST" = "$PROD_HOST" ]; then
    echo "  REFUSING TO RUN: .env.development points at the same host as .env" >&2
    echo "  host: $DEV_HOST" >&2
    echo "  Fix .env.development before using this script." >&2
    exit 1
  fi
fi

echo ""
echo "  ┌──────────────────────────────────────────────"
echo "  │  Target: DEV"
echo "  │  Host:   $DEV_HOST"
echo "  │  DB:     $DEV_NAME"
echo "  └──────────────────────────────────────────────"
echo ""

# `status` only reads, so it does not need a confirmation — and making the safe
# command frictionless is what keeps people from reaching for the unsafe one.
if [ "${1:-}" != "status" ]; then
  printf "  Type the host to continue: "
  read -r TYPED
  if [ "$TYPED" != "$DEV_HOST" ]; then
    echo "  Did not match. Nothing was run." >&2
    exit 1
  fi
  echo ""
fi

MIGRATION_ENV_FILE="$ENV_FILE" exec bash "$SCRIPT_DIR/run_migrations.sh" "$@"
