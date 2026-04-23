"""
POST /api/crm/events — client-side event ingestion.

Authenticated via user JWT (same token used by gepp-business-v2 frontend).
Server stamps organization_id + user_location_id from the token — client cannot spoof them.
"""

import logging
from typing import Any, Dict

from ...exceptions import BadRequestException
from ..admin.crm.crm_service import emit_event

logger = logging.getLogger(__name__)

# Client-allowed event types only (whitelist to prevent spam).
# Server-side events (auth, transaction, reward, etc.) are emitted directly from handlers
# and must NOT be accepted via this endpoint.
CLIENT_ALLOWED_EVENT_TYPES = {
    'page_view',
    'feature_click',
    'export_clicked',
    'qr_scanner_opened',
    'dashboard_widget_clicked',
    'report_downloaded',
    'help_opened',
}

CLIENT_ALLOWED_CATEGORIES = {'page', 'system'}


def handle_client_event(data: dict, current_user: dict, request_meta: dict, db_session) -> Dict[str, Any]:
    """
    Entry point from app.py for POST /api/crm/events.

    Body:
      {
        "eventType": "page_view",
        "eventCategory": "page",
        "properties": {"path": "/dashboard", "referrer": "..."}
      }
    """
    if not isinstance(data, dict):
        raise BadRequestException("Body must be a JSON object")

    event_type = (data.get('eventType') or '').strip()
    event_category = (data.get('eventCategory') or '').strip()

    if event_type not in CLIENT_ALLOWED_EVENT_TYPES:
        raise BadRequestException(f"Event type '{event_type}' not allowed from client")
    if event_category not in CLIENT_ALLOWED_CATEGORIES:
        raise BadRequestException(f"Event category '{event_category}' not allowed from client")

    evt = emit_event(
        db_session,
        event_type=event_type,
        event_category=event_category,
        organization_id=current_user.get('organization_id'),
        user_location_id=current_user.get('user_id'),
        properties=data.get('properties') or {},
        event_source='client',
        session_id=request_meta.get('session_id'),
        ip_address=request_meta.get('ip_address'),
        user_agent=request_meta.get('user_agent'),
        commit=True,
    )

    return {
        "eventId": evt.id if evt else None,
        "accepted": bool(evt),
    }
