"""
CRM delivery sender — the single path from campaign to Mandrill.

Public API:
    enqueue_delivery(db, campaign, user_location_id, recipient_email, render_context) -> dict

Steps (per-delivery, committed independently):
  1. Unsub check — skip if email in crm_unsubscribes
  2. Cooldown check — skip if sent within cooldown_days
  3. Lookup template, user, org
  4. Render subject/html/plain via email_renderer
  5. INSERT crm_campaign_deliveries (status='pending')
  6. Invoke Mandrill via crm_service.send_via_email_lambda
  7. UPDATE delivery row → 'sent' + mandrill_message_id; emit email_sent event
  8. On failure → 'failed' + error_message; log and return (no raise)
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

import time

from . import crm_service
from .cooldown import check_cooldown, _DEFAULT_COOLDOWN_DAYS
from .email_renderer import render
from .logger import crm_log, new_correlation_id
from .unsubscribe_token import make_unsub_url
from ....models.crm import CrmCampaignDelivery

logger = logging.getLogger(__name__)

_DEFAULT_COOLDOWN_DAYS = 7


def enqueue_delivery(
    db: Session,
    campaign,
    user_location_id: Optional[int],
    recipient_email: str,
    render_context: Optional[Dict[str, Any]] = None,
    existing_delivery_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Enqueue and send one email delivery for *campaign* to *recipient_email*.

    Args:
        db:                   SQLAlchemy session (committed per delivery).
        campaign:             CrmCampaign ORM object (or dict with same keys).
        user_location_id:     ID in user_locations for per-user sends; None for list-only sends.
        recipient_email:      TO address.
        render_context:       Extra Mustache vars merged into the template render context.
        existing_delivery_id: If set (for retries), UPDATE the existing delivery row instead of
                              INSERTing a new one. The existing row's retry_count is incremented
                              and next_retry_at is cleared on success or exhaustion.

    Returns:
        Delivery row dict on success/unsub/failure.
        {'skipped': True, 'reason': 'cooldown'} if cooldown blocks the send.

    Never raises — failures are captured in the delivery row and logged.
    """
    render_context = render_context or {}
    _t0 = time.monotonic()
    _cid = new_correlation_id()

    # ── Helper: coerce campaign to attribute-style access ────────────────
    def _attr(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    campaign_id    = _attr(campaign, 'id')
    template_id    = _attr(campaign, 'template_id')
    trigger_config = _attr(campaign, 'trigger_config') or {}
    org_id_hint    = _attr(campaign, 'organization_id')

    crm_log("delivery.start", campaign_id=campaign_id,
            user_location_id=user_location_id, recipient_email=recipient_email,
            correlation_id=_cid)

    # ── 1. Unsubscribe check ─────────────────────────────────────────────
    unsub_row = db.execute(
        text("SELECT 1 FROM crm_unsubscribes WHERE email = :email LIMIT 1"),
        {"email": recipient_email},
    ).fetchone()

    if unsub_row:
        delivery = CrmCampaignDelivery(
            campaign_id=campaign_id,
            user_location_id=user_location_id,
            organization_id=org_id_hint,
            recipient_email=recipient_email,
            status="unsubscribed",
        )
        db.add(delivery)
        db.commit()
        logger.info("delivery_sender: skipped unsubscribed email=%s", recipient_email)
        return _row_to_dict(delivery)

    # ── 2. Cooldown check (delegates to cooldown.check_cooldown) ────────────
    cooldown_days = int(trigger_config.get("cooldown_days") or _DEFAULT_COOLDOWN_DAYS)
    is_blocked, last_sent = check_cooldown(db, campaign_id, user_location_id, cooldown_days)
    if is_blocked:
        logger.info(
            "delivery_sender: cooldown active for campaign=%s user=%s (last_sent=%s, cooldown=%sd)",
            campaign_id, user_location_id, last_sent, cooldown_days,
        )
        return {"skipped": True, "reason": "cooldown"}

    # ── 3. Lookup template ───────────────────────────────────────────────
    template_row = db.execute(
        text("SELECT id, subject, body_html, body_plain FROM crm_email_templates WHERE id = :tid"),
        {"tid": template_id},
    ).fetchone()

    if not template_row:
        logger.error("delivery_sender: template %s not found for campaign %s", template_id, campaign_id)
        return {"error": f"template {template_id} not found"}

    template_dict = {
        "id": template_row[0],
        "subject": template_row[1] or "",
        "body_html": template_row[2] or "",
        "body_plain": template_row[3] or "",
    }

    # ── 4. Lookup user + org ─────────────────────────────────────────────
    user_data: Dict[str, Any] = {}
    org_data:  Dict[str, Any] = {}
    organization_id = org_id_hint

    if user_location_id:
        user_row = db.execute(
            text("""
                SELECT ul.id, ul.email, ul.firstname, ul.lastname,
                       ul.organization_id, o.name AS org_name
                FROM user_locations ul
                LEFT JOIN organizations o ON o.id = ul.organization_id
                WHERE ul.id = :uid AND ul.deleted_date IS NULL
                LIMIT 1
            """),
            {"uid": user_location_id},
        ).fetchone()

        if user_row:
            user_data = {
                "id": user_row[0],
                "email": user_row[1] or recipient_email,
                "firstname": user_row[2] or "",
                "lastname": user_row[3] or "",
            }
            organization_id = user_row[4] or org_id_hint
            org_data = {"name": user_row[5] or ""}
    else:
        # List-based send — no specific user; use org from campaign
        if org_id_hint:
            org_row = db.execute(
                text("SELECT name FROM organizations WHERE id = :oid AND deleted_date IS NULL"),
                {"oid": org_id_hint},
            ).fetchone()
            if org_row:
                org_data = {"name": org_row[0] or ""}

    if not user_data.get("email"):
        user_data["email"] = recipient_email

    # ── 5. Render ────────────────────────────────────────────────────────
    extra_vars = {
        "unsubscribe_url": make_unsub_url(recipient_email),
        **render_context,
    }
    subject, html, plain = render(template_dict, user_data or None, org_data or None, extra_vars)

    # ── 6. Hash body for dedup ───────────────────────────────────────────
    rendered_body_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

    # ── 7. INSERT delivery row (pending) — or UPDATE existing row for retries ──
    if existing_delivery_id is not None:
        # Retry path: load and update the existing row in-place
        delivery = db.get(CrmCampaignDelivery, existing_delivery_id)
        if delivery is None:
            logger.error(
                "delivery_sender: existing_delivery_id=%s not found; aborting retry",
                existing_delivery_id,
            )
            return {"error": f"delivery {existing_delivery_id} not found"}
        delivery.status = "pending"
        delivery.rendered_subject = subject[:500]
        delivery.rendered_body_hash = rendered_body_hash
        delivery.error_message = None
        delivery.next_retry_at = None
        db.flush()
    else:
        # Normal path: insert a new delivery row
        delivery = CrmCampaignDelivery(
            campaign_id=campaign_id,
            user_location_id=user_location_id,
            organization_id=organization_id,
            recipient_email=recipient_email,
            status="pending",
            rendered_subject=subject[:500],
            rendered_body_hash=rendered_body_hash,
        )
        db.add(delivery)
        db.flush()  # get delivery.id without full commit

    # ── 8. Invoke Mandrill ───────────────────────────────────────────────
    try:
        result = crm_service.send_via_email_lambda(
            to_email=recipient_email,
            subject=subject,
            html_content=html,
            text_content=plain or None,
            from_name=_attr(campaign, "send_from_name"),
            from_email=_attr(campaign, "send_from_email"),
            reply_to=_attr(campaign, "reply_to"),
            metadata={
                "delivery_id": str(delivery.id),
                "campaign_id": str(campaign_id),
                "organization_id": str(organization_id or ""),
            },
        )
    except Exception as exc:
        # Unexpected error (e.g. boto3 not configured) — mark failed
        delivery.status = "failed"
        delivery.error_message = str(exc)
        delivery.retry_count = (delivery.retry_count or 0) + 1
        db.commit()
        logger.error("delivery_sender: Mandrill invoke raised: %s", exc)
        crm_log("delivery.failed",
                campaign_id=campaign_id, user_location_id=user_location_id,
                delivery_id=delivery.id, error_message=str(exc),
                latency_ms=int((time.monotonic() - _t0) * 1000),
                correlation_id=_cid)
        return _row_to_dict(delivery)

    # ── 9. Update on success ─────────────────────────────────────────────
    if result.get("success") and result.get("mandrill_message_id"):
        mandrill_id = result["mandrill_message_id"]
        delivery.status = "sent"
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.mandrill_message_id = mandrill_id
        delivery.mandrill_response = result.get("raw_response")
        db.commit()

        crm_service.emit_event(
            db,
            event_type="email_sent",
            event_category="email",
            event_source="internal",
            organization_id=organization_id,
            user_location_id=user_location_id,
            properties={
                "delivery_id": delivery.id,
                "campaign_id": campaign_id,
                "subject": subject,
                "mandrill_message_id": mandrill_id,
            },
            commit=True,
        )
        logger.info(
            "delivery_sender: sent campaign=%s delivery=%s mandrill_id=%s",
            campaign_id, delivery.id, mandrill_id,
        )
        crm_log("delivery.sent",
                campaign_id=campaign_id, user_location_id=user_location_id,
                delivery_id=delivery.id, mandrill_id=mandrill_id,
                latency_ms=int((time.monotonic() - _t0) * 1000),
                correlation_id=_cid)

    else:
        # Mandrill responded but without a message id — treat as failure
        error_msg = result.get("error") or "Missing mandrill_message_id"
        delivery.status = "failed"
        delivery.error_message = error_msg
        delivery.retry_count = (delivery.retry_count or 0) + 1
        delivery.mandrill_response = result.get("raw_response")
        db.commit()
        logger.warning(
            "delivery_sender: Mandrill returned no _id for campaign=%s delivery=%s: %s",
            campaign_id, delivery.id, error_msg,
        )
        crm_log("delivery.failed",
                campaign_id=campaign_id, user_location_id=user_location_id,
                delivery_id=delivery.id, error_message=error_msg,
                latency_ms=int((time.monotonic() - _t0) * 1000),
                correlation_id=_cid)

    return _row_to_dict(delivery)


def _row_to_dict(delivery: CrmCampaignDelivery) -> Dict[str, Any]:
    """Serialize a delivery row to a plain dict for callers."""
    return {
        "id": delivery.id,
        "campaign_id": delivery.campaign_id,
        "user_location_id": delivery.user_location_id,
        "organization_id": delivery.organization_id,
        "recipient_email": delivery.recipient_email,
        "status": delivery.status,
        "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
        "mandrill_message_id": delivery.mandrill_message_id,
        "rendered_body_hash": delivery.rendered_body_hash,
        "error_message": delivery.error_message,
        "retry_count": delivery.retry_count,
    }
