"""
CRM Conversation Inbox admin handlers — Sprint 10 P1.

Standard CRUD entry points:
  GET    /admin/crm-conversations              → list_crm_conversations
  GET    /admin/crm-conversations/{id}         → get_crm_conversation
  DELETE /admin/crm-conversations/{id}         → set status='closed' (no hard delete)

Sub-routes dispatched by crm/__init__.py handle_crm_admin_subroute:
  POST /admin/crm-conversations/{id}/reply     → send_reply
  POST /admin/crm-conversations/{id}/mark-read → mark_read
  POST /admin/crm-conversations/{id}/status    → set_status (open|closed|spam)
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ....exceptions import BadRequestException, NotFoundException
from . import inbox_service

logger = logging.getLogger(__name__)


# ─── Standard CRUD ───────────────────────────────────────────────────────────

def list_crm_conversations(
    db: Session, query_params: dict, current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    # Super-admin: org_id may be None (list across all orgs) or filtered by ?organizationId=X.
    # Non-admin: must have organization_id resolved from query or token.
    org_id = _resolve_list_org_id(query_params, current_user)
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    filters = {
        'status':     query_params.get('status'),
        'unreadOnly': query_params.get('unreadOnly'),
        'q':          query_params.get('q'),
        'leadId':     query_params.get('leadId') or query_params.get('lead_id'),
    }
    return inbox_service.list_conversations(db, org_id, filters, page, page_size)


def get_crm_conversation(
    db: Session, resource_id: int, current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")
    return inbox_service.get_conversation(db, int(resource_id), org_id)


def delete_crm_conversation(
    db: Session, resource_id: int, current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    """Soft-close (no hard delete — conversations are append-only audit trail)."""
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")
    return inbox_service.set_status(db, int(resource_id), org_id, 'closed')


# ─── Sub-route dispatcher ─────────────────────────────────────────────────────

def dispatch_inbox_subroute(
    resource_id,
    sub_path: str,
    method: str,
    db: Session,
    data: dict,
    query_params: dict,
    current_user: dict,
) -> Dict[str, Any]:
    """
    Called from crm/__init__.py handle_crm_admin_subroute when resource == 'crm-conversations'.
    """
    parts = [p for p in (sub_path or '').strip('/').split('/') if p]
    org_id = _org_from_user(current_user) or _int_or_none(
        (data or {}).get('organizationId') or (query_params or {}).get('organizationId')
    )
    if not resource_id:
        raise NotFoundException(f"crm-conversations sub-route not found: {method} /{sub_path}")
    if not org_id:
        raise BadRequestException("organizationId is required")

    conv_id = int(resource_id)

    # POST /crm-conversations/{id}/reply
    if parts == ['reply'] and method == 'POST':
        return inbox_service.send_reply(
            db, conv_id, org_id,
            body_html=(data.get('bodyHtml') or data.get('body_html') or '').strip(),
            body_plain=data.get('bodyPlain') or data.get('body_plain'),
            subject=data.get('subject'),
            from_user=current_user,
        )

    # POST /crm-conversations/{id}/mark-read
    if parts == ['mark-read'] and method == 'POST':
        return inbox_service.mark_read(db, conv_id, org_id)

    # POST /crm-conversations/{id}/status
    if parts == ['status'] and method == 'POST':
        status = (data.get('status') or '').strip()
        if not status:
            raise BadRequestException("'status' is required in request body")
        return inbox_service.set_status(db, conv_id, org_id, status)

    raise NotFoundException(f"crm-conversations sub-route not found: {method} /{sub_path}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require_org_id(source: dict, user: Optional[dict] = None) -> int:
    raw = ((source or {}).get('organizationId') or (source or {}).get('organization_id')
           or (user or {}).get('organization_id'))
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise BadRequestException("organizationId is required")


def _org_from_user(current_user: Optional[dict]) -> Optional[int]:
    if not current_user:
        return None
    raw = current_user.get('organization_id')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_super_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    role = (user.get('admin_role') or user.get('platform_role') or '').strip()
    return role in ('super-admin', 'gepp-admin')


def _resolve_list_org_id(query_params: dict, current_user: Optional[dict] = None) -> Optional[int]:
    """List-endpoint org resolution — see lead_handlers._resolve_list_org_id."""
    raw = (query_params or {}).get('organizationId') or (query_params or {}).get('organization_id')
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    if _is_super_admin(current_user):
        return None
    v = _org_from_user(current_user)
    if v is not None:
        return v
    raise BadRequestException("organizationId is required")


def _int_or_none(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
