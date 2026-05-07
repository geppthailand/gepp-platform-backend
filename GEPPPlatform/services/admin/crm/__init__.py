"""CRM / Marketing admin routes — dispatches /api/admin/crm-* to the right handler method.

Wired into the main admin router via admin_handlers.py handler_map dicts (see AdminHandlers methods
list_resource / get_resource / create_resource / update_resource / delete_resource).

Analytics + segments + templates + campaigns + email lists also have sub-paths (e.g. `/preview`,
`/evaluate`, `/test`, `/metrics`) that are routed here from services/admin/__init__.py.
"""

import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

from ....exceptions import APIException, NotFoundException, BadRequestException
from . import crm_service

logger = logging.getLogger(__name__)


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
        return _dispatch_templates(resource_id, sub_path, method, db_session, data, query_params, current_user)

    if resource == 'crm-campaigns':
        return _dispatch_campaigns(resource_id, sub_path, method, db_session, data, query_params, current_user)

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

    # GET /crm-analytics/user/{id}/events  →  per-user event timeline
    if len(parts) == 3 and parts[0] == 'user' and parts[2] == 'events':
        user_id = _to_int(parts[1])
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 25))
        event_type_filter = query_params.get('eventType')
        offset = (max(page, 1) - 1) * page_size
        where = "user_location_id = :uid"
        params: dict = {'uid': user_id}
        if event_type_filter:
            where += " AND event_type = :et"
            params['et'] = event_type_filter
        from sqlalchemy import text as _text
        total_row = db_session.execute(
            _text(f"SELECT COUNT(*) FROM crm_events WHERE {where}"), params
        ).scalar()
        rows = db_session.execute(
            _text(f"""
                SELECT id, event_type, event_category, organization_id, properties,
                       occurred_at, event_source
                FROM crm_events
                WHERE {where}
                ORDER BY occurred_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {**params, 'limit': page_size, 'offset': offset},
        ).fetchall()
        items = [
            {
                'id': r[0],
                'eventType': r[1],
                'eventCategory': r[2],
                'organizationId': r[3],
                'properties': r[4] or {},
                'occurredAt': r[5].isoformat() if r[5] else None,
                'eventSource': r[6],
            }
            for r in rows
        ]
        return {"items": items, "total": int(total_row or 0), "page": page, "pageSize": page_size}

    raise NotFoundException(f"Analytics sub-path not found: {sub_path}")


# ─── Segments (stubs — BE2 fills in Sprint 2) ────────────────────────────────

def _dispatch_segments(resource_id, sub_path, method, db_session, data, query_params):
    from .segment_evaluator import get_field_registry, preview_segment, evaluate_segment
    from .crm_handlers import get_crm_segment
    from sqlalchemy import text

    parts = [p for p in (sub_path or '').strip('/').split('/') if p]

    # GET /crm-segments/fields  →  field registry for rule builder
    if not resource_id and parts == ['fields'] and method == 'GET':
        return get_field_registry()

    # POST /crm-segments/preview  →  preview count+sample without saving
    if not resource_id and parts == ['preview'] and method == 'POST':
        rules = data.get('rules')
        scope = data.get('scope', 'user')
        org_id = _int_param(data, 'organizationId')
        if not rules:
            raise BadRequestException("rules is required for preview")
        return preview_segment(db_session, rules, scope, org_id)

    # POST /crm-segments/{id}/evaluate  →  re-materialize membership
    if resource_id and parts == ['evaluate'] and method == 'POST':
        return evaluate_segment(db_session, resource_id)

    # GET /crm-segments/{id}/members
    if resource_id and parts == ['members'] and method == 'GET':
        seg = get_crm_segment(db_session, resource_id)
        scope_pk = 'user_location_id' if seg['scope'] == 'user' else 'organization_id'
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('pageSize', 25))
        offset = (max(page, 1) - 1) * page_size
        total_row = db_session.execute(
            text("SELECT COUNT(*) FROM crm_segment_members WHERE segment_id = :sid"),
            {'sid': resource_id},
        ).scalar()
        rows = db_session.execute(
            text(f"""
                SELECT sm.member_id, sm.evaluated_at,
                       CASE WHEN sm.member_type = 'user'
                            THEN ul.email
                            ELSE o.name
                       END AS display_name
                FROM crm_segment_members sm
                LEFT JOIN user_locations ul ON sm.member_type='user' AND ul.id=sm.member_id
                LEFT JOIN organizations o ON sm.member_type='organization' AND o.id=sm.member_id
                WHERE sm.segment_id = :sid
                ORDER BY sm.member_id
                LIMIT :limit OFFSET :offset
            """),
            {'sid': resource_id, 'limit': page_size, 'offset': offset},
        ).fetchall()
        return {
            "items": [{"memberId": r[0], "evaluatedAt": r[1].isoformat() if r[1] else None, "displayName": r[2] or ""} for r in rows],
            "total": int(total_row or 0),
            "page": page,
            "pageSize": page_size,
        }

    # GET /crm-segments/{id}/insights  →  tier distribution summary
    if resource_id and parts == ['insights'] and method == 'GET':
        seg = get_crm_segment(db_session, resource_id)
        table = 'crm_user_profiles' if seg['scope'] == 'user' else 'crm_org_profiles'
        pk_col = 'user_location_id' if seg['scope'] == 'user' else 'organization_id'
        rows = db_session.execute(
            text(f"""
                SELECT p.activity_tier, COUNT(*)
                FROM crm_segment_members sm
                JOIN {table} p ON p.{pk_col} = sm.member_id
                WHERE sm.segment_id = :sid
                GROUP BY p.activity_tier
            """),
            {'sid': resource_id},
        ).fetchall()
        tier_dist = {r[0] or 'dormant': int(r[1]) for r in rows}
        avg_score_row = db_session.execute(
            text(f"""
                SELECT AVG(p.engagement_score)
                FROM crm_segment_members sm
                JOIN {table} p ON p.{pk_col} = sm.member_id
                WHERE sm.segment_id = :sid
            """),
            {'sid': resource_id},
        ).scalar()
        return {
            "memberCount": seg['memberCount'],
            "tierDistribution": tier_dist,
            "avgEngagementScore": round(float(avg_score_row or 0), 2),
        }

    # GET /crm-segments/{id}/versions  →  version history chain
    if resource_id and parts == ['versions'] and method == 'GET':
        rows = db_session.execute(
            text("""
                WITH RECURSIVE chain AS (
                    SELECT id, name, version, is_current, created_date, parent_segment_id
                    FROM crm_segments WHERE id = :id AND deleted_date IS NULL
                    UNION ALL
                    SELECT s.id, s.name, s.version, s.is_current, s.created_date, s.parent_segment_id
                    FROM crm_segments s
                    JOIN chain c ON c.parent_segment_id = s.id
                    WHERE s.deleted_date IS NULL
                )
                SELECT id, version, is_current, created_date FROM chain ORDER BY version DESC
            """),
            {'id': resource_id},
        ).fetchall()
        return {"versions": [{"id": r[0], "version": r[1], "isCurrent": r[2], "createdDate": r[3].isoformat() if r[3] else None} for r in rows]}

    # POST /crm-segments/{id}/clone
    if resource_id and parts == ['clone'] and method == 'POST':
        from .crm_handlers import create_crm_segment
        seg = get_crm_segment(db_session, resource_id)
        return create_crm_segment(db_session, {
            'name': f"{seg['name']} (copy)",
            'description': seg.get('description'),
            'scope': seg['scope'],
            'rules': seg['rules'],
            'organizationId': seg.get('organizationId'),
        })

    raise NotFoundException(f"crm-segments sub-route not found: {method} /{sub_path}")


# ─── Templates ───────────────────────────────────────────────────────────────

def _dispatch_templates(resource_id, sub_path, method, db_session, data, query_params, current_user=None):
    """
    Template sub-routes (Sprint 2 — BE Sonnet 2):
      POST /admin/crm-templates/{id}/render-preview — render a saved template
      POST /admin/crm-templates/render-preview      — render an inline template dict
      GET  /admin/crm-templates/{id}/versions       — version history chain
      POST /admin/crm-templates/generate-ai         — AI content generation (rate-limited)
    """
    from .email_renderer import render as render_template
    from .crm_handlers import get_crm_template
    from sqlalchemy import text as _text

    parts = [p for p in (sub_path or '').strip('/').split('/') if p]

    # POST /crm-templates/{id}/render-preview  →  rendered subject + html
    if resource_id and parts == ['render-preview'] and method == 'POST':
        tpl = get_crm_template(db_session, resource_id)
        user_data = data.get('user') or {}
        org_data  = data.get('org') or {}
        extra     = dict(data.get('extraVars') or {})
        # Auto-inject a signed unsubscribe_url so the preview matches what real
        # recipients will see (Task 4).  We use a sentinel email so the token is
        # cryptographically valid but will never match an actual subscriber.
        if not extra.get('unsubscribe_url'):
            from .unsubscribe_token import make_unsub_url
            extra['unsubscribe_url'] = make_unsub_url('preview@example.com')
        subject, html, plain = render_template(tpl, user_data, org_data, extra)
        return {"subject": subject, "html": html, "plain": plain}

    # POST /crm-templates/render-preview  →  render by passing template inline
    if not resource_id and parts == ['render-preview'] and method == 'POST':
        template_row = data.get('template') or {}
        user_data = data.get('user') or {}
        org_data  = data.get('org') or {}
        extra     = dict(data.get('extraVars') or {})
        if not extra.get('unsubscribe_url'):
            from .unsubscribe_token import make_unsub_url
            extra['unsubscribe_url'] = make_unsub_url('preview@example.com')
        subject, html, plain = render_template(template_row, user_data, org_data, extra)
        return {"subject": subject, "html": html, "plain": plain}

    # GET /crm-templates/{id}/versions  →  version history chain (Task 1)
    if resource_id and parts == ['versions'] and method == 'GET':
        rows = db_session.execute(
            _text("""
                WITH RECURSIVE chain AS (
                    SELECT id, name, version,
                           COALESCE(is_current, TRUE) AS is_current,
                           created_date, parent_template_id
                    FROM crm_email_templates
                    WHERE id = :id AND deleted_date IS NULL
                    UNION ALL
                    SELECT t.id, t.name, t.version,
                           COALESCE(t.is_current, TRUE),
                           t.created_date, t.parent_template_id
                    FROM crm_email_templates t
                    JOIN chain c ON c.parent_template_id = t.id
                    WHERE t.deleted_date IS NULL
                )
                SELECT id, version, is_current, created_date FROM chain ORDER BY version DESC
            """),
            {'id': resource_id},
        ).fetchall()
        return {
            "versions": [
                {
                    "id": r[0],
                    "version": r[1],
                    "isCurrent": r[2],
                    "createdDate": r[3].isoformat() if r[3] else None,
                }
                for r in rows
            ]
        }

    # POST /crm-templates/generate-ai  →  AI email generation (rate-limited, Task 3)
    if not resource_id and parts == ['generate-ai'] and method == 'POST':
        # Rate-limit guard — must run BEFORE the LLM call.
        from . import ai_rate_limit
        uid = current_user.get('id') if current_user else None
        oid = current_user.get('organization_id') if current_user else None
        ai_rate_limit.check_and_increment(db_session, user_location_id=uid, organization_id=oid)

        from ....prompts.crm_email_gen.default.clients.llm_client import call_llm_for_email
        prompt_text = (data.get('prompt') or '').strip()
        if not prompt_text:
            raise BadRequestException("'prompt' is required")
        # Backwards-compat: accept legacy 'intent' as the tone + 'audience' appended.
        tone = (data.get('tone') or data.get('intent') or 'professional').strip()
        variables = data.get('variables') or []
        if not isinstance(variables, list):
            variables = []
        audience = (data.get('audience') or '').strip()
        if audience:
            prompt_text = f"{prompt_text}\n\nAudience: {audience}"

        try:
            result = call_llm_for_email(prompt=prompt_text, tone=tone, variables=variables)
        except Exception as e:
            logger.error("AI template generation failed: %s", e)
            raise BadRequestException(f"AI generation failed: {e}")

        # Emit usage event AFTER successful generation so the counter only grows on real calls.
        try:
            crm_service.emit_event(
                db_session,
                event_type='ai_template_generated',
                event_category='crm',
                user_location_id=uid,
                organization_id=oid,
                properties={
                    'token_usage': result.get('token_usage'),
                    'model': result.get('model'),
                },
                commit=True,
            )
        except Exception as emit_exc:
            logger.warning("Could not emit ai_template_generated event (non-fatal): %s", emit_exc)

        return result

    raise NotFoundException(f"crm-templates sub-route not found: {method} /{sub_path}")


# ─── Campaigns ───────────────────────────────────────────────────────────────

def _dispatch_campaigns(resource_id, sub_path, method, db_session, data, query_params, current_user=None):
    """
    Campaign sub-routes (Sprint 2 — BE Sonnet 1):
      POST /admin/crm-campaigns/{id}/start    — start a draft or paused campaign
      POST /admin/crm-campaigns/{id}/pause    — pause a running campaign
      POST /admin/crm-campaigns/{id}/resume   — resume a paused campaign
      POST /admin/crm-campaigns/{id}/archive  — archive any non-archived campaign
      POST /admin/crm-campaigns/{id}/test     — send 1 email without affecting metrics

    Routes from Sprint 1 (measure path):
      GET  /admin/crm-campaigns/{id}/metrics    — aggregated delivery stats + cache
      GET  /admin/crm-campaigns/{id}/deliveries — paginated deliveries for campaign

    Response shapes (for FE Sonnet 2):
      start  → {"status": str, "recipientCount": int, "enqueuedAt": str (ISO)}
      pause  → {"status": "paused", "pausedAt": str (ISO)}
      resume → {"status": "running"}
      archive→ {"status": "archived", "archivedAt": str (ISO)}
      test   → {"sent": true, "mandrillMessageId": str | null}
    """
    from .crm_handlers import list_crm_deliveries
    from sqlalchemy import text
    import json
    from datetime import datetime, timezone

    parts = [p for p in (sub_path or '').strip('/').split('/') if p]

    # ── POST /crm-campaigns/{id}/start ───────────────────────────────────────
    if resource_id and parts == ['start'] and method == 'POST':
        return _start_campaign(db_session, resource_id)

    # ── POST /crm-campaigns/{id}/pause ───────────────────────────────────────
    if resource_id and parts == ['pause'] and method == 'POST':
        return _pause_campaign(db_session, resource_id)

    # ── POST /crm-campaigns/{id}/resume ──────────────────────────────────────
    if resource_id and parts == ['resume'] and method == 'POST':
        return _resume_campaign(db_session, resource_id)

    # ── POST /crm-campaigns/{id}/archive ─────────────────────────────────────
    if resource_id and parts == ['archive'] and method == 'POST':
        return _archive_campaign(db_session, resource_id)

    # ── POST /crm-campaigns/{id}/test ────────────────────────────────────────
    if resource_id and parts == ['test'] and method == 'POST':
        return _test_campaign(db_session, resource_id, data, current_user or {})

    # ── GET /crm-campaigns/{id}/metrics ──────────────────────────────────────
    if resource_id and parts == ['metrics'] and method == 'GET':
        campaign_id = resource_id
        force_refresh = (query_params.get('refresh') or '').lower() in ('1', 'true', 'yes')

        # Check cache first (TTL = 5 minutes)
        if not force_refresh:
            cache_row = db_session.execute(
                text("""
                    SELECT metrics_cache, metrics_cached_at
                    FROM crm_campaigns
                    WHERE id = :id AND deleted_date IS NULL
                """),
                {'id': campaign_id},
            ).fetchone()
            if not cache_row:
                raise NotFoundException(f"Campaign {campaign_id} not found")
            cached_data, cached_at = cache_row[0], cache_row[1]
            if cached_data and cached_at:
                # Check freshness
                now_utc = datetime.now(timezone.utc)
                # cached_at may be tz-aware or tz-naive from DB; normalize
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=timezone.utc)
                age_seconds = (now_utc - cached_at).total_seconds()
                if age_seconds < 300:  # 5 minutes
                    return cached_data if isinstance(cached_data, dict) else json.loads(cached_data)

        # Recompute from crm_campaign_deliveries
        # Status mapping (actual DB values from migration 034):
        #   sent-family:       sent, delivered, opened, clicked, soft_bounced, hard_bounced,
        #                      rejected, unsubscribed
        #   opened-family:     opened, clicked
        #   clicked:           clicked
        #   bounced:           soft_bounced, hard_bounced
        #   unsubscribed:      unsubscribed
        #   failed:            failed
        #   pending:           pending, sending
        agg_row = db_session.execute(
            text("""
                SELECT
                    COUNT(*)                                                           AS total,
                    COUNT(*) FILTER (WHERE status IN (
                        'sent','delivered','opened','clicked',
                        'soft_bounced','hard_bounced','rejected','unsubscribed'
                    ))                                                                 AS sent,
                    COUNT(*) FILTER (WHERE status IN ('opened','clicked'))             AS opened,
                    COUNT(*) FILTER (WHERE status = 'clicked')                         AS clicked,
                    COUNT(*) FILTER (WHERE status IN ('soft_bounced','hard_bounced'))  AS bounced,
                    COUNT(*) FILTER (WHERE status = 'unsubscribed')                    AS unsubscribed,
                    COUNT(*) FILTER (WHERE status = 'failed')                          AS failed,
                    COUNT(*) FILTER (WHERE status IN ('pending','sending'))             AS pending,
                    MIN(sent_at)                                                        AS first_sent_at,
                    MAX(sent_at)                                                        AS last_sent_at
                FROM crm_campaign_deliveries
                WHERE campaign_id = :cid
            """),
            {'cid': campaign_id},
        ).fetchone()

        if not agg_row:
            raise NotFoundException(f"Campaign {campaign_id} not found")

        total      = int(agg_row[0] or 0)
        sent       = int(agg_row[1] or 0)
        opened     = int(agg_row[2] or 0)
        clicked    = int(agg_row[3] or 0)
        bounced    = int(agg_row[4] or 0)
        unsub      = int(agg_row[5] or 0)
        failed     = int(agg_row[6] or 0)
        pending    = int(agg_row[7] or 0)
        first_sent = agg_row[8]
        last_sent  = agg_row[9]

        # Rates (guard division by zero)
        open_rate   = round(opened  / sent   * 100, 2) if sent   > 0 else 0.0
        click_rate  = round(clicked / opened * 100, 2) if opened > 0 else 0.0
        bounce_rate = round(bounced / sent   * 100, 2) if sent   > 0 else 0.0
        unsub_rate  = round(unsub   / sent   * 100, 2) if sent   > 0 else 0.0

        metrics = {
            "campaignId":   campaign_id,
            "total":        total,
            "sent":         sent,
            "opened":       opened,
            "clicked":      clicked,
            "bounced":      bounced,
            "unsubscribed": unsub,
            "failed":       failed,
            "pending":      pending,
            "openRate":     open_rate,
            "clickRate":    click_rate,
            "bounceRate":   bounce_rate,
            "unsubscribeRate": unsub_rate,
            "firstSentAt":  first_sent.isoformat() if first_sent else None,
            "lastSentAt":   last_sent.isoformat()  if last_sent  else None,
        }

        # Write cache
        db_session.execute(
            text("""
                UPDATE crm_campaigns
                SET metrics_cache = :cache, metrics_cached_at = NOW()
                WHERE id = :id
            """),
            {'cache': json.dumps(metrics), 'id': campaign_id},
        )
        db_session.commit()

        return metrics

    # ── GET /crm-campaigns/{id}/deliveries ───────────────────────────────────
    if resource_id and parts == ['deliveries'] and method == 'GET':
        # Inject campaign filter and delegate to shared list handler
        merged_params = dict(query_params)
        merged_params['campaignId'] = resource_id
        return list_crm_deliveries(db_session, merged_params)

    # ── GET /crm-campaigns/{id}/impact ───────────────────────────────────────
    # Returns lift analysis comparing recipient engagement before vs. after campaign start.
    # Response shape documented in campaign_impact.py module docstring.
    if resource_id and parts == ['impact'] and method == 'GET':
        from .campaign_impact import compute_impact
        try:
            window_days = max(1, min(365, int(query_params.get('windowDays', 30) or 30)))
        except (TypeError, ValueError):
            window_days = 30
        return compute_impact(db_session, resource_id, window_days=window_days)

    # ── GET /crm-campaigns/{id}/suggested-actions ────────────────────────────
    # Sprint 4 — deterministic next-best-action suggestions computed from delivery stats.
    # Response: {campaignId, openedNotClicked, bouncedCount, pendingOver24hCount,
    #            totalRecipients, computedAt}
    if resource_id and parts == ['suggested-actions'] and method == 'GET':
        return _get_suggested_actions(db_session, resource_id)

    # ── POST /crm-campaigns/{id}/derive-recipients ───────────────────────────
    # Sprint 4 — derive a recipient list from delivery status for follow-up campaigns.
    # Body: {kind: 'non_openers' | 'openers_not_clickers' | 'bouncers'}
    # Response: {campaignId, kind, recipientUserIds, emails, count, computedAt}
    if resource_id and parts == ['derive-recipients'] and method == 'POST':
        kind = (data.get('kind') or '').strip()
        return _derive_recipients(db_session, resource_id, kind)

    raise NotFoundException(
        f"crm-campaigns sub-route not found: {method} /{sub_path}"
    )


def _get_suggested_actions(db_session, campaign_id):
    """
    GET /admin/crm-campaigns/{id}/suggested-actions

    Computes 4 deterministic metrics in a single SQL pass over crm_campaign_deliveries:
      - openedNotClicked : opened but no click after 7 days (actionable re-engagement)
      - bouncedCount     : hard + soft bounced + rejected (suppression candidates)
      - pendingOver24hCount : stuck in pending for > 24h (investigate send path)
      - totalRecipients  : total delivery rows for this campaign

    All logic is deterministic SQL — no LLM at runtime (per strategy constraint D-A4).
    """
    from sqlalchemy import text as _t
    from datetime import datetime, timezone

    # Verify campaign exists
    exists = db_session.execute(
        _t("SELECT 1 FROM crm_campaigns WHERE id = :id AND deleted_date IS NULL"),
        {'id': campaign_id},
    ).fetchone()
    if not exists:
        raise NotFoundException(f"Campaign {campaign_id} not found")

    row = db_session.execute(
        _t("""
            SELECT
                COUNT(*) FILTER (
                    WHERE status IN ('opened','clicked')
                )                                                               AS opened,
                COUNT(*) FILTER (
                    WHERE status = 'opened'
                      AND first_clicked_at IS NULL
                      AND sent_at < NOW() - INTERVAL '7 days'
                )                                                               AS opened_not_clicked,
                COUNT(*) FILTER (
                    WHERE status IN ('hard_bounced','soft_bounced','rejected')
                )                                                               AS bounced_count,
                COUNT(*) FILTER (
                    WHERE status = 'pending'
                      AND created_date < NOW() - INTERVAL '24 hours'
                )                                                               AS pending_over_24h,
                COUNT(*)                                                        AS total_recipients
            FROM crm_campaign_deliveries
            WHERE campaign_id = :cid
        """),
        {'cid': campaign_id},
    ).fetchone()

    now_utc = datetime.now(timezone.utc)
    return {
        "campaignId":         campaign_id,
        "opened":             int(row[0] or 0),
        "openedNotClicked":   int(row[1] or 0),
        "bouncedCount":       int(row[2] or 0),
        "pendingOver24hCount":int(row[3] or 0),
        "totalRecipients":    int(row[4] or 0),
        "computedAt":         now_utc.isoformat(),
    }


def _derive_recipients(db_session, campaign_id, kind):
    """
    POST /admin/crm-campaigns/{id}/derive-recipients

    Builds a recipient list from crm_campaign_deliveries filtered by delivery status.

    kind options:
      non_openers          — status IN ('sent','delivered')  [received but never opened]
      openers_not_clickers — status='opened' AND first_clicked_at IS NULL
                             AND sent_at < NOW()-7d           [engaged but not converted]
      bouncers             — status IN ('hard_bounced','soft_bounced','rejected')

    Returns {campaignId, kind, recipientUserIds, emails, count, computedAt}.
    The FE wizard reads recipientUserIds + emails to pre-fill a new campaign.
    No crm_email_lists row is created here — the wizard creates an ephemeral list on submit.
    """
    from sqlalchemy import text as _t
    from datetime import datetime, timezone

    VALID_KINDS = {'non_openers', 'openers_not_clickers', 'bouncers'}
    if kind not in VALID_KINDS:
        raise BadRequestException(
            f"Invalid kind '{kind}'. Must be one of: {', '.join(sorted(VALID_KINDS))}"
        )

    # Verify campaign exists
    exists = db_session.execute(
        _t("SELECT 1 FROM crm_campaigns WHERE id = :id AND deleted_date IS NULL"),
        {'id': campaign_id},
    ).fetchone()
    if not exists:
        raise NotFoundException(f"Campaign {campaign_id} not found")

    # Build WHERE clause based on kind
    if kind == 'non_openers':
        kind_where = "status IN ('sent','delivered')"
    elif kind == 'openers_not_clickers':
        kind_where = (
            "status = 'opened' "
            "AND first_clicked_at IS NULL "
            "AND sent_at < NOW() - INTERVAL '7 days'"
        )
    else:  # bouncers
        kind_where = "status IN ('hard_bounced','soft_bounced','rejected')"

    rows = db_session.execute(
        _t(f"""
            SELECT user_location_id, recipient_email
            FROM crm_campaign_deliveries
            WHERE campaign_id = :cid
              AND {kind_where}
            ORDER BY id
        """),
        {'cid': campaign_id},
    ).fetchall()

    recipient_user_ids = [r[0] for r in rows if r[0] is not None]
    emails = [r[1] for r in rows if r[1]]

    now_utc = datetime.now(timezone.utc)
    return {
        "campaignId":         campaign_id,
        "kind":               kind,
        "recipientUserIds":   recipient_user_ids,
        "emails":             emails,
        "count":              len(rows),
        "computedAt":         now_utc.isoformat(),
    }


# ─── Campaign action implementations ─────────────────────────────────────────

def _load_campaign_row(db_session, campaign_id):
    """Fetch one campaign row (14 cols) or raise NotFoundException."""
    from sqlalchemy import text as _t
    row = db_session.execute(
        _t("""
            SELECT id, organization_id, name, campaign_type,
                   trigger_event, trigger_config, segment_id,
                   recipient_list_id, template_id, status,
                   started_at, send_from_name, send_from_email, reply_to
            FROM crm_campaigns
            WHERE id = :id AND deleted_date IS NULL
        """),
        {'id': campaign_id},
    ).fetchone()
    if not row:
        raise NotFoundException(f"Campaign {campaign_id} not found")
    return row


def _start_campaign(db_session, campaign_id):
    """
    Start a draft or paused campaign.

    Trigger  → status='running', no deliveries yet.
    Blast    → resolve recipient list / segment, fan out in 50-row chunks, status='completed'.

    Returns: {"status": str, "recipientCount": int, "enqueuedAt": str}
    """
    from sqlalchemy import text as _t
    from datetime import datetime, timezone
    from . import delivery_sender as _ds

    row = _load_campaign_row(db_session, campaign_id)
    (camp_id, org_id, _name, camp_type, trigger_event, trigger_config,
     segment_id, recipient_list_id, template_id, status,
     started_at, from_name, from_email, reply_to) = row

    if status not in ('draft', 'paused'):
        raise APIException(
            f"Campaign is already '{status}' — only draft or paused campaigns can be started",
            status_code=409,
        )
    if not template_id:
        raise BadRequestException("Campaign must have a template_id before starting")
    if camp_type == 'trigger' and not trigger_event:
        raise BadRequestException("Trigger campaign must have trigger_event set")
    if camp_type == 'blast' and not recipient_list_id and not segment_id:
        raise BadRequestException("Blast campaign must have recipient_list_id or segment_id set")

    now_utc = datetime.now(timezone.utc)

    # ── Trigger: just flip status ─────────────────────────────────────────
    if camp_type == 'trigger':
        db_session.execute(
            _t("""UPDATE crm_campaigns
                  SET status='running', started_at=COALESCE(started_at,:now), updated_date=:now
                  WHERE id=:id"""),
            {'id': campaign_id, 'now': now_utc},
        )
        db_session.commit()
        return {"status": "running", "recipientCount": 0, "enqueuedAt": now_utc.isoformat()}

    # ── Blast: resolve recipients ─────────────────────────────────────────
    recipients = []  # [(email, user_location_id | None)]
    if recipient_list_id:
        lr = db_session.execute(
            _t("SELECT emails FROM crm_email_lists WHERE id=:id AND deleted_date IS NULL"),
            {'id': recipient_list_id},
        ).fetchone()
        if lr:
            for entry in (lr[0] or []):
                email = entry.get('email') if isinstance(entry, dict) else str(entry)
                if email:
                    recipients.append((email, None))
    elif segment_id:
        for seg_row in db_session.execute(
            _t("""SELECT ul.id, ul.email
                  FROM crm_segment_members sm
                  JOIN user_locations ul ON ul.id=sm.member_id AND ul.deleted_date IS NULL
                  WHERE sm.segment_id=:sid AND sm.member_type='user'"""),
            {'sid': segment_id},
        ).fetchall():
            if seg_row[1]:
                recipients.append((seg_row[1], seg_row[0]))

    # Flip to running immediately
    db_session.execute(
        _t("""UPDATE crm_campaigns
              SET status='running', started_at=COALESCE(started_at,:now), updated_date=:now
              WHERE id=:id"""),
        {'id': campaign_id, 'now': now_utc},
    )
    db_session.commit()

    # ── SQS guard: hard-block blasts > 1 000 until SQS path is implemented ──
    # SQS-backed delivery queue (Sprint 4 / crm_blast_scaling.md) is not yet
    # available.  Blasts between 100-1000 are warned; > 1000 are rejected.
    _INLINE_WARN_THRESHOLD = 100
    _INLINE_HARD_LIMIT     = 1000
    if len(recipients) > _INLINE_HARD_LIMIT:
        raise BadRequestException(
            f"Blasts with more than {_INLINE_HARD_LIMIT} recipients must use the SQS path "
            f"— currently disabled. Contact the platform team."
        )
    if len(recipients) > _INLINE_WARN_THRESHOLD:
        logger.warning(
            "_start_campaign: blast campaign=%s has %d recipients (> %d threshold). "
            "Inline fan-out may approach Lambda timeout. Enable SQS path in Sprint 4 "
            "when blasts reliably exceed this size.",
            campaign_id, len(recipients), _INLINE_WARN_THRESHOLD,
        )

    # Fan out in chunks of 50 — per-chunk commit avoids long DB transactions
    campaign_obj = {
        'id': campaign_id, 'organization_id': org_id, 'template_id': template_id,
        'trigger_config': trigger_config or {}, 'send_from_name': from_name,
        'send_from_email': from_email, 'reply_to': reply_to,
    }
    enqueued = 0
    for i in range(0, len(recipients), 50):
        for email, uid in recipients[i:i + 50]:
            if not _ds.enqueue_delivery(db_session, campaign_obj, user_location_id=uid,
                                        recipient_email=email).get('skipped'):
                enqueued += 1
        db_session.commit()

    # Transition to completed
    db_session.execute(
        _t("UPDATE crm_campaigns SET status='completed', ended_at=:now, updated_date=:now WHERE id=:id"),
        {'id': campaign_id, 'now': datetime.now(timezone.utc)},
    )
    db_session.commit()
    return {"status": "completed", "recipientCount": enqueued, "enqueuedAt": now_utc.isoformat()}


def _pause_campaign(db_session, campaign_id):
    """Pause a running campaign. Returns {"status": "paused", "pausedAt": str}."""
    from sqlalchemy import text as _t
    from datetime import datetime, timezone
    row = _load_campaign_row(db_session, campaign_id)
    if row[9] != 'running':
        raise APIException(
            f"Campaign is '{row[9]}' — only 'running' campaigns can be paused", status_code=409)
    now_utc = datetime.now(timezone.utc)
    db_session.execute(
        _t("UPDATE crm_campaigns SET status='paused', updated_date=:now WHERE id=:id"),
        {'id': campaign_id, 'now': now_utc},
    )
    db_session.commit()
    return {"status": "paused", "pausedAt": now_utc.isoformat()}


def _resume_campaign(db_session, campaign_id):
    """Resume a paused campaign. Returns {"status": "running"}."""
    from sqlalchemy import text as _t
    from datetime import datetime, timezone
    row = _load_campaign_row(db_session, campaign_id)
    if row[9] != 'paused':
        raise APIException(
            f"Campaign is '{row[9]}' — only 'paused' campaigns can be resumed", status_code=409)
    db_session.execute(
        _t("UPDATE crm_campaigns SET status='running', updated_date=:now WHERE id=:id"),
        {'id': campaign_id, 'now': datetime.now(timezone.utc)},
    )
    db_session.commit()
    return {"status": "running"}


def _archive_campaign(db_session, campaign_id):
    """Archive any non-archived campaign. Returns {"status": "archived", "archivedAt": str}."""
    from sqlalchemy import text as _t
    from datetime import datetime, timezone
    row = _load_campaign_row(db_session, campaign_id)
    if row[9] == 'archived':
        raise APIException("Campaign is already archived", status_code=409)
    now_utc = datetime.now(timezone.utc)
    db_session.execute(
        _t("""UPDATE crm_campaigns
              SET status='archived', ended_at=COALESCE(ended_at,:now), updated_date=:now
              WHERE id=:id"""),
        {'id': campaign_id, 'now': now_utc},
    )
    db_session.commit()
    return {"status": "archived", "archivedAt": now_utc.isoformat()}


def _test_campaign(db_session, campaign_id, data, current_user):
    """
    Send one test email without inserting a delivery row or affecting metrics.

    Anti-abuse: recipientEmail must be the admin's own email OR appear in any
    crm_email_lists row for the same org.

    Returns: {"sent": bool, "mandrillMessageId": str | null}
    """
    from sqlalchemy import text as _t
    from .email_renderer import render as _render
    from .unsubscribe_token import make_unsub_url

    recipient_email = (data.get('recipientEmail') or '').strip().lower()
    if not recipient_email:
        raise BadRequestException("recipientEmail is required")

    row = _load_campaign_row(db_session, campaign_id)
    (camp_id, org_id, _name, _ct, _te, _tc,
     _sid, _rlid, template_id, _status,
     _started, from_name, from_email, reply_to) = row

    if not template_id:
        raise BadRequestException("Campaign has no template_id — set a template before testing")

    # Auth check — admin's own email is always allowed
    admin_email = (current_user.get('email') or '').strip().lower()
    if recipient_email != admin_email:
        list_match = db_session.execute(
            _t("""SELECT 1 FROM crm_email_lists
                  WHERE organization_id=:org_id
                    AND deleted_date IS NULL
                    AND emails @> jsonb_build_array(jsonb_build_object('email', :email::text))
                  LIMIT 1"""),
            {'org_id': org_id, 'email': recipient_email},
        ).fetchone()
        if not list_match:
            raise BadRequestException(
                "Test sends are restricted to your own email or addresses in this org's email lists"
            )

    # Load template
    tpl_row = db_session.execute(
        _t("SELECT id, subject, body_html, body_plain FROM crm_email_templates WHERE id=:tid"),
        {'tid': template_id},
    ).fetchone()
    if not tpl_row:
        raise BadRequestException(f"Template {template_id} not found")

    tpl = {'id': tpl_row[0], 'subject': tpl_row[1] or '',
           'body_html': tpl_row[2] or '', 'body_plain': tpl_row[3] or ''}

    # Render with sample context
    subject, html, plain = _render(
        tpl,
        {'firstname': 'Test User', 'lastname': '', 'email': recipient_email},
        {'name': 'Test Org'},
        {'unsubscribe_url': make_unsub_url(recipient_email), 'event_properties': {}},
    )

    # Send directly — no delivery row inserted
    result = crm_service.send_via_email_lambda(
        to_email=recipient_email,
        subject=f"[TEST] {subject}",
        html_content=html,
        text_content=plain or None,
        from_name=from_name,
        from_email=from_email,
        reply_to=reply_to,
        tags=['crm-test'],
        metadata={'campaign_id': str(campaign_id), 'test_send': 'true'},
    )
    return {"sent": bool(result.get('success')), "mandrillMessageId": result.get('mandrill_message_id')}


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
