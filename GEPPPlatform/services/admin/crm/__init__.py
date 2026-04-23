"""CRM / Marketing admin routes — dispatches /api/admin/crm-* to the right handler method.

Wired into the main admin router via admin_handlers.py handler_map dicts (see AdminHandlers methods
list_resource / get_resource / create_resource / update_resource / delete_resource).

Analytics + segments + templates + campaigns + email lists also have sub-paths (e.g. `/preview`,
`/evaluate`, `/test`, `/metrics`) that are routed here from services/admin/__init__.py.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session

from ...exceptions import APIException, NotFoundException, BadRequestException
from . import crm_service


def handle_crm_admin_subroute(
    resource: str,
    resource_id,
    sub_path: str,
    method: str,
    db_session: Session,
    data: dict,
    query_params: dict,
    current_user: dict,
) -> Dict[str, Any]:
    """
    Dispatch CRM admin sub-routes like:
      POST /admin/crm-segments/preview
      POST /admin/crm-segments/{id}/evaluate
      GET  /admin/crm-segments/{id}/members
      GET  /admin/crm-segments/{id}/insights
      GET  /admin/crm-segments/{id}/versions
      POST /admin/crm-segments/{id}/clone
      GET  /admin/crm-segments/fields
      POST /admin/crm-templates/render-preview
      POST /admin/crm-templates/generate-ai
      POST /admin/crm-campaigns/{id}/start | pause | resume | archive | test
      GET  /admin/crm-campaigns/{id}/deliveries
      GET  /admin/crm-campaigns/{id}/metrics
      GET  /admin/crm-campaigns/{id}/impact
      GET  /admin/crm-analytics/overview
      GET  /admin/crm-analytics/org/{id}
      GET  /admin/crm-analytics/org/{id}/users
      GET  /admin/crm-analytics/timeseries
      GET  /admin/crm-analytics/funnel
    """
    # ── Analytics ────────────────────────────────────────────────────────────
    if resource == 'crm-analytics' and method == 'GET':
        return _dispatch_analytics(sub_path, db_session, query_params)

    # ── Segments / Templates / Campaigns (BE2 Sprint 2-4) ────────────────────
    if resource == 'crm-segments':
        return _dispatch_segments(resource_id, sub_path, method, db_session, data, query_params)

    if resource == 'crm-templates':
        return _dispatch_templates(resource_id, sub_path, method, db_session, data, query_params)

    if resource == 'crm-campaigns':
        return _dispatch_campaigns(resource_id, sub_path, method, db_session, data, query_params)

    raise NotFoundException(
        f"CRM sub-route not found: {method} /{resource}/{resource_id or ''}/{sub_path}"
    )


# ─── Analytics dispatcher ────────────────────────────────────────────────────

def _dispatch_analytics(
    sub_path: str,
    db_session: Session,
    query_params: dict,
) -> Dict[str, Any]:
    """
    Routes:
      overview                  → get_analytics_overview
      org/{id}                  → get_analytics_org
      org/{id}/users            → get_analytics_org_users
      timeseries                → get_analytics_timeseries
      funnel                    → get_analytics_funnel
    """
    parts = [p for p in sub_path.strip('/').split('/') if p]

    # GET /crm-analytics/overview
    if parts == ['overview']:
        return crm_service.get_analytics_overview(db_session)

    # GET /crm-analytics/timeseries
    if parts == ['timeseries']:
        return crm_service.get_analytics_timeseries(
            db_session,
            organization_id=_int_param(query_params, 'orgId'),
            event_type=query_params.get('eventType'),
            granularity=query_params.get('granularity', 'day'),
            date_from=query_params.get('from'),
            date_to=query_params.get('to'),
        )

    # GET /crm-analytics/funnel?orgId=X&steps=login,transaction_created,reward_claimed
    if parts == ['funnel']:
        org_id = _int_param(query_params, 'orgId')
        if org_id is None:
            raise BadRequestException("orgId is required for funnel endpoint")
        raw_steps = query_params.get('steps', '')
        steps = [s.strip() for s in raw_steps.split(',') if s.strip()] if raw_steps else []
        return crm_service.get_analytics_funnel(db_session, org_id, steps)

    # GET /crm-analytics/org/{id}
    if len(parts) == 2 and parts[0] == 'org':
        org_id = _to_int(parts[1])
        return crm_service.get_analytics_org(db_session, org_id)

    # GET /crm-analytics/org/{id}/users
    if len(parts) == 3 and parts[0] == 'org' and parts[2] == 'users':
        org_id = _to_int(parts[1])
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 25))
        return crm_service.get_analytics_org_users(db_session, org_id, page, page_size)

    raise NotFoundException(f"Analytics sub-path not found: {sub_path}")


# ─── Segments (stubs — BE2 fills in Sprint 2) ────────────────────────────────

def _dispatch_segments(resource_id, sub_path, method, db_session, data, query_params):
    raise NotFoundException(
        f"crm-segments sub-route pending BE2 Sprint 2: {method} /{sub_path}"
    )


# ─── Templates (stubs — BE2 fills in Sprint 3) ───────────────────────────────

def _dispatch_templates(resource_id, sub_path, method, db_session, data, query_params):
    raise NotFoundException(
        f"crm-templates sub-route pending BE2 Sprint 3: {method} /{sub_path}"
    )


# ─── Campaigns (stubs — BE2 fills in Sprint 4) ───────────────────────────────

def _dispatch_campaigns(resource_id, sub_path, method, db_session, data, query_params):
    raise NotFoundException(
        f"crm-campaigns sub-route pending BE2 Sprint 4: {method} /{sub_path}"
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _int_param(params: dict, key: str):
    """Return params[key] as int, or None if missing/invalid."""
    val = params.get(key)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BadRequestException(f"Expected integer path segment, got: {value!r}")
