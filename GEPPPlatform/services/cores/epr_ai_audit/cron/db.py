"""Tiny psycopg2 connection helper for the EPR AI audit cron.

The platform-backend's primary connection model is SQLAlchemy
(see GEPPPlatform.libs.database). The cron Lambda for EPR AI audit was
ported verbatim from gepp-v2-backend and uses raw psycopg2 throughout —
keeping the same model here avoids rewriting ~2000 lines of worker /
dedup / legacy_import code.

Same DB_* env vars as the SQLAlchemy setup.
"""

import os

import psycopg2


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "gepp_platform"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASS", ""),
    )
