"""EPR AI Audit API handlers.

Dispatches the 4 routes ported from gepp-v2-backend:
  POST   /api/epr/ai_audit/embed-transaction
  GET    /api/epr/ai_audit/transactions
  PUT    /api/epr/ai_audit/embed-transaction/{source_id}
  PATCH  /api/epr/ai_audit/transactions/{source_id}/status   (audit decision)
"""

import re
from typing import Any, Dict

from GEPPPlatform.libs.exceptions import APIException, NotFoundException
from .service import EprAiAuditService


# PUT /api/epr/ai_audit/embed-transaction/{source_id}
_EDIT_PATH_RE = re.compile(r"/epr/ai_audit/embed-transaction/([^/]+)$")

# PATCH /api/epr/ai_audit/transactions/{source_id}/status
_STATUS_PATH_RE = re.compile(r"/epr/ai_audit/transactions/([^/]+)/status$")


def handle_epr_ai_audit_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    path = event.get("rawPath", "")
    method = params.get("method", "GET")

    db_session = params.get("db_session")
    if not db_session:
        raise APIException("Database session not provided")

    service = EprAiAuditService(db_session)
    query_params = params.get("query_params") or {}

    if path.endswith("/epr/ai_audit/ocr") and method == "POST":
        from .ocr import read_transaction
        files = data.get("files") or []
        fields = data.get("fields") or []
        if not files:
            raise APIException("No files provided")
        return {"success": True, "data": read_transaction(files, fields)}

    if path.endswith("/epr/ai_audit/recycler-audit-ocr") and method == "POST":
        from .ocr import read_audit
        files = data.get("files") or []
        fields = data.get("fields") or []
        if not files:
            raise APIException("No files provided")
        return {"success": True, "data": read_audit(files, fields)}

    if path.endswith("/epr/ai_audit/embed-transaction") and method == "POST":
        return {"success": True, "data": service.embed_transaction(data)}

    if path.endswith("/epr/ai_audit/transactions") and method == "GET":
        return {"success": True, "data": service.list_transactions(query_params)}

    if method == "PUT":
        m = _EDIT_PATH_RE.search(path)
        if m:
            source_id = m.group(1)
            return {"success": True, "data": service.update_transaction(source_id, data)}

    if method == "PATCH":
        m = _STATUS_PATH_RE.search(path)
        if m:
            source_id = m.group(1)
            return {"success": True, "data": service.update_status(source_id, data)}

    raise NotFoundException(f"Route not found: {path} [{method}]")
