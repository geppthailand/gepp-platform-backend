"""
POST /api/webhooks/mailchimp — Mailchimp Transactional (Mandrill) webhook receiver.

Public endpoint — security comes from HMAC-SHA1 signature verification per
https://mailchimp.com/developer/transactional/guides/track-respond-activity-webhooks/

Envelope: form-encoded body with a `mandrill_events` param containing a JSON array
of events. Each event has a type (send | open | click | hard_bounce | soft_bounce |
reject | spam | unsub) and a `msg` object with `_id` (Mandrill message id) and our
`metadata` (which we populate with {delivery_id, campaign_id, organization_id}).
"""

import os
import json
import hmac
import base64
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Lazy import to avoid circular at module load — resolved on first call
def _crm_log(event: str, **kwargs):
    try:
        from GEPPPlatform.services.admin.crm.logger import crm_log
        crm_log(event, **kwargs)
    except Exception:
        pass  # never let logging break the webhook


# ── Mandrill event → delivery status mapping ─────────────────────────────────
# (transition only *forward* — we never move status backward)
# Status names must match the chk_crm_delivery_status CHECK constraint in
# migration 034. `spam` from Mandrill is mapped to `unsubscribed` since a spam
# complaint is functionally identical to an unsubscribe (the recipient is also
# inserted into crm_unsubscribes via the auto-unsub branch below).
_STATUS_ORDER = [
    "pending", "sending", "sent", "delivered",
    "opened", "clicked",
    "soft_bounced", "failed", "hard_bounced", "rejected",
    "unsubscribed",
]
_STATUS_RANK = {s: i for i, s in enumerate(_STATUS_ORDER)}

_EVENT_TO_STATUS = {
    "send":        "sent",
    "open":        "opened",
    "click":       "clicked",
    "hard_bounce": "hard_bounced",
    "soft_bounce": None,         # special: increment counter, set next_retry_at
    "spam":        "unsubscribed",  # spam = effective unsub (CHECK doesn't allow 'spam_reported')
    "unsub":       "unsubscribed",
    "reject":      "rejected",
}

_EVENT_TO_CRM_TYPE = {
    "send":        "email_sent",
    "open":        "email_opened",
    "click":       "email_clicked",
    "hard_bounce": "email_bounced",
    "soft_bounce": "email_bounced",
    "spam":        "email_unsubscribed",
    "unsub":       "email_unsubscribed",
    "reject":      "email_sent",   # failed send; still log
}

# Events that require an auto-unsubscribe entry
_AUTO_UNSUB_EVENTS = {"hard_bounce", "spam", "unsub"}


def verify_signature(url: str, form_params: Dict[str, List[str]], signature_header: str) -> bool:
    """
    Mailchimp Transactional signature = base64(HMAC-SHA1(webhook_key, url + sorted(key+value pairs))).
    Returns True on match.
    """
    webhook_key = os.environ.get('MAILCHIMP_WEBHOOK_KEY', '')
    if not webhook_key or not signature_header:
        return False

    # Build signed string per Mandrill spec
    signed = url
    for key in sorted(form_params.keys()):
        for value in form_params[key]:
            signed += key + value

    mac = hmac.new(webhook_key.encode('utf-8'), signed.encode('utf-8'), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode('utf-8')
    return hmac.compare_digest(expected, signature_header.strip())


def parse_events(raw_body: str) -> List[Dict[str, Any]]:
    parsed = parse_qs(raw_body or '')
    mandrill_events_param = parsed.get('mandrill_events', [None])[0]
    if not mandrill_events_param:
        return []
    try:
        return json.loads(mandrill_events_param)
    except json.JSONDecodeError:
        logger.warning("mailchimp webhook: mandrill_events not valid JSON")
        return []


def _can_advance(current_status: Optional[str], new_status: str) -> bool:
    """Return True if transitioning from current_status → new_status is a forward move."""
    if not current_status:
        return True
    return _STATUS_RANK.get(new_status, -1) > _STATUS_RANK.get(current_status, -1)


def _process_event(event: Dict[str, Any], db_session) -> None:
    """Process a single Mandrill event dict — update delivery row + emit crm_events."""
    from GEPPPlatform.services.admin.crm import crm_service  # lazy import

    event_type = event.get("event", "")
    msg = event.get("msg") or {}
    msg_id = msg.get("_id") or event.get("_id") or ""
    metadata = msg.get("metadata") or {}
    ts_epoch = msg.get("ts") or event.get("ts")
    email = msg.get("email", "")

    delivery_id_str = metadata.get("delivery_id")
    campaign_id_str = metadata.get("campaign_id")
    organization_id_str = metadata.get("organization_id")

    try:
        delivery_id = int(delivery_id_str) if delivery_id_str else None
    except (ValueError, TypeError):
        delivery_id = None

    try:
        campaign_id = int(campaign_id_str) if campaign_id_str else None
    except (ValueError, TypeError):
        campaign_id = None

    try:
        organization_id = int(organization_id_str) if organization_id_str else None
    except (ValueError, TypeError):
        organization_id = None

    # ── Find delivery row ─────────────────────────────────────────────────
    delivery_row = None
    if delivery_id:
        delivery_row = db_session.execute(
            text("""
                SELECT id, status, campaign_id, user_location_id, organization_id,
                       recipient_email, open_count, click_count, retry_count
                FROM crm_campaign_deliveries
                WHERE id = :did
                LIMIT 1
            """),
            {"did": delivery_id},
        ).fetchone()

    if delivery_row is None and msg_id:
        # Fallback: match by mandrill_message_id
        delivery_row = db_session.execute(
            text("""
                SELECT id, status, campaign_id, user_location_id, organization_id,
                       recipient_email, open_count, click_count, retry_count
                FROM crm_campaign_deliveries
                WHERE mandrill_message_id = :mid
                LIMIT 1
            """),
            {"mid": msg_id},
        ).fetchone()

    if delivery_row is None:
        logger.warning(
            "mailchimp_webhook: no delivery row found for event=%s delivery_id=%s msg_id=%s",
            event_type, delivery_id, msg_id,
        )
        # Still try to auto-unsub if applicable
        if event_type in _AUTO_UNSUB_EVENTS and email:
            _insert_unsubscribe(db_session, email, event_type)
        return

    row_id           = delivery_row[0]
    current_status   = delivery_row[1]
    row_campaign_id  = delivery_row[2] or campaign_id
    user_location_id = delivery_row[3]
    row_org_id       = delivery_row[4] or organization_id
    row_email        = delivery_row[5] or email
    open_count       = delivery_row[6] or 0
    click_count      = delivery_row[7] or 0
    retry_count      = delivery_row[8] or 0

    # ── Idempotency: skip if we've already recorded this exact event ───────
    existing_event = db_session.execute(
        text("""
            SELECT 1 FROM crm_events
            WHERE properties->>'mandrill_event' = :ev
              AND properties->>'mandrill_msg_id' = :mid
              AND user_location_id IS NOT DISTINCT FROM :uid
            LIMIT 1
        """),
        {"ev": event_type, "mid": msg_id, "uid": user_location_id},
    ).fetchone()

    if existing_event:
        logger.debug(
            "mailchimp_webhook: duplicate event=%s msg_id=%s — skipping",
            event_type, msg_id,
        )
        return

    now = datetime.now(timezone.utc)

    # ── Update delivery row ───────────────────────────────────────────────
    new_status = _EVENT_TO_STATUS.get(event_type)

    if event_type == "soft_bounce":
        # Don't advance status — increment counter and schedule retry
        db_session.execute(
            text("""
                UPDATE crm_campaign_deliveries
                SET retry_count    = retry_count + 1,
                    next_retry_at  = NOW() + INTERVAL '1 hour',
                    updated_date   = NOW()
                WHERE id = :row_id
            """),
            {"row_id": row_id},
        )

    elif new_status and _can_advance(current_status, new_status):
        params: Dict[str, Any] = {"row_id": row_id, "status": new_status}
        extra_sets = ["status = :status", "updated_date = NOW()"]

        if new_status == "sent" and current_status in (None, "pending", "sending"):
            extra_sets.append("sent_at = COALESCE(sent_at, NOW())")
            if msg_id:
                extra_sets.append("mandrill_message_id = :mid")
                params["mid"] = msg_id

        elif new_status == "opened":
            extra_sets.append("opened_at = COALESCE(opened_at, NOW())")
            extra_sets.append("open_count = open_count + 1")

        elif new_status == "clicked":
            extra_sets.append("first_clicked_at = COALESCE(first_clicked_at, NOW())")
            extra_sets.append("click_count = click_count + 1")

        elif new_status == "hard_bounced":
            extra_sets.append("bounced_at = NOW()")
            bounce_desc = msg.get("bounce_description") or msg.get("bounce_error") or ""
            if bounce_desc:
                extra_sets.append("error_message = :bounce_desc")
                params["bounce_desc"] = bounce_desc

        elif new_status == "rejected":
            reject_reason = (msg.get("reject_reason") or "").strip()
            if reject_reason:
                extra_sets.append("error_message = :reject_reason")
                params["reject_reason"] = reject_reason

        db_session.execute(
            text(f"UPDATE crm_campaign_deliveries SET {', '.join(extra_sets)} WHERE id = :row_id"),
            params,
        )

    # ── Auto-unsubscribe for hard_bounce / spam / unsub ───────────────────
    if event_type in _AUTO_UNSUB_EVENTS:
        _insert_unsubscribe(db_session, row_email or email, event_type)

    # ── Emit crm_events row ───────────────────────────────────────────────
    crm_event_type = _EVENT_TO_CRM_TYPE.get(event_type)
    if crm_event_type:
        crm_service.emit_event(
            db_session,
            event_type=crm_event_type,
            event_category="email",
            event_source="email_provider",
            organization_id=row_org_id,
            user_location_id=user_location_id,
            properties={
                "delivery_id": row_id,
                "campaign_id": row_campaign_id,
                "mandrill_event": event_type,
                "mandrill_msg_id": msg_id,
            },
        )

    db_session.commit()


def _insert_unsubscribe(db_session, email: str, source_event: str) -> None:
    """INSERT into crm_unsubscribes ON CONFLICT DO NOTHING."""
    if not email:
        return
    source_map = {
        "hard_bounce": "mandrill_bounce",
        "spam":        "mandrill_spam",
        "unsub":       "mandrill_unsub",
    }
    source = source_map.get(source_event, "mandrill_webhook")
    db_session.execute(
        text("""
            INSERT INTO crm_unsubscribes (email, source, unsubscribed_at)
            VALUES (:email, :source, NOW())
            ON CONFLICT (email) DO NOTHING
        """),
        {"email": email, "source": source},
    )
    logger.info("mailchimp_webhook: auto-unsubscribed email=%s source=%s", email, source)


def handle_mailchimp_webhook(event: dict, db_session) -> Dict[str, Any]:
    """
    Entry from app.py. Returns API Gateway response.
    Verifies Mandrill HMAC-SHA1 signature, then processes each event.
    """
    raw_body = event.get('body', '') or ''
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    signature = headers.get('x-mandrill-signature', '')

    # Construct the full URL as Mandrill sees it (behind API Gateway)
    request_context = event.get('requestContext', {})
    domain = headers.get('host') or request_context.get('domainName', '')
    path = event.get('rawPath') or event.get('path', '')
    url = f"https://{domain}{path}"

    form_params = parse_qs(raw_body)

    if not verify_signature(url, form_params, signature):
        logger.warning("mailchimp webhook: signature verification FAILED")
        return {"statusCode": 401, "body": json.dumps({"error": "Invalid signature"})}

    events = parse_events(raw_body)
    logger.info("mailchimp webhook: received %d events", len(events))

    from GEPPPlatform.services.admin.crm.logger import new_correlation_id
    _batch_cid = new_correlation_id()
    _crm_log("webhook.received",
             signature_valid=True, event_count=len(events),
             correlation_id=_batch_cid)

    processed = 0
    errors = 0
    for evt in events:
        try:
            _process_event(evt, db_session)
            processed += 1
            _crm_log("webhook.processed",
                     mandrill_event=evt.get("event"),
                     msg_id=(evt.get("msg") or {}).get("_id") or evt.get("_id"),
                     delivery_id=(evt.get("msg") or {}).get("metadata", {}).get("delivery_id"),
                     correlation_id=_batch_cid)
        except Exception as exc:
            errors += 1
            logger.error("mailchimp_webhook: error processing event %s: %s", evt.get("event"), exc)
            # Don't let one bad event break the rest — continue
            try:
                db_session.rollback()
            except Exception:
                pass

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": processed, "errors": errors}),
    }
