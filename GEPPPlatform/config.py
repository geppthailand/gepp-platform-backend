"""
Non-secret app-wide configuration.

This file is the single source of truth for values like the deployed version
string, build commit, etc. — anything callers want to see in response headers
or `/api/version` payloads to verify they're hitting fresh code.

Bump ``VERSION`` *before* each deploy so a stale Lambda is trivial to detect:
the response header ``X-App-Version`` is what's actually running on the
server. Compare against the value the build pipeline shipped to know whether
your edit landed.

NOTHING in this file is secret. Secrets stay in env vars / AWS Secrets Manager.
"""

import os

# ── Version metadata ──────────────────────────────────────────────────────
# Bump VERSION on every meaningful deploy. Format is free-form; semver-ish
# (MAJOR.MINOR.PATCH) is what we use today.
VERSION: str = "2026.05.18.02"

# Short label describing the change in this version (free text, optional).
# Surfaced in /api/version for a quick human-readable confirmation.
VERSION_NOTE: str = (
    "waste-transactions date filter now uses TransactionRecord.transaction_date "
    "(EXISTS-subquery); materials report splits Waste-to-Energy items"
)

# Build-time / commit info — usually injected by CI at deploy time via env
# vars, but the default makes local runs identifiable too.
BUILD_COMMIT: str = os.environ.get("BUILD_COMMIT", "local")
BUILD_TIME: str = os.environ.get("BUILD_TIME", "")
DEPLOYMENT_STATE: str = os.environ.get("DEPLOYMENT_STATE", "")


def version_payload() -> dict:
    """Compact dict surfaced by /api/version and the response headers."""
    return {
        "version": VERSION,
        "note": VERSION_NOTE,
        "commit": BUILD_COMMIT,
        "build_time": BUILD_TIME,
        "deployment_state": DEPLOYMENT_STATE,
    }
