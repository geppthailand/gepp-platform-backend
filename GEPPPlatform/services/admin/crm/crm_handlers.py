"""
CRM admin handlers — standard list/get/create/update/delete stubs for each crm_* resource.

Wired into AdminHandlers.handler_map dicts in admin_handlers.py.

Sprint-1 devs fill in bodies; this file establishes the contract and empty response shape.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import NotFoundException, BadRequestException
from ....exceptions import APIException as _APIException

logger = logging.getLogger(__name__)


def _resolve_email_list_scope(current_user: Optional[dict]) -> Optional[int]:
    """
    Return the organization_id constraint for email-list operations, or raise.

    Rules:
      - super-admin / gepp-admin  → None (no restriction — see all orgs)
      - user with organization_id → that org_id (restricted to own org)
      - anyone else               → raise 403
    """
    current_user = current_user or {}
    admin_role = (current_user.get('admin_role') or
                  current_user.get('platform_role') or '').strip()

    if admin_role in ('super-admin', 'gepp-admin'):
        return None  # full access

    org_id = current_user.get('organization_id')
    if org_id:
        try:
            return int(org_id)
        except (TypeError, ValueError):
            pass

    raise _APIException("Forbidden: no organization scope for email list access", status_code=403)


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
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    name_filter = (query_params.get('name') or '').strip()
    scope_filter = (query_params.get('scope') or '').strip()
    org_filter = query_params.get('organizationId')

    where_clauses = ["deleted_date IS NULL", "is_current = TRUE"]
    params: Dict[str, Any] = {}
    if name_filter:
        where_clauses.append("name ILIKE :name_q")
        params['name_q'] = f"%{name_filter}%"
    if scope_filter in ('user', 'organization'):
        where_clauses.append("scope = :scope")
        params['scope'] = scope_filter
    if org_filter:
        try:
            params['org_id'] = int(org_filter)
            where_clauses.append("(organization_id = :org_id OR organization_id IS NULL)")
        except (TypeError, ValueError):
            pass

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    count_row = db_session.execute(
        text(f"SELECT COUNT(*) FROM crm_segments WHERE {where_sql}"), params
    ).scalar()
    total = int(count_row or 0)

    rows = db_session.execute(
        text(f"""
            SELECT id, name, description, scope, version, member_count,
                   organization_id, is_current, last_evaluated_at,
                   created_date, updated_date
            FROM crm_segments
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, 'limit': page_size, 'offset': offset},
    ).fetchall()

    items = [
        {
            'id': r[0],
            'name': r[1],
            'description': r[2],
            'scope': r[3],
            'version': r[4],
            'memberCount': int(r[5] or 0),
            'organizationId': r[6],
            'isCurrent': r[7],
            'lastEvaluatedAt': r[8].isoformat() if r[8] else None,
            'createdDate': r[9].isoformat() if r[9] else None,
            'updatedDate': r[10].isoformat() if r[10] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_crm_segment(db_session: Session, resource_id: int) -> Dict[str, Any]:
    row = db_session.execute(
        text("""
            SELECT id, name, description, scope, rules, version, member_count,
                   organization_id, is_current, parent_segment_id,
                   last_evaluated_at, created_date, updated_date
            FROM crm_segments
            WHERE id = :id AND deleted_date IS NULL
        """),
        {'id': resource_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Segment {resource_id} not found")

    return {
        'id': row[0],
        'name': row[1],
        'description': row[2],
        'scope': row[3],
        'rules': row[4],
        'version': row[5],
        'memberCount': int(row[6] or 0),
        'organizationId': row[7],
        'isCurrent': row[8],
        'parentSegmentId': row[9],
        'lastEvaluatedAt': row[10].isoformat() if row[10] else None,
        'createdDate': row[11].isoformat() if row[11] else None,
        'updatedDate': row[12].isoformat() if row[12] else None,
    }


def create_crm_segment(db_session: Session, data: dict) -> Dict[str, Any]:
    from ....models.crm import CrmSegment
    from .segment_evaluator import compile_rules

    name = (data.get('name') or '').strip()
    if not name:
        raise BadRequestException("name is required")

    scope = data.get('scope', 'user')
    if scope not in ('user', 'organization'):
        raise BadRequestException("scope must be 'user' or 'organization'")

    rules = data.get('rules')
    if not rules:
        raise BadRequestException("rules is required")

    # Validate rules compile without error
    compile_rules(rules, scope)

    seg = CrmSegment(
        name=name,
        description=data.get('description'),
        scope=scope,
        rules=rules,
        organization_id=data.get('organizationId') or data.get('organization_id'),
        version=1,
        is_current=True,
        member_count=0,
    )
    db_session.add(seg)
    db_session.flush()
    db_session.commit()
    return get_crm_segment(db_session, seg.id)


def update_crm_segment(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    """
    Creating a new version is our update strategy:
    mark old row is_current=False, insert new row with parent_segment_id=old_id.
    """
    from ....models.crm import CrmSegment
    from .segment_evaluator import compile_rules
    import json

    old = db_session.execute(
        text("SELECT id, scope, version, organization_id FROM crm_segments WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    ).fetchone()
    if not old:
        raise NotFoundException(f"Segment {resource_id} not found")

    scope = data.get('scope', old[1])
    rules = data.get('rules')
    if rules:
        compile_rules(rules, scope)

    # Mark old as non-current
    db_session.execute(
        text("UPDATE crm_segments SET is_current = FALSE, updated_date = NOW() WHERE id = :id"),
        {'id': resource_id},
    )

    new_seg = CrmSegment(
        name=data.get('name') or db_session.execute(
            text("SELECT name FROM crm_segments WHERE id = :id"), {'id': resource_id}
        ).scalar(),
        description=data.get('description'),
        scope=scope,
        rules=rules if rules else db_session.execute(
            text("SELECT rules FROM crm_segments WHERE id = :id"), {'id': resource_id}
        ).scalar(),
        organization_id=data.get('organizationId') or old[3],
        version=old[2] + 1,
        parent_segment_id=resource_id,
        is_current=True,
        member_count=0,
    )
    db_session.add(new_seg)
    db_session.flush()
    db_session.commit()
    return get_crm_segment(db_session, new_seg.id)


def delete_crm_segment(db_session: Session, resource_id: int) -> Dict[str, Any]:
    result = db_session.execute(
        text("UPDATE crm_segments SET deleted_date = NOW(), is_current = FALSE WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    )
    db_session.commit()
    if result.rowcount == 0:
        raise NotFoundException(f"Segment {resource_id} not found")
    return {"id": resource_id, "deleted": True}


# ───────────────────────────────────────────────────────────────
# Email templates
# ───────────────────────────────────────────────────────────────

def list_crm_templates(db_session: Session, query_params: dict) -> Dict[str, Any]:
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25
    name_filter = (query_params.get('name') or '').strip()
    generated_by = (query_params.get('generatedBy') or '').strip()
    include_all_versions = (query_params.get('includeAllVersions') or '').lower() in ('1', 'true', 'yes')

    where = ["deleted_date IS NULL"]
    params: Dict[str, Any] = {}
    if not include_all_versions:
        # Default: show only the current (latest) version of each template family.
        # Rows without is_current column (pre-migration) default TRUE per migration.
        where.append("COALESCE(is_current, TRUE) = TRUE")
    if name_filter:
        where.append("(name ILIKE :name_q OR subject ILIKE :name_q)")
        params['name_q'] = f"%{name_filter}%"
    if generated_by in ('human', 'ai'):
        where.append("generated_by = :gen")
        params['gen'] = generated_by
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    total = int(db_session.execute(
        text(f"SELECT COUNT(*) FROM crm_email_templates WHERE {where_sql}"), params
    ).scalar() or 0)
    rows = db_session.execute(
        text(f"""
            SELECT id, name, subject, preview_text, generated_by, version,
                   organization_id, created_date, updated_date,
                   COALESCE(is_current, TRUE) AS is_current,
                   parent_template_id
            FROM crm_email_templates
            WHERE {where_sql}
            ORDER BY id DESC LIMIT :lim OFFSET :off
        """),
        {**params, 'lim': page_size, 'off': offset},
    ).fetchall()
    items = [
        {
            'id': r[0], 'name': r[1], 'subject': r[2], 'previewText': r[3],
            'generatedBy': r[4], 'version': r[5], 'organizationId': r[6],
            'createdDate': r[7].isoformat() if r[7] else None,
            'updatedDate': r[8].isoformat() if r[8] else None,
            'isCurrent': r[9],
            'parentTemplateId': r[10],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_crm_template(db_session: Session, resource_id: int) -> Dict[str, Any]:
    row = db_session.execute(
        text("""
            SELECT id, name, subject, preview_text, body_html, body_plain,
                   variables, generated_by, ai_prompt, version,
                   organization_id, created_date, updated_date,
                   COALESCE(is_current, TRUE) AS is_current,
                   parent_template_id,
                   ai_model, ai_token_usage
            FROM crm_email_templates
            WHERE id = :id AND deleted_date IS NULL
        """),
        {'id': resource_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Template {resource_id} not found")
    return {
        'id': row[0], 'name': row[1], 'subject': row[2], 'previewText': row[3],
        'bodyHtml': row[4], 'bodyPlain': row[5], 'variables': row[6] or [],
        'generatedBy': row[7], 'aiPrompt': row[8], 'version': row[9],
        'organizationId': row[10],
        'createdDate': row[11].isoformat() if row[11] else None,
        'updatedDate': row[12].isoformat() if row[12] else None,
        'isCurrent': row[13],
        'parentTemplateId': row[14],
        'aiModel': row[15],
        'aiTokenUsage': row[16],
    }


def create_crm_template(db_session: Session, data: dict) -> Dict[str, Any]:
    from ....models.crm import CrmEmailTemplate
    name = (data.get('name') or '').strip()
    subject = (data.get('subject') or '').strip()
    body_html = (data.get('bodyHtml') or '').strip()
    if not name:
        raise BadRequestException("name is required")
    if not subject:
        raise BadRequestException("subject is required")
    if not body_html:
        raise BadRequestException("bodyHtml is required")
    tpl = CrmEmailTemplate(
        name=name,
        subject=subject,
        preview_text=data.get('previewText'),
        body_html=body_html,
        body_plain=data.get('bodyPlain'),
        variables=data.get('variables') or [],
        generated_by=data.get('generatedBy', 'human'),
        ai_prompt=data.get('aiPrompt'),
        ai_model=data.get('aiModel'),
        ai_token_usage=data.get('aiTokenUsage'),
        organization_id=data.get('organizationId'),
        version=1,
    )
    db_session.add(tpl)
    db_session.flush()
    db_session.commit()
    return get_crm_template(db_session, tpl.id)


def update_crm_template(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    """
    Template versioning strategy (mirrors update_crm_segment):
      1. Load existing row — raise NotFoundException if missing.
      2. Mark old row is_current=FALSE, updated_date=NOW().
      3. Insert new row with version=old.version+1, parent_template_id=old.id, is_current=TRUE.
      4. Commit and return the new row via get_crm_template.

    Fields not supplied in `data` are inherited from the old row.
    """
    from ....models.crm import CrmEmailTemplate

    old_row = db_session.execute(
        text("""
            SELECT id, name, subject, preview_text, body_html, body_plain,
                   variables, generated_by, ai_prompt, ai_model, ai_token_usage,
                   version, organization_id
            FROM crm_email_templates
            WHERE id = :id AND deleted_date IS NULL
        """),
        {'id': resource_id},
    ).fetchone()
    if not old_row:
        raise NotFoundException(f"Template {resource_id} not found")

    (old_id, old_name, old_subject, old_preview, old_html, old_plain,
     old_vars, old_gen_by, old_prompt, old_model, old_token_usage,
     old_version, old_org_id) = old_row

    # No real changes? Return current row unchanged (early exit keeps versions clean).
    has_changes = any(k in data for k in (
        'name', 'subject', 'previewText', 'bodyHtml', 'bodyPlain',
        'variables', 'aiPrompt', 'aiModel', 'aiTokenUsage',
    ))
    if not has_changes:
        return get_crm_template(db_session, resource_id)

    # Step 1 — retire old row
    db_session.execute(
        text("UPDATE crm_email_templates SET is_current = FALSE, updated_date = NOW() WHERE id = :id"),
        {'id': resource_id},
    )

    # Step 2 — create new version row
    new_tpl = CrmEmailTemplate(
        name=data.get('name', old_name),
        subject=data.get('subject', old_subject),
        preview_text=data.get('previewText', old_preview),
        body_html=data.get('bodyHtml', old_html),
        body_plain=data.get('bodyPlain', old_plain),
        variables=data.get('variables', old_vars) or [],
        generated_by=old_gen_by,                          # provenance doesn't change on edit
        ai_prompt=data.get('aiPrompt', old_prompt),
        ai_model=data.get('aiModel', old_model),
        ai_token_usage=data.get('aiTokenUsage', old_token_usage),
        organization_id=data.get('organizationId', old_org_id),
        version=old_version + 1,
        parent_template_id=resource_id,
        is_current=True,
    )
    db_session.add(new_tpl)
    db_session.flush()
    db_session.commit()
    return get_crm_template(db_session, new_tpl.id)


def delete_crm_template(db_session: Session, resource_id: int) -> Dict[str, Any]:
    result = db_session.execute(
        text("UPDATE crm_email_templates SET deleted_date = NOW() WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    )
    db_session.commit()
    if result.rowcount == 0:
        raise NotFoundException(f"Template {resource_id} not found")
    return {"id": resource_id, "deleted": True}


# ───────────────────────────────────────────────────────────────
# Campaigns
# ───────────────────────────────────────────────────────────────

def list_crm_campaigns(db_session: Session, query_params: dict) -> Dict[str, Any]:
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25
    status_filter = (query_params.get('status') or '').strip()
    name_filter = (query_params.get('name') or '').strip()
    template_id_filter = query_params.get('templateId') or query_params.get('template_id')
    where = ["c.deleted_date IS NULL"]
    params: Dict[str, Any] = {}
    if name_filter:
        where.append("c.name ILIKE :name_q")
        params['name_q'] = f"%{name_filter}%"
    if status_filter:
        where.append("c.status = :status")
        params['status'] = status_filter
    if template_id_filter:
        try:
            params['template_id'] = int(template_id_filter)
            where.append("c.template_id = :template_id")
        except (TypeError, ValueError):
            pass
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    total = int(db_session.execute(
        text(f"SELECT COUNT(*) FROM crm_campaigns c WHERE {where_sql}"), params
    ).scalar() or 0)
    rows = db_session.execute(
        text(f"""
            SELECT c.id, c.name, c.campaign_type, c.status, c.segment_id,
                   c.template_id, t.name AS template_name,
                   c.scheduled_at, c.started_at, c.ended_at,
                   c.organization_id, c.created_date, c.metrics_cache
            FROM crm_campaigns c
            LEFT JOIN crm_email_templates t ON t.id = c.template_id
            WHERE {where_sql}
            ORDER BY c.id DESC LIMIT :lim OFFSET :off
        """),
        {**params, 'lim': page_size, 'off': offset},
    ).fetchall()
    items = [
        {
            'id': r[0], 'name': r[1], 'campaignType': r[2], 'status': r[3],
            'segmentId': r[4], 'templateId': r[5], 'templateName': r[6],
            'scheduledAt': r[7].isoformat() if r[7] else None,
            'startedAt': r[8].isoformat() if r[8] else None,
            'endedAt': r[9].isoformat() if r[9] else None,
            'organizationId': r[10],
            'createdDate': r[11].isoformat() if r[11] else None,
            'metricsCache': r[12] or {},
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_crm_campaign(db_session: Session, resource_id: int) -> Dict[str, Any]:
    row = db_session.execute(
        text("""
            SELECT c.id, c.name, c.description, c.campaign_type, c.trigger_event,
                   c.trigger_config, c.segment_id, c.template_id, c.status,
                   c.scheduled_at, c.started_at, c.ended_at,
                   c.send_from_name, c.send_from_email, c.reply_to, c.cc_list_id,
                   c.organization_id, c.created_date, c.metrics_cache
            FROM crm_campaigns c
            WHERE c.id = :id AND c.deleted_date IS NULL
        """),
        {'id': resource_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Campaign {resource_id} not found")
    return {
        'id': row[0], 'name': row[1], 'description': row[2],
        'campaignType': row[3], 'triggerEvent': row[4], 'triggerConfig': row[5] or {},
        'segmentId': row[6], 'templateId': row[7], 'status': row[8],
        'scheduledAt': row[9].isoformat() if row[9] else None,
        'startedAt': row[10].isoformat() if row[10] else None,
        'endedAt': row[11].isoformat() if row[11] else None,
        'sendFromName': row[12], 'sendFromEmail': row[13], 'replyTo': row[14],
        'ccListId': row[15], 'organizationId': row[16],
        'createdDate': row[17].isoformat() if row[17] else None,
        'metricsCache': row[18] or {},
    }


def create_crm_campaign(db_session: Session, data: dict) -> Dict[str, Any]:
    from ....models.crm import CrmCampaign
    name = (data.get('name') or '').strip()
    template_id = data.get('templateId') or data.get('template_id')
    campaign_type = data.get('campaignType', 'blast')
    if not name:
        raise BadRequestException("name is required")
    if not template_id:
        raise BadRequestException("templateId is required")
    if campaign_type not in ('trigger', 'blast'):
        raise BadRequestException("campaignType must be 'trigger' or 'blast'")
    camp = CrmCampaign(
        name=name,
        description=data.get('description'),
        campaign_type=campaign_type,
        trigger_event=data.get('triggerEvent'),
        trigger_config=data.get('triggerConfig') or {},
        segment_id=data.get('segmentId'),
        template_id=template_id,
        status='draft',
        scheduled_at=data.get('scheduledAt'),
        send_from_name=data.get('sendFromName'),
        send_from_email=data.get('sendFromEmail'),
        reply_to=data.get('replyTo'),
        cc_list_id=data.get('ccListId'),
        organization_id=data.get('organizationId'),
    )
    db_session.add(camp)
    db_session.flush()
    db_session.commit()
    return get_crm_campaign(db_session, camp.id)


def update_crm_campaign(db_session: Session, resource_id: int, data: dict) -> Dict[str, Any]:
    existing = db_session.execute(
        text("SELECT id FROM crm_campaigns WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    ).fetchone()
    if not existing:
        raise NotFoundException(f"Campaign {resource_id} not found")
    col_map = [
        ('name', 'name'), ('description', 'description'), ('segment_id', 'segmentId'),
        ('template_id', 'templateId'), ('trigger_event', 'triggerEvent'),
        ('trigger_config', 'triggerConfig'), ('scheduled_at', 'scheduledAt'),
        ('send_from_name', 'sendFromName'), ('send_from_email', 'sendFromEmail'),
        ('reply_to', 'replyTo'), ('cc_list_id', 'ccListId'),
    ]
    updates = []
    params: Dict[str, Any] = {'id': resource_id}
    for col, key in col_map:
        if key in data:
            updates.append(f"{col} = :{col}")
            params[col] = data[key]
    if not updates:
        return get_crm_campaign(db_session, resource_id)
    updates.append("updated_date = NOW()")
    db_session.execute(
        text(f"UPDATE crm_campaigns SET {', '.join(updates)} WHERE id = :id"), params
    )
    db_session.commit()
    return get_crm_campaign(db_session, resource_id)


def delete_crm_campaign(db_session: Session, resource_id: int) -> Dict[str, Any]:
    result = db_session.execute(
        text("UPDATE crm_campaigns SET deleted_date = NOW(), status = 'archived' WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    )
    db_session.commit()
    if result.rowcount == 0:
        raise NotFoundException(f"Campaign {resource_id} not found")
    return {"id": resource_id, "deleted": True}


# ───────────────────────────────────────────────────────────────
# Email lists
# ───────────────────────────────────────────────────────────────

def list_crm_email_lists(db_session: Session, query_params: dict, current_user: Optional[dict] = None) -> Dict[str, Any]:
    _scope_org_id = _resolve_email_list_scope(current_user)
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25
    name_filter = (query_params.get('name') or '').strip()
    # Scope overrides any org filter from query params for non-admins
    if _scope_org_id is not None:
        org_filter_val: Optional[int] = _scope_org_id
    else:
        raw_org = query_params.get('organizationId')
        try:
            org_filter_val = int(raw_org) if raw_org else None
        except (TypeError, ValueError):
            org_filter_val = None
    where = ["deleted_date IS NULL"]
    params: Dict[str, Any] = {}
    if name_filter:
        where.append("name ILIKE :name_q")
        params['name_q'] = f"%{name_filter}%"
    if org_filter_val is not None:
        params['org_id'] = org_filter_val
        where.append("organization_id = :org_id")
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size
    total = int(db_session.execute(
        text(f"SELECT COUNT(*) FROM crm_email_lists WHERE {where_sql}"), params
    ).scalar() or 0)
    rows = db_session.execute(
        text(f"""
            SELECT id, name, description, organization_id, emails,
                   created_date, updated_date
            FROM crm_email_lists WHERE {where_sql}
            ORDER BY id DESC LIMIT :lim OFFSET :off
        """),
        {**params, 'lim': page_size, 'off': offset},
    ).fetchall()
    items = [
        {
            'id': r[0], 'name': r[1], 'description': r[2],
            'organizationId': r[3],
            'emails': r[4] or [],
            'emailCount': len(r[4] or []),
            'createdDate': r[5].isoformat() if r[5] else None,
            'updatedDate': r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_crm_email_list(db_session: Session, resource_id: int, current_user: Optional[dict] = None) -> Dict[str, Any]:
    _scope_org_id = _resolve_email_list_scope(current_user)
    row = db_session.execute(
        text("""
            SELECT id, name, description, organization_id, emails, created_date, updated_date
            FROM crm_email_lists WHERE id = :id AND deleted_date IS NULL
        """),
        {'id': resource_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Email list {resource_id} not found")
    # Enforce org scoping: non-admins may only read their own org's lists
    if _scope_org_id is not None and row[3] != _scope_org_id:
        raise NotFoundException(f"Email list {resource_id} not found")
    return {
        'id': row[0], 'name': row[1], 'description': row[2],
        'organizationId': row[3], 'emails': row[4] or [],
        'emailCount': len(row[4] or []),
        'createdDate': row[5].isoformat() if row[5] else None,
        'updatedDate': row[6].isoformat() if row[6] else None,
    }


def create_crm_email_list(db_session: Session, data: dict, current_user: Optional[dict] = None) -> Dict[str, Any]:
    from ....models.crm import CrmEmailList
    _scope_org_id = _resolve_email_list_scope(current_user)
    name = (data.get('name') or '').strip()
    org_id = data.get('organizationId') or data.get('organization_id')
    if not name:
        raise BadRequestException("name is required")
    if not org_id:
        raise BadRequestException("organizationId is required")
    # Enforce org scoping: non-admins may only create lists for their own org
    try:
        int_org_id = int(org_id)
    except (TypeError, ValueError):
        raise BadRequestException("organizationId must be an integer")
    if _scope_org_id is not None and int_org_id != _scope_org_id:
        raise _APIException("Forbidden: cannot create email list for another organization", status_code=403)
    emails = data.get('emails') or []
    if not isinstance(emails, list):
        raise BadRequestException("emails must be an array")
    lst = CrmEmailList(
        name=name,
        description=data.get('description'),
        organization_id=int_org_id,
        emails=emails,
    )
    db_session.add(lst)
    db_session.flush()
    db_session.commit()
    return get_crm_email_list(db_session, lst.id, current_user=current_user)


def update_crm_email_list(db_session: Session, resource_id: int, data: dict, current_user: Optional[dict] = None) -> Dict[str, Any]:
    _scope_org_id = _resolve_email_list_scope(current_user)
    existing = db_session.execute(
        text("SELECT id, organization_id FROM crm_email_lists WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    ).fetchone()
    if not existing:
        raise NotFoundException(f"Email list {resource_id} not found")
    # Enforce org scoping: non-admins may only update their own org's lists
    if _scope_org_id is not None and existing[1] != _scope_org_id:
        raise NotFoundException(f"Email list {resource_id} not found")
    updates = []
    params: Dict[str, Any] = {'id': resource_id}
    for col, key in [('name', 'name'), ('description', 'description'), ('emails', 'emails')]:
        if key in data:
            updates.append(f"{col} = :{col}")
            params[col] = data[key]
    if not updates:
        return get_crm_email_list(db_session, resource_id, current_user=current_user)
    updates.append("updated_date = NOW()")
    db_session.execute(
        text(f"UPDATE crm_email_lists SET {', '.join(updates)} WHERE id = :id"), params
    )
    db_session.commit()
    return get_crm_email_list(db_session, resource_id, current_user=current_user)


def delete_crm_email_list(db_session: Session, resource_id: int, current_user: Optional[dict] = None) -> Dict[str, Any]:
    _scope_org_id = _resolve_email_list_scope(current_user)
    # Enforce org scoping: fetch first to check ownership
    existing = db_session.execute(
        text("SELECT id, organization_id FROM crm_email_lists WHERE id = :id AND deleted_date IS NULL"),
        {'id': resource_id},
    ).fetchone()
    if not existing:
        raise NotFoundException(f"Email list {resource_id} not found")
    if _scope_org_id is not None and existing[1] != _scope_org_id:
        raise NotFoundException(f"Email list {resource_id} not found")
    db_session.execute(
        text("UPDATE crm_email_lists SET deleted_date = NOW() WHERE id = :id"),
        {'id': resource_id},
    )
    db_session.commit()
    return {"id": resource_id, "deleted": True}


# ───────────────────────────────────────────────────────────────
# Per-user + per-org profiles (read-only views)
# ───────────────────────────────────────────────────────────────

def list_crm_user_profiles(db_session: Session, query_params: dict) -> Dict[str, Any]:
    """
    List one row per V3 user (user_locations.is_user=true, platform=GEPP_BUSINESS_WEB),
    LEFT JOIN crm_user_profiles for engagement metrics.

    Mirrors list_crm_org_profiles: every user always appears with sensible defaults
    (zero counts, 'dormant' tier) until the nightly profile_refresher rollup runs.

    Filters:
      - name        ILIKE on first/last name + email
      - email       ILIKE on email (alias of name when only email-shaped value provided)
      - tier        exact match on activity_tier ('active' | 'at_risk' | 'dormant' | 'lead')
      - orgId       exact match on organization_id
      - minScore    engagement_score >= value (numeric)

    Sort:
      - sort=engagementScore (default), lastLogin, name, transactions, orgId
      - order=asc | desc (default desc)
    """
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    name_filter  = (query_params.get('name') or '').strip()
    email_filter = (query_params.get('email') or '').strip()
    tier_filter  = (query_params.get('activityTier') or query_params.get('tier') or '').strip()
    org_filter   = query_params.get('organizationId') or query_params.get('orgId')
    min_score    = query_params.get('minScore')

    where_clauses = [
        "ul.is_user = TRUE",
        "ul.is_active = TRUE",
        "ul.platform = 'GEPP_BUSINESS_WEB'",
    ]
    params: Dict[str, Any] = {}
    if name_filter:
        where_clauses.append(
            "(ul.first_name ILIKE :name_q OR ul.last_name ILIKE :name_q OR ul.email ILIKE :name_q)"
        )
        params['name_q'] = f"%{name_filter}%"
    if email_filter:
        where_clauses.append("ul.email ILIKE :email_q")
        params['email_q'] = f"%{email_filter}%"
    if tier_filter:
        where_clauses.append("COALESCE(p.activity_tier, 'dormant') = :tier")
        params['tier'] = tier_filter
    if org_filter:
        try:
            params['org_id'] = int(org_filter)
            where_clauses.append("ul.organization_id = :org_id")
        except (TypeError, ValueError):
            pass
    if min_score is not None and min_score != '':
        try:
            params['min_score'] = float(min_score)
            where_clauses.append("COALESCE(p.engagement_score, 0) >= :min_score")
        except (TypeError, ValueError):
            pass

    where_sql = " AND ".join(where_clauses)

    # Sort whitelist — ORDER BY is interpolated, never user-supplied SQL.
    sort_map = {
        'engagementScore':  "COALESCE(p.engagement_score, 0)",
        'lastLogin':        "p.last_login_at",
        'name':             "ul.first_name",
        'transactions':     "COALESCE(p.transaction_count_30d, 0)",
        'orgId':            "ul.organization_id",
        'id':               "ul.id",
    }
    sort_key = (query_params.get('sort') or 'engagementScore').strip()
    sort_col = sort_map.get(sort_key, sort_map['engagementScore'])
    order = (query_params.get('order') or 'desc').strip().lower()
    if order not in ('asc', 'desc'):
        order = 'desc'
    nulls = 'NULLS LAST' if order == 'desc' else 'NULLS FIRST'

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM user_locations ul
        LEFT JOIN crm_user_profiles p ON p.user_location_id = ul.id
        WHERE {where_sql}
    """)
    total = int(db_session.execute(count_sql, params).scalar() or 0)

    offset = (page - 1) * page_size
    rows_sql = text(f"""
        SELECT
            ul.id                                   AS user_location_id,
            ul.first_name                            AS first_name,
            ul.last_name                             AS last_name,
            ul.email                                AS email,
            ul.phone                                AS phone,
            ul.organization_id                      AS organization_id,
            o.name                                  AS organization_name,
            COALESCE(p.engagement_score, 0)         AS engagement_score,
            COALESCE(p.activity_tier, 'dormant')    AS activity_tier,
            p.last_login_at                         AS last_login_at,
            p.days_since_last_login                 AS days_since_last_login,
            COALESCE(p.login_count_30d, 0)          AS login_count_30d,
            COALESCE(p.transaction_count_30d, 0)    AS transaction_count_30d,
            COALESCE(p.qr_count_30d, 0)             AS qr_count_30d,
            COALESCE(p.reward_claim_count_30d, 0)   AS reward_claim_count_30d,
            COALESCE(p.iot_readings_count_30d, 0)   AS iot_readings_count_30d,
            COALESCE(p.gri_submission_count_30d, 0) AS gri_submission_count_30d,
            COALESCE(p.traceability_count_30d, 0)   AS traceability_count_30d,
            COALESCE(p.onboarded, FALSE)            AS onboarded,
            p.first_login_at                        AS first_login_at,
            p.last_profile_refresh_at               AS last_profile_refresh_at,
            ul.created_date                         AS created_date
        FROM user_locations ul
        LEFT JOIN crm_user_profiles p ON p.user_location_id = ul.id
        LEFT JOIN organizations o ON o.id = ul.organization_id AND o.deleted_date IS NULL
        WHERE {where_sql}
        ORDER BY {sort_col} {order} {nulls}, ul.id DESC
        LIMIT :limit OFFSET :offset
    """)
    params['limit'] = page_size
    params['offset'] = offset
    result = db_session.execute(rows_sql, params)

    items = [
        {
            'id': row.user_location_id,
            'userLocationId': row.user_location_id,
            'firstName': row.first_name,
            'lastName': row.last_name,
            'name': ' '.join(filter(None, [row.first_name, row.last_name])) or row.email,
            'email': row.email,
            'phone': row.phone,
            'organizationId': row.organization_id,
            'organizationName': row.organization_name,
            'engagementScore': float(row.engagement_score or 0),
            'activityTier': row.activity_tier,
            'lastLoginAt': row.last_login_at,
            'daysSinceLastLogin': row.days_since_last_login,
            'loginCount30d': row.login_count_30d,
            'transactionCount30d': row.transaction_count_30d,
            'qrCount30d': row.qr_count_30d,
            'rewardClaimCount30d': row.reward_claim_count_30d,
            'iotReadingsCount30d': row.iot_readings_count_30d,
            'griSubmissionCount30d': row.gri_submission_count_30d,
            'traceabilityCount30d': row.traceability_count_30d,
            'onboarded': row.onboarded,
            'firstLoginAt': row.first_login_at,
            'lastProfileRefreshAt': row.last_profile_refresh_at,
            'createdDate': row.created_date,
        }
        for row in result
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}

def list_crm_org_profiles(db_session: Session, query_params: dict) -> Dict[str, Any]:
    """
    List one row per organization, LEFT JOIN crm_org_profiles for engagement metrics.

    crm_org_profiles is a nightly-refreshed cache (profile_refresher.py) so it may be empty
    or stale. Joining off `organizations` ensures every org appears with sensible defaults
    (zero counts, 'dormant' tier) until the rollup runs.
    """
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    name_filter = (query_params.get('name') or '').strip()
    tier_filter = (query_params.get('activityTier') or query_params.get('tier') or '').strip()

    where_clauses = ["o.deleted_date IS NULL"]
    params: Dict[str, Any] = {}
    if name_filter:
        where_clauses.append(
            "(o.name ILIKE :name_q OR oi.company_name ILIKE :name_q "
            "OR oi.company_name_en ILIKE :name_q OR oi.company_name_th ILIKE :name_q)"
        )
        params['name_q'] = f"%{name_filter}%"
    if tier_filter:
        where_clauses.append("COALESCE(p.activity_tier, 'dormant') = :tier")
        params['tier'] = tier_filter

    where_sql = " AND ".join(where_clauses)

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM organizations o
        JOIN user_locations ul ON ul.id = o.owner_id AND ul.platform = 'GEPP_BUSINESS_WEB'
        LEFT JOIN organization_info oi ON oi.id = o.organization_info_id
        LEFT JOIN crm_org_profiles p ON p.organization_id = o.id
        WHERE {where_sql}
    """)
    total = int(db_session.execute(count_sql, params).scalar() or 0)

    offset = (page - 1) * page_size
    # Note on JOINs:
    #   - user_locations ul (owner_email): organizations.owner_id → user_locations.id
    #     (mirrors get_analytics_org pattern in crm_service.py).
    #   - subscriptions s + subscription_plans sp (subscription_plan): we LEFT JOIN
    #     active subscriptions and prefer sp.display_name with fallback to sp.name.
    #     A LATERAL subquery picks the most recent active subscription per org so we
    #     never multiply rows when an org has multiple historical subs.
    rows_sql = text(f"""
        SELECT
            o.id AS organization_id,
            o.name AS organization_name,
            COALESCE(oi.company_name, oi.company_name_en, oi.company_name_th, o.name) AS company_name,
            ul.email AS owner_email,
            COALESCE(active_sub.display_name, active_sub.plan_name) AS subscription_plan,
            o.created_date,
            COALESCE(p.active_user_count_30d, 0) AS active_user_count_30d,
            COALESCE(p.total_user_count, 0) AS total_user_count,
            COALESCE(p.active_user_ratio, 0) AS active_user_ratio,
            COALESCE(p.transaction_count_30d, 0) AS transaction_count_30d,
            COALESCE(p.traceability_count_30d, 0) AS traceability_count_30d,
            COALESCE(p.gri_submission_count_30d, 0) AS gri_submission_count_30d,
            COALESCE(active_sub.plan_id, p.subscription_plan_id) AS subscription_plan_id,
            COALESCE(p.subscription_active, FALSE) AS subscription_active,
            p.quota_used_pct,
            COALESCE(p.activity_tier, 'dormant') AS activity_tier,
            p.last_activity_at,
            p.last_profile_refresh_at
        FROM organizations o
        JOIN user_locations ul ON ul.id = o.owner_id AND ul.platform = 'GEPP_BUSINESS_WEB'
        LEFT JOIN organization_info oi ON oi.id = o.organization_info_id
        LEFT JOIN crm_org_profiles p ON p.organization_id = o.id
        LEFT JOIN LATERAL (
            SELECT sp.id AS plan_id, sp.name AS plan_name, sp.display_name
            FROM subscriptions s
            LEFT JOIN subscription_plans sp ON sp.id = s.plan_id
            WHERE s.organization_id = o.id
              AND s.status = 'active'
              AND s.is_active = TRUE
            ORDER BY s.created_date DESC
            LIMIT 1
        ) active_sub ON TRUE
        WHERE {where_sql}
        ORDER BY o.id DESC
        LIMIT :limit OFFSET :offset
    """)
    params['limit'] = page_size
    params['offset'] = offset
    result = db_session.execute(rows_sql, params)
    items = [
        {
            'id': row.organization_id,                    # Refine resource id
            'organizationId': row.organization_id,
            # Frontend expects `name` as the org display name. Keep `organizationName`
            # too for backward compat with any older callers.
            'name': row.organization_name,
            'organizationName': row.organization_name,
            'companyName': row.company_name,
            'ownerEmail': row.owner_email,
            'subscriptionPlan': row.subscription_plan,
            'createdDate': row.created_date,
            'activeUserCount30d': row.active_user_count_30d,
            'totalUserCount': row.total_user_count,
            'activeUserRatio': float(row.active_user_ratio or 0),
            'transactionCount30d': row.transaction_count_30d,
            'traceabilityCount30d': row.traceability_count_30d,
            'griSubmissionCount30d': row.gri_submission_count_30d,
            'subscriptionPlanId': row.subscription_plan_id,
            'subscriptionActive': row.subscription_active,
            'quotaUsedPct': float(row.quota_used_pct) if row.quota_used_pct is not None else None,
            'activityTier': row.activity_tier,
            'lastActivityAt': row.last_activity_at,
            'lastProfileRefreshAt': row.last_profile_refresh_at,
        }
        for row in result
    ]

    return {"items": items, "total": total, "page": page, "pageSize": page_size}


# ───────────────────────────────────────────────────────────────
# Deliveries — read-only list per campaign (sub-route), but expose flat list for admin
# ───────────────────────────────────────────────────────────────

def list_crm_deliveries(db_session: Session, query_params: dict) -> Dict[str, Any]:
    """
    Paginated flat list of crm_campaign_deliveries across all campaigns.

    Filters:
      campaignId         — exact match
      status             — exact match
      recipientEmail     — ILIKE
      organizationId     — exact match
      userLocationId     — exact match (alias: recipientUserId)
      dateFrom/dateTo    — on sent_at (inclusive range)

    Response shape includes: openCount, clickCount, firstClickedAt, bouncedAt.
    ORDER BY sent_at DESC NULLS LAST, id DESC.
    """
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    where_clauses = ["d.id IS NOT NULL"]  # always-true anchor for easy AND chaining
    params: Dict[str, Any] = {}

    campaign_id = query_params.get('campaignId')
    if campaign_id:
        try:
            params['campaign_id'] = int(campaign_id)
            where_clauses.append("d.campaign_id = :campaign_id")
        except (TypeError, ValueError):
            pass

    status_filter = (query_params.get('status') or '').strip()
    if status_filter:
        where_clauses.append("d.status = :status")
        params['status'] = status_filter

    email_filter = (query_params.get('recipientEmail') or '').strip()
    if email_filter:
        where_clauses.append("d.recipient_email ILIKE :email_q")
        params['email_q'] = f"%{email_filter}%"

    org_id = query_params.get('organizationId')
    if org_id:
        try:
            params['org_id'] = int(org_id)
            where_clauses.append("d.organization_id = :org_id")
        except (TypeError, ValueError):
            pass

    # Sprint 4 — filter by userLocationId (alias recipientUserId)
    user_location_id_filter = (
        query_params.get('userLocationId') or query_params.get('recipientUserId') or ''
    ).strip()
    if user_location_id_filter:
        try:
            params['user_location_id'] = int(user_location_id_filter)
            where_clauses.append("d.user_location_id = :user_location_id")
        except (TypeError, ValueError):
            pass

    date_from = (query_params.get('dateFrom') or '').strip()
    if date_from:
        where_clauses.append("d.sent_at >= :date_from")
        params['date_from'] = date_from

    date_to = (query_params.get('dateTo') or '').strip()
    if date_to:
        where_clauses.append("d.sent_at <= :date_to")
        params['date_to'] = date_to

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM crm_campaign_deliveries d
        WHERE {where_sql}
    """)
    total = int(db_session.execute(count_sql, params).scalar() or 0)

    rows_sql = text(f"""
        SELECT
            d.id,
            d.campaign_id,
            c.name                                            AS campaign_name,
            d.user_location_id,
            d.recipient_email,
            ul.first_name                                     AS recipient_first_name,
            ul.last_name                                      AS recipient_last_name,
            d.organization_id,
            o.name                                            AS organization_name,
            d.status,
            d.sent_at,
            d.opened_at,
            d.first_clicked_at,
            d.mandrill_message_id,
            d.error_message,
            d.retry_count,
            d.open_count,
            d.click_count,
            d.bounced_at
        FROM crm_campaign_deliveries d
        LEFT JOIN crm_campaigns c ON c.id = d.campaign_id
        LEFT JOIN user_locations ul ON ul.id = d.user_location_id
        LEFT JOIN organizations o ON o.id = d.organization_id
        WHERE {where_sql}
        ORDER BY d.sent_at DESC NULLS LAST, d.id DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = db_session.execute(
        rows_sql, {**params, 'limit': page_size, 'offset': offset}
    ).fetchall()

    items = [
        {
            'id': r[0],
            'campaignId': r[1],
            'campaignName': r[2],
            'userLocationId': r[3],
            'recipientEmail': r[4],
            'recipientName': ' '.join(filter(None, [r[5], r[6]])) or r[4],
            'organizationId': r[7],
            'organizationName': r[8],
            'status': r[9],
            'sentAt': r[10].isoformat() if r[10] else None,
            'openedAt': r[11].isoformat() if r[11] else None,
            'firstClickedAt': r[12].isoformat() if r[12] else None,
            'mandrillMessageId': r[13],
            'errorMessage': r[14],
            'retryCount': r[15] or 0,
            # Sprint 4 additions
            'openCount': r[16] or 0,
            'clickCount': r[17] or 0,
            'bouncedAt': r[18].isoformat() if r[18] else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


# ───────────────────────────────────────────────────────────────
# CSV export — Sprint 4 BE-1
# ───────────────────────────────────────────────────────────────

def export_crm_deliveries_csv(db_session: Session, query_params: dict) -> str:
    """
    Export crm_campaign_deliveries to CSV.  Reuses the same filters as
    list_crm_deliveries but has no pagination — streams all matching rows.

    CSV headers:
        id, campaign_id, campaign_name, user_location_id, recipient_email,
        recipient_name, organization_id, organization_name, status,
        sent_at, opened_at, first_clicked_at, bounced_at,
        open_count, click_count, mandrill_message_id, retry_count, error_message

    Returns the CSV body as a plain string.
    """
    import csv
    import io

    where_clauses = ["d.id IS NOT NULL"]
    params: Dict[str, Any] = {}

    campaign_id = query_params.get('campaignId')
    if campaign_id:
        try:
            params['campaign_id'] = int(campaign_id)
            where_clauses.append("d.campaign_id = :campaign_id")
        except (TypeError, ValueError):
            pass

    status_filter = (query_params.get('status') or '').strip()
    if status_filter:
        where_clauses.append("d.status = :status")
        params['status'] = status_filter

    email_filter = (query_params.get('recipientEmail') or '').strip()
    if email_filter:
        where_clauses.append("d.recipient_email ILIKE :email_q")
        params['email_q'] = f"%{email_filter}%"

    org_id = query_params.get('organizationId')
    if org_id:
        try:
            params['org_id'] = int(org_id)
            where_clauses.append("d.organization_id = :org_id")
        except (TypeError, ValueError):
            pass

    user_location_id_filter = (
        query_params.get('userLocationId') or query_params.get('recipientUserId') or ''
    ).strip()
    if user_location_id_filter:
        try:
            params['user_location_id'] = int(user_location_id_filter)
            where_clauses.append("d.user_location_id = :user_location_id")
        except (TypeError, ValueError):
            pass

    date_from = (query_params.get('dateFrom') or '').strip()
    if date_from:
        where_clauses.append("d.sent_at >= :date_from")
        params['date_from'] = date_from

    date_to = (query_params.get('dateTo') or '').strip()
    if date_to:
        where_clauses.append("d.sent_at <= :date_to")
        params['date_to'] = date_to

    where_sql = " AND ".join(where_clauses)

    rows_sql = text(f"""
        SELECT
            d.id,
            d.campaign_id,
            c.name                                            AS campaign_name,
            d.user_location_id,
            d.recipient_email,
            COALESCE(NULLIF(TRIM(CONCAT(ul.first_name, ' ', ul.last_name)), ''), d.recipient_email)
                                                              AS recipient_name,
            d.organization_id,
            o.name                                            AS organization_name,
            d.status,
            d.sent_at,
            d.opened_at,
            d.first_clicked_at,
            d.bounced_at,
            d.open_count,
            d.click_count,
            d.mandrill_message_id,
            d.retry_count,
            d.error_message
        FROM crm_campaign_deliveries d
        LEFT JOIN crm_campaigns c ON c.id = d.campaign_id
        LEFT JOIN user_locations ul ON ul.id = d.user_location_id
        LEFT JOIN organizations o ON o.id = d.organization_id
        WHERE {where_sql}
        ORDER BY d.sent_at DESC NULLS LAST, d.id DESC
    """)
    rows = db_session.execute(rows_sql, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id', 'campaign_id', 'campaign_name',
        'user_location_id', 'recipient_email', 'recipient_name',
        'organization_id', 'organization_name',
        'status', 'sent_at', 'opened_at', 'first_clicked_at', 'bounced_at',
        'open_count', 'click_count',
        'mandrill_message_id', 'retry_count', 'error_message',
    ])
    for r in rows:
        writer.writerow([
            r[0], r[1], r[2],
            r[3], r[4], r[5],
            r[6], r[7],
            r[8],
            r[9].isoformat() if r[9] else '',
            r[10].isoformat() if r[10] else '',
            r[11].isoformat() if r[11] else '',
            r[12].isoformat() if r[12] else '',
            r[13] or 0,
            r[14] or 0,
            r[15] or '',
            r[16] or 0,
            r[17] or '',
        ])
    return output.getvalue()


# ───────────────────────────────────────────────────────────────
# Unsubscribes (read-only admin view)
# ───────────────────────────────────────────────────────────────

def list_crm_unsubscribes(db_session: Session, query_params: dict) -> Dict[str, Any]:
    """
    Paginated list of crm_unsubscribes.

    Filters:
      email      — ILIKE
      source     — exact match (email_link | manual | bounce | complaint | mailchimp_webhook)
      dateFrom   — on created_date (= unsubscribed_at alias) inclusive
      dateTo     — inclusive

    ORDER BY unsubscribed_at DESC (= created_date on the table).
    """
    try:
        page = max(1, int(query_params.get('page', 1) or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(200, int(query_params.get('pageSize', 25) or 25)))
    except (TypeError, ValueError):
        page_size = 25

    where_clauses: list = ["u.id IS NOT NULL"]
    params: Dict[str, Any] = {}

    email_filter = (query_params.get('email') or '').strip()
    if email_filter:
        where_clauses.append("u.email ILIKE :email_q")
        params['email_q'] = f"%{email_filter}%"

    source_filter = (query_params.get('source') or '').strip()
    if source_filter:
        where_clauses.append("u.source = :source")
        params['source'] = source_filter

    date_from = (query_params.get('dateFrom') or '').strip()
    if date_from:
        where_clauses.append("u.unsubscribed_at >= :date_from")
        params['date_from'] = date_from

    date_to = (query_params.get('dateTo') or '').strip()
    if date_to:
        where_clauses.append("u.unsubscribed_at <= :date_to")
        params['date_to'] = date_to

    where_sql = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    total = int(db_session.execute(
        text(f"SELECT COUNT(*) FROM crm_unsubscribes u WHERE {where_sql}"), params
    ).scalar() or 0)

    rows_sql = text(f"""
        SELECT
            u.id,
            u.email,
            u.source,
            u.reason,
            u.unsubscribed_at                              AS created_date,
            u.user_location_id,
            ul.organization_id                             AS organization_id
        FROM crm_unsubscribes u
        LEFT JOIN user_locations ul ON ul.id = u.user_location_id
        WHERE {where_sql}
        ORDER BY u.unsubscribed_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = db_session.execute(
        rows_sql, {**params, 'limit': page_size, 'offset': offset}
    ).fetchall()

    items = [
        {
            'id': r[0],
            'email': r[1],
            'source': r[2],
            'reason': r[3],
            'createdDate': r[4].isoformat() if r[4] else None,
            'userLocationId': r[5],
            'organizationId': r[6],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}
