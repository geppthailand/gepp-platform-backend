"""EPR AI Audit core service.

Ported from gepp-v2-backend (GEPPV2.services.ai_audit). Split into two layers:

  api/   — synchronous REST handlers for /api/epr/ai_audit/* (SQLAlchemy session)
           POST  /api/epr/ai_audit/embed-transaction
           GET   /api/epr/ai_audit/transactions
           PUT   /api/epr/ai_audit/embed-transaction/{source_id}
           PATCH /api/epr/ai_audit/transactions/{source_id}/status   (audit decision)

  cron/  — background dedup worker driven by entry_points/GEPPEPRAIAudit.py
           (raw psycopg2 connections, matches the v2 source). Includes the
           queue helpers, the per-transaction worker, and the duplicate
           scorer. Dedup compares each transaction against the others in its
           own project; there is no legacy-MySQL comparison corpus.
"""

from .api.handlers import handle_epr_ai_audit_routes  # noqa: F401
