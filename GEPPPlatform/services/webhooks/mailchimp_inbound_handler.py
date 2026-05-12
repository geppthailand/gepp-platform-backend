"""
POST /api/webhooks/mailchimp/inbound — Mailchimp Transactional INBOUND webhook.

When a recipient replies to a CRM email, Mailchimp routes the reply to the
inbound endpoint configured under the address `reply+<thread_token>@gepp.me`.
This handler:

  1. Verifies the HMAC-SHA1 signature (same algorithm as the activity webhook).
  2. Parses the `mandrill_events` payload (array of inbound message events).
  3. For each event:
       a. Extracts the `thread_token` from the To: address (`reply+<token>@gepp.me`).
       b. Calls `inbox_service.insert_inbound_message(...)` to attach the reply
          to the matching conversation, bump unread_count, and emit
          `email_reply_received` into crm_events.

Inbound payload reference:
  https://mailchimp.com/developer/transactional/guides/set-up-inbound-email-processing/
"""

import os
import re
import json
import hmac
import base64
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Match "reply+<token>@<anything>" in either an Email field or the raw address.
_REPLY_PLUS_RE = re.compile(r"reply\+([A-Za-z0-9_-]{8,128})@", re.IGNORECASE)


def verify_signature(url: str, form_params: Dict[str, List[str]], signature_header: str) -> bool:
    """Same algorithm as activity webhook — mailchimp_handler.verify_signature."""
    webhook_key = os.environ.get('MAILCHIMP_WEBHOOK_KEY', '')
    if not webhook_key or not signature_header:
        return False
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
        logger.warning("mailchimp inbound webhook: mandrill_events not valid JSON")
        return []


def _extract_thread_token(msg: Dict[str, Any]) -> Optional[str]:
    """
    Inbound payloads put the recipient list under `msg.to` as
    [[email, name], ...]; the envelope is in `msg.email`.

    We scan every available address until we find a `reply+<token>@...` match.
    """
    candidates: List[str] = []
    raw_email = msg.get('email')
    if isinstance(raw_email, str):
        candidates.append(raw_email)

    to_list = msg.get('to') or []
    if isinstance(to_list, list):
        for entry in to_list:
            if isinstance(entry, (list, tuple)) and entry:
                candidates.append(str(entry[0]))
            elif isinstance(entry, dict):
                addr = entry.get('email')
                if addr:
                    candidates.append(addr)
            elif isinstance(entry, str):
                candidates.append(entry)

    # Some Mandrill payloads also include CC list — scan those too.
    cc_list = msg.get('cc') or []
    if isinstance(cc_list, list):
        for entry in cc_list:
            if isinstance(entry, (list, tuple)) and entry:
                candidates.append(str(entry[0]))
            elif isinstance(entry, dict):
                addr = entry.get('email')
                if addr:
                    candidates.append(addr)

    for addr in candidates:
        m = _REPLY_PLUS_RE.search(addr or '')
        if m:
            return m.group(1)
    return None


def _process_inbound_event(event: Dict[str, Any], db: Session) -> Tuple[str, Optional[int]]:
    """
    Returns a status string + the new message id (or None).
    Status: 'inserted' | 'no_thread' | 'skipped'
    """
    from GEPPPlatform.services.admin.crm.inbox_service import insert_inbound_message

    msg = event.get('msg') or {}
    token = _extract_thread_token(msg)
    if not token:
        logger.info("mailchimp inbound: no thread_token found in event")
        return 'no_thread', None

    from_email = msg.get('from_email') or msg.get('email_from') or ''
    to_email = None
    raw_to = msg.get('email')
    if isinstance(raw_to, str):
        to_email = raw_to
    elif isinstance(msg.get('to'), list) and msg['to']:
        first = msg['to'][0]
        if isinstance(first, (list, tuple)) and first:
            to_email = str(first[0])
        elif isinstance(first, dict):
            to_email = first.get('email')
        elif isinstance(first, str):
            to_email = first

    new_id = insert_inbound_message(
        db,
        thread_token=token,
        from_email=from_email,
        to_email=to_email,
        subject=msg.get('subject'),
        body_html=msg.get('html'),
        body_plain=msg.get('text'),
        mandrill_message_id=msg.get('_id') or event.get('_id'),
    )
    if new_id is None:
        logger.warning("mailchimp inbound: thread_token=%s did not match any conversation", token)
        return 'no_thread', None
    return 'inserted', new_id


def handle_mailchimp_inbound_webhook(event: dict, db_session: Session) -> Dict[str, Any]:
    """
    Entry from app.py. Returns API Gateway response.
    """
    raw_body = event.get('body', '') or ''
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    signature = headers.get('x-mandrill-signature', '')

    request_context = event.get('requestContext', {})
    domain = headers.get('host') or request_context.get('domainName', '')
    path = event.get('rawPath') or event.get('path', '')
    url = f"https://{domain}{path}"

    form_params = parse_qs(raw_body)

    if not verify_signature(url, form_params, signature):
        logger.warning("mailchimp inbound webhook: signature verification FAILED")
        return {"statusCode": 401, "body": json.dumps({"error": "Invalid signature"})}

    events = parse_events(raw_body)
    logger.info("mailchimp inbound webhook: received %d events", len(events))

    inserted = 0
    no_thread = 0
    errors = 0
    for evt in events:
        try:
            status, _ = _process_inbound_event(evt, db_session)
            if status == 'inserted':
                inserted += 1
            else:
                no_thread += 1
            db_session.commit()
        except Exception as exc:
            errors += 1
            logger.error("mailchimp_inbound_webhook: error processing event: %s", exc)
            try:
                db_session.rollback()
            except Exception:
                pass

    return {
        "statusCode": 200,
        "body": json.dumps({
            "inserted": inserted,
            "noThread": no_thread,
            "errors": errors,
        }),
    }
