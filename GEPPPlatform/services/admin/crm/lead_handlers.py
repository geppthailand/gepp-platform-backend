"""
CRM Lead admin handlers — list/get/create/update/delete + sub-routes.

Sub-routes dispatched by crm/__init__.py handle_crm_admin_subroute:
  POST /admin/crm-leads/{id}/status      → change_status
  POST /admin/crm-leads/{id}/assign      → assign_owner
  POST /admin/crm-leads/{id}/convert     → convert_lead
  POST /admin/crm-leads/{id}/score       → score_lead
  GET  /admin/crm-leads/{id}/activities  → list_activities
  POST /admin/crm-leads/{id}/activities  → add_activity (manual note/call/meeting)
  POST /admin/crm-leads/import           → bulk_import_csv
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from ....exceptions import BadRequestException, NotFoundException
from . import lead_service

logger = logging.getLogger(__name__)

# ─── Standard CRUD ─────────────────────────────────────────────────────────

def list_crm_leads(db: Session, query_params: dict, current_user: Optional[dict] = None) -> Dict[str, Any]:
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    # Super-admin / gepp-admin can list across all orgs (or filter by ?organizationId=X).
    # Non-admin callers must have organization_id resolved from their token.
    org_id = _resolve_list_org_id(query_params, current_user)

    filters = {
        'status':             query_params.get('status'),
        'owner_user_id':      query_params.get('ownerUserId'),
        'source':             query_params.get('source'),
        'country':            query_params.get('country'),
        'tag':                query_params.get('tag'),
        'min_score':          query_params.get('minScore'),
        'max_score':          query_params.get('maxScore'),
        'q':                  query_params.get('q'),
        'created_after':      query_params.get('createdAfter'),
        'last_activity_after':query_params.get('lastActivityAfter'),
    }

    return lead_service.list_leads(db, org_id, filters, page, page_size)


def get_crm_lead(db: Session, resource_id: int, current_user: Optional[dict] = None) -> Dict[str, Any]:
    org_id = _org_from_user(current_user) or _org_from_lead(db, resource_id, current_user)
    return lead_service.get_lead(db, resource_id, org_id)


def create_crm_lead(db: Session, data: dict, current_user: Optional[dict] = None) -> Dict[str, Any]:
    org_id = _create_org_id(data, current_user)
    if org_id is None and data.get('organizationName') and not data.get('company'):
        data = {**data, 'company': data.get('organizationName')}
    return lead_service.create_lead(
        db,
        org_id=org_id,
        data=data,
        source=data.get('source') or 'manual',
        source_metadata=data.get('sourceMetadata') or data.get('source_metadata'),
        owner_user_id=_int_or_none(data.get('ownerUserId') or data.get('owner_user_id')),
    )


def update_crm_lead(
    db: Session, resource_id: int, data: dict, current_user: Optional[dict] = None
) -> Dict[str, Any]:
    org_id = _optional_org_id(data, user=current_user) or _org_from_lead(db, resource_id, current_user)
    return lead_service.update_lead(db, resource_id, org_id, data)


def delete_crm_lead(db: Session, resource_id: int, current_user: Optional[dict] = None) -> Dict[str, Any]:
    org_id = _org_from_user(current_user) or _org_from_lead(db, resource_id, current_user)
    return lead_service.delete_lead(db, resource_id, org_id)


# ─── Sub-route dispatcher ─────────────────────────────────────────────────────

def dispatch_lead_subroute(
    resource_id,
    sub_path: str,
    method: str,
    db: Session,
    data: dict,
    query_params: dict,
    current_user: dict,
) -> Dict[str, Any]:
    """
    Called from crm/__init__.py handle_crm_admin_subroute when resource == 'crm-leads'.
    """
    from ....exceptions import NotFoundException as _NF
    parts = [p for p in (sub_path or '').strip('/').split('/') if p]
    org_id = _org_from_user(current_user) or _int_or_none(
        data.get('organizationId') or query_params.get('organizationId')
    )

    # POST /crm-leads/import  (no resource_id)
    if not resource_id and parts == ['import'] and method == 'POST':
        if not org_id:
            raise BadRequestException("organizationId is required for CSV import")
        csv_text = data.get('csvText') or data.get('csv_text') or ''
        owner_uid = _int_or_none(
            data.get('ownerUserId') or data.get('owner_user_id')
            or (current_user or {}).get('user_id')
        )
        return lead_service.bulk_import_csv(db, org_id, csv_text, owner_user_id=owner_uid)

    # All remaining sub-routes require a numeric resource_id.
    if not resource_id:
        raise _NF(f"crm-leads sub-route not found: {method} /{sub_path}")
    if not org_id:
        org_id = _org_from_lead(db, int(resource_id), current_user)

    lead_id = int(resource_id)
    by_user = _int_or_none((current_user or {}).get('user_id') or (current_user or {}).get('id'))

    # POST /crm-leads/{id}/status
    if parts == ['status'] and method == 'POST':
        new_status = (data.get('status') or '').strip()
        if not new_status:
            raise BadRequestException("'status' is required in request body")
        return lead_service.change_status(db, lead_id, org_id, new_status, by_user_id=by_user)

    # POST /crm-leads/{id}/assign
    if parts == ['assign'] and method == 'POST':
        owner_uid = _int_or_none(data.get('ownerUserId') or data.get('owner_user_id'))
        if owner_uid is None:
            raise BadRequestException("'ownerUserId' is required in request body")
        return lead_service.assign_owner(db, lead_id, org_id, owner_uid, by_user_id=by_user)

    # POST /crm-leads/{id}/convert
    if parts == ['convert'] and method == 'POST':
        user_loc_id = _int_or_none(
            data.get('userLocationId') or data.get('user_location_id')
        )
        if user_loc_id is None:
            raise BadRequestException("'userLocationId' is required in request body")
        return lead_service.convert_lead(db, lead_id, org_id, user_loc_id)

    # POST /crm-leads/{id}/score
    if parts == ['score'] and method == 'POST':
        return lead_service.score_lead(db, lead_id)

    # GET /crm-leads/{id}/activities
    if parts == ['activities'] and method == 'GET':
        try:
            page = max(1, int(query_params.get('page', 1) or 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(200, int(query_params.get('pageSize', 50) or 50)))
        except (TypeError, ValueError):
            page_size = 50
        return lead_service.list_activities(db, lead_id, page, page_size)

    # POST /crm-leads/{id}/activities  — manual note / call / meeting
    if parts == ['activities'] and method == 'POST':
        activity_type = (data.get('activityType') or data.get('activity_type') or 'note_added').strip()
        properties    = data.get('properties') or {}
        act_id = lead_service.add_activity(
            db, lead_id,
            activity_type=activity_type,
            properties=properties,
            user_id=by_user,
        )
        db.commit()
        return {"id": act_id, "leadId": lead_id, "activityType": activity_type}

    raise _NF(f"crm-leads sub-route not found: {method} /{sub_path}")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _is_super_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    role = (user.get('admin_role') or user.get('platform_role') or '').strip()
    return role in ('super-admin', 'gepp-admin')


def _resolve_list_org_id(source: dict, user: Optional[dict] = None) -> Optional[int]:
    """
    For list endpoints:
      - super-admin: optional ?organizationId=X filter, otherwise return None (see all orgs)
      - non-admin: must have organization_id from their token, else BadRequest
    """
    raw = (source or {}).get('organizationId') or (source or {}).get('organization_id')
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    if _is_super_admin(user):
        return None
    user_org = (user or {}).get('organization_id')
    try:
        return int(user_org)
    except (TypeError, ValueError):
        raise BadRequestException("organizationId is required")


def _require_org_id(source: dict, user: Optional[dict] = None) -> int:
    """Extract and return org_id from body/query, falling back to current_user."""
    raw = _raw_org_id(source, user)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise BadRequestException("organizationId is required")


def _create_org_id(source: dict, user: Optional[dict] = None) -> Optional[int]:
    org_id = _optional_org_id(source, user)
    if org_id is not None:
        return org_id
    if _is_super_admin(user):
        return None
    raise BadRequestException("organizationId is required")


def _optional_org_id(source: dict, user: Optional[dict] = None) -> Optional[int]:
    raw = _raw_org_id(source, user)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _raw_org_id(source: dict, user: Optional[dict] = None):
    return ((source or {}).get('organizationId') or (source or {}).get('organization_id')
            or (user or {}).get('organization_id'))


def _org_from_user(current_user: Optional[dict]) -> Optional[int]:
    if not current_user:
        return None
    raw = current_user.get('organization_id')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _org_from_lead(db: Session, lead_id: int, current_user: Optional[dict]) -> Optional[int]:
    if not _is_super_admin(current_user):
        raise BadRequestException("organizationId is required")
    row = db.execute(
        text("SELECT organization_id FROM crm_leads WHERE id = :id AND deleted_date IS NULL"),
        {'id': lead_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Lead {lead_id} not found")
    return int(row[0]) if row[0] is not None else None


def _int_or_none(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
