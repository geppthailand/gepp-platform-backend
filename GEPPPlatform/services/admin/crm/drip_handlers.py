"""
CRM Drip Sequences admin handlers — Sprint 10.

Routes dispatched by crm/__init__.py handle_crm_admin_subroute:
  GET    /admin/crm-drip-sequences                           → list
  POST   /admin/crm-drip-sequences                           → create
  GET    /admin/crm-drip-sequences/{id}                      → get (with steps)
  PATCH  /admin/crm-drip-sequences/{id}                      → update
  DELETE /admin/crm-drip-sequences/{id}                      → soft delete
  POST   /admin/crm-drip-sequences/{id}/status               → set_status
  POST   /admin/crm-drip-sequences/{id}/enroll               → enroll
  GET    /admin/crm-drip-sequences/{id}/enrollments          → list_enrollments
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ....exceptions import BadRequestException, NotFoundException
from . import drip_service

logger = logging.getLogger(__name__)


# ─── CRUD ────────────────────────────────────────────────────────────────────

def list_crm_drip_sequences(
    db: Session,
    query_params: dict,
    current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    # Super-admin: org_id may be None (list across all orgs) or filtered by ?organizationId=X.
    # Non-admin: must have organization_id resolved from query or token.
    org_id = _resolve_list_org_id(query_params, current_user)
    try:
        page = max(1, int(query_params.get("page", 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get("pageSize", 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    filters = {
        "status":        query_params.get("status"),
        "trigger_event": query_params.get("triggerEvent"),
        "q":             query_params.get("q"),
    }
    return drip_service.list_sequences(db, org_id, filters, page, page_size)


def get_crm_drip_sequence(
    db: Session,
    resource_id: int,
    current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")
    return drip_service.get_sequence(db, resource_id, org_id)


def create_crm_drip_sequence(
    db: Session,
    data: dict,
    current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")
    created_by = (current_user or {}).get("user_location_id")
    return drip_service.create_sequence(db, org_id, data, created_by=created_by)


def update_crm_drip_sequence(
    db: Session,
    resource_id: int,
    data: dict,
    current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")
    return drip_service.update_sequence(db, resource_id, org_id, data)


def delete_crm_drip_sequence(
    db: Session,
    resource_id: int,
    current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")
    return drip_service.delete_sequence(db, resource_id, org_id)


# ─── Sub-routes ──────────────────────────────────────────────────────────────

def dispatch_drip_subroute(
    resource_id: Optional[int],
    sub_path: str,
    method: str,
    db: Session,
    data: dict,
    query_params: dict,
    current_user: Optional[dict],
) -> Dict[str, Any]:
    """
    Dispatch sub-routes for crm-drip-sequences.
    sub_path is the trailing part after the resource_id.
    """
    org_id = _org_from_user(current_user)
    if org_id is None:
        raise BadRequestException("organizationId is required")

    # ── POST /{id}/status ─────────────────────────────────────────────────
    if sub_path == "status" and method == "POST":
        if not resource_id:
            raise BadRequestException("sequence id is required")
        new_status = (data.get("status") or "").strip()
        if not new_status:
            raise BadRequestException("status is required")
        return drip_service.set_status(db, resource_id, org_id, new_status)

    # ── POST /{id}/enroll ─────────────────────────────────────────────────
    if sub_path == "enroll" and method == "POST":
        if not resource_id:
            raise BadRequestException("sequence id is required")
        lead_id          = data.get("leadId") or data.get("lead_id")
        user_location_id = data.get("userLocationId") or data.get("user_location_id")
        if not lead_id and not user_location_id:
            raise BadRequestException("leadId or userLocationId is required")
        return drip_service.enroll(
            db, resource_id,
            lead_id=int(lead_id) if lead_id else None,
            user_location_id=int(user_location_id) if user_location_id else None,
            org_id=org_id,
        )

    # ── GET /{id}/enrollments ─────────────────────────────────────────────
    if sub_path == "enrollments" and method == "GET":
        if not resource_id:
            raise BadRequestException("sequence id is required")
        try:
            page = max(1, int(query_params.get("page", 1) or 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(200, int(query_params.get("pageSize", 25) or 25)))
        except (TypeError, ValueError):
            page_size = 25
        return drip_service.list_enrollments(db, resource_id, org_id, page, page_size)

    raise NotFoundException(
        f"crm-drip-sequences sub-route not found: {method} /{sub_path}"
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _org_from_user(current_user: Optional[dict]) -> Optional[int]:
    if not current_user:
        return None
    v = current_user.get("organization_id") or current_user.get("organizationId")
    return int(v) if v else None


def _require_org_id(query_params: dict, current_user: Optional[dict] = None) -> int:
    v = (query_params or {}).get("organizationId") or (query_params or {}).get("organization_id")
    if v:
        return int(v)
    if current_user:
        v2 = _org_from_user(current_user)
        if v2:
            return v2
    raise BadRequestException("organizationId is required")


def _is_super_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    role = (user.get("admin_role") or user.get("platform_role") or "").strip()
    return role in ("super-admin", "gepp-admin")


def _resolve_list_org_id(query_params: dict, current_user: Optional[dict] = None) -> Optional[int]:
    """
    List-endpoint org resolution:
      - explicit ?organizationId=X wins for everyone
      - super-admin without query param → None (list across all orgs)
      - non-admin → derive from token, else BadRequest
    """
    raw = (query_params or {}).get("organizationId") or (query_params or {}).get("organization_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    if _is_super_admin(current_user):
        return None
    v = _org_from_user(current_user)
    if v:
        return v
    raise BadRequestException("organizationId is required")
