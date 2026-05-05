"""
Per-request DB target resolver for the admin XLSX export.

Lets the backoffice user choose at export-time which database to pull
from — local / dev / prod — without restarting the local backend. Each
target's connection string is read from the corresponding file under
v3/backend/migrations/:

    local → relies on the env vars the running process already has
    dev   → migrations/.env.development
    prd   → migrations/.env

Engines are cached per (host, port, db, user) tuple so repeat exports
reuse the same connection pool. This is intentionally a *local-dev
feature*: in deployed Lambda the migrations/*.env files don't ship, and
the resolver gracefully falls back to the request's existing session.
"""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool


SUPPORTED_TARGETS = ('local', 'dev', 'prd')

# Resolves to /v3/backend/migrations relative to this file.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_MIGRATIONS_DIR = _BACKEND_ROOT / 'migrations'

_ENV_FILE_BY_TARGET: Dict[str, Path] = {
    'dev': _MIGRATIONS_DIR / '.env.development',
    'prd': _MIGRATIONS_DIR / '.env',
}

# (host, port, db, user) → Engine. Cache so we don't recreate the pool
# on every export.
_ENGINE_CACHE: Dict[Tuple[str, str, str, str], Engine] = {}


def _conn_creds_for_target(target: str) -> Optional[Dict[str, str]]:
    """Return a dict of DB_* values for `target`, or None to mean
    'use the current process env'."""
    if target == 'local':
        return None
    env_path = _ENV_FILE_BY_TARGET.get(target)
    if not env_path or not env_path.exists():
        raise FileNotFoundError(
            f"DB target '{target}' requested but env file not found: {env_path}"
        )
    raw = dotenv_values(env_path)
    if not raw:
        raise ValueError(f"DB target '{target}' env file is empty: {env_path}")
    # Bridge DB_PASSWORD ↔ DB_PASS so callers can treat them as one.
    if not raw.get('DB_PASS') and raw.get('DB_PASSWORD'):
        raw['DB_PASS'] = raw['DB_PASSWORD']
    if not raw.get('DB_PASSWORD') and raw.get('DB_PASS'):
        raw['DB_PASSWORD'] = raw['DB_PASS']
    return {k: v for k, v in raw.items() if v is not None}


def _engine_for(creds: Dict[str, str]) -> Engine:
    host = creds.get('DB_HOST', 'localhost')
    port = creds.get('DB_PORT', '5432')
    name = creds.get('DB_NAME', 'gepp_platform')
    user = creds.get('DB_USER', 'postgres')
    pw   = creds.get('DB_PASS') or creds.get('DB_PASSWORD') or ''
    key = (host, str(port), name, user)
    eng = _ENGINE_CACHE.get(key)
    if eng is not None:
        return eng
    url = f"postgresql://{user}:{pw}@{host}:{port}/{name}"
    eng = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=4,
        pool_pre_ping=True,
        echo=False,
    )
    _ENGINE_CACHE[key] = eng
    return eng


def session_for_target(
    target: str,
    fallback_session: Session,
) -> Tuple[Session, bool]:
    """Returns (session, is_new).

    `is_new=True` means the caller owns the session and must close it
    (we minted it for this target). `is_new=False` means we returned the
    request's existing session — don't close it."""
    target = (target or 'local').strip().lower()
    if target not in SUPPORTED_TARGETS:
        raise ValueError(
            f"Unknown dbTarget '{target}'. Use one of: {', '.join(SUPPORTED_TARGETS)}"
        )
    creds = _conn_creds_for_target(target)
    if creds is None:
        return fallback_session, False
    eng = _engine_for(creds)
    SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    return SessionLocal(), True
