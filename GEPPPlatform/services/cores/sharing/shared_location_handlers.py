"""
Shared Location API handlers — routes for /api/shared-locations.

Source-owner endpoints operate on the actor's org as the SOURCE; incoming/reject
operate on the actor's org as the TARGET. The acting org + user come from the JWT
(current_user), so callers never pass an organization id.
"""

import json
from typing import Any, Dict

from .shared_location_service import SharedLocationService
from ....libs.exceptions import (
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
)


def _int_or_none(value: Any):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shared_location_routes(event: Dict[str, Any], context: Any, **params) -> Any:
    """Route handler for /api/shared-locations/* endpoints."""
    raw_path = event.get("rawPath", "") or ""
    path = raw_path.split('?')[0]
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')

    if method == 'OPTIONS':
        return {'message': 'CORS preflight'}

    db_session = params.get('db_session')
    current_user = params.get('current_user', {}) or {}
    user_id = current_user.get('user_id')
    organization_id = current_user.get('organization_id')

    if not user_id:
        raise UnauthorizedException('User ID not found in request')
    if not organization_id:
        raise BadRequestException('No organization context for this user')

    service = SharedLocationService(db_session)

    # Path segments after the base, e.g. ['123'] or ['123', 'reject'] or ['incoming'].
    base = '/api/shared-locations'
    idx = path.find(base)
    tail = path[idx + len(base):].strip('/') if idx != -1 else ''
    segments = [s for s in tail.split('/') if s]

    query = event.get('queryStringParameters') or {}
    body = {}
    if method in ('POST', 'PUT', 'PATCH'):
        try:
            body = json.loads(event.get('body') or '{}')
        except (ValueError, TypeError):
            body = {}

    # ── collection routes ─────────────────────────────────────────────────────
    if not segments:
        if method == 'GET':
            src_loc_id = _int_or_none(query.get('source_user_location_id'))
            if src_loc_id is None:
                raise BadRequestException('source_user_location_id query parameter is required')
            return service.list_shares(organization_id, src_loc_id, user_id)
        if method == 'POST':
            src_loc_id = _int_or_none(body.get('source_user_location_id'))
            if src_loc_id is None:
                raise BadRequestException('source_user_location_id is required')
            return service.create_share(organization_id, src_loc_id, user_id, body)
        raise NotFoundException('Shared-location endpoint not found')

    # ── /incoming ─────────────────────────────────────────────────────────────
    if segments[0] == 'incoming' and method == 'GET':
        return service.list_incoming(organization_id, user_id)

    # ── item routes: /{id} and /{id}/reject ───────────────────────────────────
    share_id = _int_or_none(segments[0])
    if share_id is None:
        raise NotFoundException('Shared-location endpoint not found')

    if len(segments) >= 2 and segments[1] == 'reject':
        if method == 'POST':
            return service.reject_share(share_id, organization_id, user_id)
        raise NotFoundException('Shared-location endpoint not found')

    if len(segments) >= 2 and segments[1] == 'place':
        if method == 'POST':
            parent_node_id = _int_or_none(body.get('parent_node_id'))
            if parent_node_id is None:
                raise BadRequestException('parent_node_id is required')
            return service.place_share(share_id, organization_id, user_id, parent_node_id)
        raise NotFoundException('Shared-location endpoint not found')

    if method == 'GET':
        return service.get_share(share_id, organization_id, user_id)
    if method in ('PATCH', 'PUT'):
        return service.update_share(share_id, organization_id, user_id, body)
    if method == 'DELETE':
        return service.delete_share(share_id, organization_id, user_id)

    raise NotFoundException('Shared-location endpoint not found')
