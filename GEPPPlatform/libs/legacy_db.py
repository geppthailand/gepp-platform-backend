"""
Read-only connection helper for the legacy MySQL DB (Gepp_new, served by
gepp-new-api). Used by the dedup pipeline to backfill historical
transactions into our Postgres so new submissions have something to
compare against.

Connection parameters come from LEGACY_DB_* env vars. Missing vars raise
a clear ValueError rather than silently failing — the cron worker handles
the error and marks the job as failed-with-retry.
"""

import logging
import os

import pymysql

logger = logging.getLogger(__name__)


def get_legacy_connection():
    """Return a new PyMySQL connection to the legacy Gepp_new database.

    Use as `conn = get_legacy_connection(); try: ... finally: conn.close()`.
    DictCursor isn't set by default — callers use tuple rows for consistency
    with the psycopg2 patterns elsewhere in this codebase.
    """
    host = os.environ.get("LEGACY_DB_HOST")
    port = os.environ.get("LEGACY_DB_PORT")
    user = os.environ.get("LEGACY_DB_USER")
    password = os.environ.get("LEGACY_DB_PASS")
    database = os.environ.get("LEGACY_DB_NAME")

    missing = [k for k, v in [
        ("LEGACY_DB_HOST", host), ("LEGACY_DB_PORT", port),
        ("LEGACY_DB_USER", user), ("LEGACY_DB_PASS", password),
        ("LEGACY_DB_NAME", database),
    ] if not v]
    if missing:
        raise ValueError(f"Legacy DB not configured. Missing env vars: {', '.join(missing)}")

    return pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=60,
    )
