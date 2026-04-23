"""
POST /api/webhooks/mailchimp — Mailchimp Transactional (Mandrill) webhook receiver.

Public endpoint — security comes from HMAC-SHA1 signature verification per
https://mailchimp.com/developer/transactional/guides/track-respond-activity-webhooks/

Envelope: form-encoded body with a `mandrill_events` param containing a JSON array
of events. Each event has a type (send | open | click | hard_bounce | soft_bounce |
reject | spam | unsub) and a `msg` object with `_id` (Mandrill message id) and our
`metadata` (which we populate with {delivery_id, campaign_id, organization_id}).

BE Dev 2 fills in Sprint 4.
"""

import os
import json
import hmac
import base64
import hashlib
import logging
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)


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


def handle_mailchimp_webhook(event: dict, db_session) -> Dict[str, Any]:
    """
    Entry from app.py. Returns API Gateway response.
    BE Dev 2 implements the event→delivery update logic per the plan §6.3 step 8.
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

    # BE Dev 2: for each event, match to crm_campaign_deliveries by metadata.delivery_id,
    # update status + timestamps, insert corresponding crm_events row.
    # Handle: send | open | click | hard_bounce | soft_bounce | reject | spam | unsub

    return {"statusCode": 200, "body": json.dumps({"processed": len(events)})}
