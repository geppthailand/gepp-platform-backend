#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# GEPP Platform — Run Lambda locally as a Flask dev server
#
# First run bootstraps everything automatically:
#   1. Creates .venv
#   2. Installs all dependencies (layers + app + local server)
#   3. Starts Flask server that simulates API Gateway → Lambda
#
# Usage:
#   ./run_local.sh              # default port 9000
#   ./run_local.sh 8080         # custom port
#   ./run_local.sh --install    # force reinstall all deps
# ──────────────────────────────────────────────────────────────

PORT="9000"
FORCE_INSTALL=false

for arg in "$@"; do
  case "$arg" in
    --install) FORCE_INSTALL=true ;;
    [0-9]*)    PORT="$arg" ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.local.txt"
STAMP_FILE="$VENV_DIR/.deps-installed"

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[*]${NC} $1"; }
ok()   { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }

# ── 1. Find Python 3.13 ───────────────────────────────────────
PYTHON=""
for candidate in python3.13 python3; do
  if command -v "$candidate" &>/dev/null; then
    PY_VER=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [ "$PY_VER" = "3.13" ]; then
      PYTHON="$(command -v "$candidate")"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  err "Python 3.13 not found. Please install it first."
  err "  macOS: brew install python@3.13"
  exit 1
fi

log "Using Python 3.13 ($PYTHON)"

# ── 2. Load .env.local (local dev config) ─────────────────────
ENV_FILE="$SCRIPT_DIR/.env.local"
if [ -f "$ENV_FILE" ]; then
  log "Loading .env.local"
  set -a; source "$ENV_FILE"; set +a
else
  warn "No .env.local found. Creating from template..."
  cat > "$ENV_FILE" << 'ENVEOF'
# Local Development Configuration
# Used by: run_local.sh (local Lambda server)

# Database Configuration (LOCAL)
DATABASE_URL=postgresql://postgres:@localhost:5432/gepp_platform
DB_HOST=localhost
DB_PORT=5432
DB_NAME=gepp_platform
DB_USER=postgres
DB_PASS=

# JWT Configuration
JWT_SECRET_KEY=local_dev_secret
JWT_ALGORITHM=HS256

DEBUG=True
LOG_LEVEL=INFO
ENVEOF
  warn "Created .env.local — edit with your local DB credentials, then re-run."
  exit 1
fi

# ── 3. Parse DATABASE_URL if individual DB_* vars missing ────
if [ -n "${DATABASE_URL:-}" ] && [ -z "${DB_HOST:-}" ]; then
  rest="${DATABASE_URL#*://}"
  userpass="${rest%%@*}"
  export DB_USER="${userpass%%:*}"
  export DB_PASS="${userpass#*:}"
  hostportdb="${rest#*@}"
  hostport="${hostportdb%%/*}"
  export DB_HOST="${hostport%%:*}"
  export DB_PORT="${hostport#*:}"
  export DB_NAME="${hostportdb#*/}"
  log "Parsed DATABASE_URL -> ${DB_HOST}:${DB_PORT}/${DB_NAME}"
fi

# ── 4. Create venv if missing ────────────────────────────────
# Recreate venv if it exists but uses wrong Python version
if [ -d "$VENV_DIR" ]; then
  VENV_PY_VER=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0")
  if [ "$VENV_PY_VER" != "3.13" ]; then
    warn "Existing .venv uses Python $VENV_PY_VER, recreating with 3.13 ..."
    rm -rf "$VENV_DIR"
  fi
fi

if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtual environment at .venv ..."
  "$PYTHON" -m venv "$VENV_DIR"
  FORCE_INSTALL=true
fi

# Activate
source "$VENV_DIR/bin/activate"

# ── 5. Install / sync dependencies ──────────────────────────
needs_install() {
  if [ "$FORCE_INSTALL" = true ]; then return 0; fi
  if [ ! -f "$STAMP_FILE" ]; then return 0; fi
  # Reinstall if requirements file changed since last install
  if [ "$REQ_FILE" -nt "$STAMP_FILE" ]; then return 0; fi
  return 1
}

if needs_install; then
  log "Installing / syncing dependencies ..."
  pip install --quiet --upgrade pip

  # Install everything from requirements.local.txt
  if [ -f "$REQ_FILE" ]; then
    pip install --quiet -r "$REQ_FILE" 2>&1 | grep -v "already satisfied" || true
  else
    err "requirements.local.txt not found at $REQ_FILE"
    exit 1
  fi

  # Stamp so we skip next time unless file changes
  touch "$STAMP_FILE"
  ok "All dependencies installed."
else
  # Quick check: verify a few critical packages are importable
  MISSING=()
  for pkg in flask sqlalchemy psycopg2 jwt bcrypt boto3 numpy scipy pgvector yaml dateutil openai; do
    if ! python3 -c "import $pkg" 2>/dev/null; then
      MISSING+=("$pkg")
    fi
  done

  if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Missing packages detected: ${MISSING[*]}"
    log "Re-installing dependencies ..."
    pip install --quiet -r "$REQ_FILE" 2>&1 | grep -v "already satisfied" || true
    touch "$STAMP_FILE"
    ok "Dependencies fixed."
  fi
fi

# ── 6. Start local server ────────────────────────────────────
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  GEPP Platform — Local Lambda Server${NC}"
echo -e "${GREEN}  Port: $PORT${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

export PYTHONPATH="$SCRIPT_DIR"
export PORT="$PORT"

exec "$VENV_DIR/bin/python" -c "
import json, sys, os, traceback

sys.path.insert(0, os.environ.get('PYTHONPATH', '.'))

from flask import Flask, request, Response
from GEPPPlatform.app import main as lambda_handler

app = Flask(__name__)

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
}

@app.after_request
def add_cors(response):
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response

@app.route('/')
def index():
    port = os.environ.get('PORT', 9000)
    routes = [
        ('GET',  '/health',              'Health check'),
        ('*',    '/api/auth/...',         'Authentication (login, register, refresh, validate)'),
        ('*',    '/api/users/...',        'User management'),
        ('*',    '/api/locations/...',    'Location management'),
        ('*',    '/api/organizations/...','Organization management'),
        ('*',    '/api/materials/...',    'Materials management'),
        ('*',    '/api/transactions/...', 'Transaction management'),
        ('*',    '/api/transaction_audit/...', 'Transaction audit'),
        ('*',    '/api/traceability/...', 'Traceability'),
        ('*',    '/api/reports/...',      'Reports'),
        ('*',    '/api/audit/...',        'Audit rules'),
        ('*',    '/api/audit-settings/...', 'AI audit settings'),
        ('*',    '/api/rewards/...',      'Rewards management'),
        ('*',    '/api/esg/...',          'ESG platform'),
        ('*',    '/api/gri/...',          'GRI reporting'),
        ('*',    '/api/integration/bma/...', 'BMA integration'),
        ('*',    '/api/input-channel/...','Public input channel (QR)'),
        ('*',    '/api/iot-devices/...',  'IoT devices'),
        ('*',    '/api/debug/...',        'Debug (dev only)'),
        ('*',    '/api/userapi/{api_path}/{service_path}/...', 'Custom API'),
    ]
    rows = ''.join(
        f'<tr><td><code>{m}</code></td><td><a href=\"{p.split(\"...\")[0]}\">{p}</a></td><td>{d}</td></tr>'
        if '...' not in p else
        f'<tr><td><code>{m}</code></td><td>{p}</td><td>{d}</td></tr>'
        for m, p, d in routes
    )
    return f'''<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>GEPP Platform Local</title>
<style>body{{font-family:system-ui;max-width:800px;margin:40px auto;padding:0 20px;background:#0f172a;color:#e2e8f0}}
h1{{color:#38bdf8}}table{{width:100%;border-collapse:collapse;margin-top:20px}}
th,td{{text-align:left;padding:8px 12px;border-bottom:1px solid #334155}}
th{{color:#94a3b8;font-size:12px;text-transform:uppercase}}
code{{background:#1e293b;padding:2px 6px;border-radius:4px;font-size:13px}}
a{{color:#38bdf8;text-decoration:none}}a:hover{{text-decoration:underline}}</style></head>
<body><h1>GEPP Platform — Local Server</h1><p>Running on port {port}</p>
<table><tr><th>Method</th><th>Path</th><th>Description</th></tr>{rows}</table></body></html>''', 200, {{'Content-Type': 'text/html'}}

@app.route('/<path:path>', methods=['GET','POST','PUT','DELETE','PATCH','OPTIONS'])
def catch_all(path):
    event = {
        'rawPath': f'/{path}',
        'requestContext': {
            'http': {
                'method': request.method,
                'path': f'/{path}',
            }
        },
        'headers': {k: v for k, v in request.headers},
        'queryStringParameters': dict(request.args) if request.args else None,
        'pathParameters': {},
        'body': request.get_data(as_text=True) or None,
    }

    try:
        result = lambda_handler(event, None)
    except Exception as e:
        result = {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e), 'trace': traceback.format_exc()}),
        }

    status = result.get('statusCode', 200)
    resp_headers = result.get('headers', {})
    body = result.get('body', '')

    return Response(body, status=status, headers=resp_headers)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 9000))
    print()
    print('  Routes:')
    print(f'    Health check  : http://localhost:{port}/health')
    print(f'    Auth          : http://localhost:{port}/api/auth/...')
    print(f'    Users         : http://localhost:{port}/api/users/...')
    print(f'    Transactions  : http://localhost:{port}/api/transactions/...')
    print(f'    Materials     : http://localhost:{port}/api/materials/...')
    print()
    app.run(host='0.0.0.0', port=port, debug=True)
"
