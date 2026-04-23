"""
CRM admin handlers — standard list/get/create/update/delete stubs for each crm_* resource.

Wired into AdminHandlers.handler_map dicts in admin_handlers.py.

Sprint-1 devs fill in bodies; this file establishes the contract and empty response shape.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ....exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────
# Analytics (no CRUD — read-only; routed via sub-path dispatcher)
# ───────────────────────────────────────────────────────────────

def list_crm_analytics(db_session: Session, query_params: dict) -> Dict[str, Any]:
    """Stub — Analytics is accessed via sub-paths (see crm/__init__.py handle_crm_admin_subroute)."""
    return {"items": [], "total": 0, "page": 1, "pageSize": 0}


# ───────────────────────────────────────────────────────────────
# Segments
# ───────────────────────────────────────────────────────────────

def list_crm_segments(db_session: Session, query_params: dict) -> Dict[str, Any]:
    # BE Dev 2 Sprint 2
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}

def get_crm_segment(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotFoundException(f"Segment {resource_id} not found (stub)")

def create_crm_segment(db_session: Session, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 2")

def update_crm_segment(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 2")

def delete_crm_segment(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 2")


# ───────────────────────────────────────────────────────────────
# Email templates
# ───────────────────────────────────────────────────────────────

def list_crm_templates(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}

def get_crm_template(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotFoundException(f"Template {resource_id} not found (stub)")

def create_crm_template(db_session: Session, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 3")

def update_crm_template(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 3")

def delete_crm_template(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 3")


# ───────────────────────────────────────────────────────────────
# Campaigns
# ───────────────────────────────────────────────────────────────

def list_crm_campaigns(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}

def get_crm_campaign(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotFoundException(f"Campaign {resource_id} not found (stub)")

def create_crm_campaign(db_session: Session, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 4")

def update_crm_campaign(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 4")

def delete_crm_campaign(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 4")


# ───────────────────────────────────────────────────────────────
# Email lists
# ───────────────────────────────────────────────────────────────

def list_crm_email_lists(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}

def get_crm_email_list(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotFoundException(f"Email list {resource_id} not found (stub)")

def create_crm_email_list(db_session: Session, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 5")

def update_crm_email_list(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 5")

def delete_crm_email_list(db_session: Session, resource_id: int) -> Dict[str, Any]:
    raise NotImplementedError("BE Dev 2: Sprint 5")


# ───────────────────────────────────────────────────────────────
# Per-user + per-org profiles (read-only views)
# ───────────────────────────────────────────────────────────────

def list_crm_user_profiles(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}

def list_crm_org_profiles(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}


# ───────────────────────────────────────────────────────────────
# Deliveries — read-only list per campaign (sub-route), but expose flat list for admin
# ───────────────────────────────────────────────────────────────

def list_crm_deliveries(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}


# ───────────────────────────────────────────────────────────────
# Unsubscribes (read-only admin view)
# ───────────────────────────────────────────────────────────────

def list_crm_unsubscribes(db_session: Session, query_params: dict) -> Dict[str, Any]:
    return {"items": [], "total": 0, "page": 1, "pageSize": 25}
