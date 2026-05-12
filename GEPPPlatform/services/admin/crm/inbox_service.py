"""
CRM Conversation Inbox service — Sprint 10 P1.

Outbound thread creation lives in `delivery_sender.py` (each delivery seeds
a `crm_conversations` row with a unique `thread_token`).  Inbound replies
arrive via `services/webhooks/mailchimp_inbound_handler.py` which extracts
the token from the Reply-To suffix (`reply+<token>@gepp.me`) and inserts an
inbound message row.

This module owns the admin-side read/write API:
  - list_conversations(db, org_id, filters, page, page_size)
  - get_conversation(db, conv_id, org_id) → conversation + ordered messages
  - send_reply(db, conv_id, org_id, from_user, subject, body_html, body_plain)
  - mark_read(db, conv_id, org_id)
  - close_conversation(db, conv_id, org_id, status)
"""

import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import BadRequestException, NotFoundException
from . import crm_service


# ── Token + reply-to helpers ────────────────────────────────────────────────

def generate_thread_token() -> str:
    """Cryptographically random 32-char URL-safe token (24 bytes → ~32 chars)."""
    return secrets.token_urlsafe(24)


def reply_to_for(thread_token: str) -> str:
    """Build the reply+<token>@<domain> address used by Mandrill inbound routing."""
    domain = os.environ.get('CRM_INBOUND_DOMAIN', 'gepp.me')
    return f"reply+{thread_token}@{domain}"


def ensure_conversation_for_delivery(
    db: Session,
    *,
    delivery_id: int,
    organization_id: Optional[int],
    user_location_id: Optional[int],
    lead_id: Optional[int],
    recipient_email: str,
    subject: str,
) -> Dict[str, Any]:
    """
    Called from delivery_sender when an outbound delivery dispatches.
    Returns {'id', 'thread_token', 'reply_to'}.

    Idempotent: a delivery row may seed at most one conversation. If the
    delivery already has a thread_token recorded, reuse it.
    """
    existing = db.execute(
        text("""
            SELECT c.id, c.thread_token
            FROM crm_conversation_messages m
            JOIN crm_conversations c ON c.id = m.conversation_id
            WHERE m.delivery_id = :did AND m.direction = 'outbound'
            ORDER BY m.id ASC
            LIMIT 1
        """),
        {'did': delivery_id},
    ).fetchone()
    if existing:
        token = existing[1]
        return {'id': existing[0], 'thread_token': token, 'reply_to': reply_to_for(token)}

    thread_token = generate_thread_token()
    now = datetime.now(timezone.utc)
    conv_id = db.execute(
        text("""
            INSERT INTO crm_conversations
              (organization_id, lead_id, user_location_id, subject,
               thread_token, status, last_message_at, unread_count,
               created_date, updated_date)
            VALUES
              (:org, :lid, :uid, :subject,
               :token, 'open', :now, 0,
               :now, :now)
            RETURNING id
        """),
        {
            'org': organization_id, 'lid': lead_id, 'uid': user_location_id,
            'subject': subject[:500] if subject else None,
            'token': thread_token, 'now': now,
        },
    ).scalar()
    db.execute(
        text("""
            INSERT INTO crm_conversation_messages
              (conversation_id, direction, delivery_id, to_email, subject,
               received_at)
            VALUES
              (:cid, 'outbound', :did, :to, :subject, :now)
        """),
        {'cid': conv_id, 'did': delivery_id, 'to': recipient_email,
         'subject': subject[:500] if subject else None, 'now': now},
    )
    db.execute(
        text("UPDATE crm_conversations SET last_message_at = :now WHERE id = :cid"),
        {'cid': conv_id, 'now': now},
    )
    return {'id': conv_id, 'thread_token': thread_token, 'reply_to': reply_to_for(thread_token)}


# ── List ─────────────────────────────────────────────────────────────────────

def list_conversations(
    db: Session, org_id: int, filters: Dict[str, Any], page: int, page_size: int,
) -> Dict[str, Any]:
    where = ["c.organization_id = :org"]
    params: Dict[str, Any] = {'org': org_id}

    status = (filters.get('status') or '').strip().lower()
    if status in ('open', 'closed', 'spam'):
        where.append("c.status = :status")
        params['status'] = status

    unread_only = (filters.get('unreadOnly') or filters.get('unread_only'))
    if str(unread_only).lower() in ('1', 'true', 'yes'):
        where.append("c.unread_count > 0")

    q = (filters.get('q') or '').strip()
    if q:
        where.append("(c.subject ILIKE :q OR EXISTS ("
                     " SELECT 1 FROM crm_conversation_messages m "
                     " WHERE m.conversation_id = c.id "
                     "   AND (m.from_email ILIKE :q OR m.to_email ILIKE :q)"
                     "))")
        params['q'] = f"%{q}%"

    lead_id = filters.get('leadId') or filters.get('lead_id')
    if lead_id:
        try:
            params['lid'] = int(lead_id)
            where.append("c.lead_id = :lid")
        except (TypeError, ValueError):
            pass

    where_sql = " AND ".join(where)
    total = db.execute(
        text(f"SELECT COUNT(*) FROM crm_conversations c WHERE {where_sql}"),
        params,
    ).scalar() or 0

    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    offset = (page - 1) * page_size

    rows = db.execute(
        text(f"""
            SELECT c.id, c.subject, c.thread_token, c.status,
                   c.last_message_at, c.unread_count, c.lead_id, c.user_location_id,
                   c.created_date,
                   (
                     SELECT json_build_object(
                       'fromEmail', m.from_email,
                       'toEmail',   m.to_email,
                       'direction', m.direction,
                       'snippet',   LEFT(COALESCE(m.body_plain, m.body_html), 200),
                       'receivedAt', m.received_at
                     )
                     FROM crm_conversation_messages m
                     WHERE m.conversation_id = c.id
                     ORDER BY m.received_at DESC, m.id DESC
                     LIMIT 1
                   ) AS last_message
            FROM crm_conversations c
            WHERE {where_sql}
            ORDER BY c.last_message_at DESC NULLS LAST, c.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, 'limit': page_size, 'offset': offset},
    ).fetchall()

    items = [
        {
            'id': r[0],
            'subject': r[1],
            'threadToken': r[2],
            'status': r[3],
            'lastMessageAt': r[4].isoformat() if r[4] else None,
            'unreadCount': int(r[5] or 0),
            'leadId': r[6],
            'userLocationId': r[7],
            'createdDate': r[8].isoformat() if r[8] else None,
            'lastMessage': r[9] or None,
        }
        for r in rows
    ]
    return {'items': items, 'total': int(total), 'page': page, 'pageSize': page_size}


# ── Get ──────────────────────────────────────────────────────────────────────

def get_conversation(db: Session, conv_id: int, org_id: int) -> Dict[str, Any]:
    conv = db.execute(
        text("""
            SELECT id, organization_id, lead_id, user_location_id, subject,
                   thread_token, status, last_message_at, unread_count,
                   created_date, updated_date
            FROM crm_conversations
            WHERE id = :id AND organization_id = :org
        """),
        {'id': conv_id, 'org': org_id},
    ).fetchone()
    if not conv:
        raise NotFoundException(f"Conversation {conv_id} not found")

    msgs = db.execute(
        text("""
            SELECT id, direction, delivery_id, from_email, to_email, subject,
                   body_html, body_plain, mandrill_message_id, received_at
            FROM crm_conversation_messages
            WHERE conversation_id = :cid
            ORDER BY received_at ASC, id ASC
        """),
        {'cid': conv_id},
    ).fetchall()

    return {
        'id': conv[0],
        'organizationId': conv[1],
        'leadId': conv[2],
        'userLocationId': conv[3],
        'subject': conv[4],
        'threadToken': conv[5],
        'status': conv[6],
        'lastMessageAt': conv[7].isoformat() if conv[7] else None,
        'unreadCount': int(conv[8] or 0),
        'createdDate': conv[9].isoformat() if conv[9] else None,
        'updatedDate': conv[10].isoformat() if conv[10] else None,
        'replyTo': reply_to_for(conv[5]),
        'messages': [
            {
                'id': m[0],
                'direction': m[1],
                'deliveryId': m[2],
                'fromEmail': m[3],
                'toEmail': m[4],
                'subject': m[5],
                'bodyHtml': m[6],
                'bodyPlain': m[7],
                'mandrillMessageId': m[8],
                'receivedAt': m[9].isoformat() if m[9] else None,
            }
            for m in msgs
        ],
    }


# ── Send reply ───────────────────────────────────────────────────────────────

def send_reply(
    db: Session,
    conv_id: int,
    org_id: int,
    *,
    body_html: str,
    body_plain: Optional[str] = None,
    subject: Optional[str] = None,
    from_user: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Send an outbound reply on an existing conversation thread.

    The reply goes through the same `send_via_email_lambda` path as campaigns.
    Reply-To is set to `reply+<thread_token>@gepp.me` so recipient replies
    route back into this same conversation via the inbound webhook.
    """
    if not (body_html or '').strip():
        raise BadRequestException("body_html is required")

    conv = db.execute(
        text("""
            SELECT id, thread_token, subject, status, lead_id, user_location_id
            FROM crm_conversations
            WHERE id = :id AND organization_id = :org
        """),
        {'id': conv_id, 'org': org_id},
    ).fetchone()
    if not conv:
        raise NotFoundException(f"Conversation {conv_id} not found")
    if conv[3] not in ('open',):
        raise BadRequestException(f"Cannot reply on a {conv[3]} conversation")

    # Recipient = the inbound 'from_email' of the most recent inbound msg,
    # or fall back to the outbound 'to_email' if no inbound replies yet.
    last_inbound = db.execute(
        text("""
            SELECT from_email FROM crm_conversation_messages
            WHERE conversation_id = :cid AND direction = 'inbound'
            ORDER BY received_at DESC, id DESC LIMIT 1
        """),
        {'cid': conv_id},
    ).fetchone()
    if last_inbound and last_inbound[0]:
        recipient = last_inbound[0]
    else:
        seed = db.execute(
            text("""
                SELECT to_email FROM crm_conversation_messages
                WHERE conversation_id = :cid AND direction = 'outbound'
                ORDER BY received_at ASC, id ASC LIMIT 1
            """),
            {'cid': conv_id},
        ).fetchone()
        recipient = seed[0] if seed else None

    if not recipient:
        raise BadRequestException("No recipient address on this conversation")

    thread_token = conv[1]
    final_subject = subject or (conv[2] and f"Re: {conv[2]}") or "Re:"

    result = crm_service.send_via_email_lambda(
        to_email=recipient,
        subject=final_subject,
        html_content=body_html,
        text_content=body_plain,
        reply_to=reply_to_for(thread_token),
        metadata={'conversation_id': str(conv_id), 'thread_token': thread_token},
        tags=['crm-inbox-reply', f'conversation-{conv_id}'],
    )

    now = datetime.now(timezone.utc)
    from_email = (from_user or {}).get('email') if from_user else None
    db.execute(
        text("""
            INSERT INTO crm_conversation_messages
              (conversation_id, direction, from_email, to_email, subject,
               body_html, body_plain, mandrill_message_id, received_at)
            VALUES
              (:cid, 'outbound', :fe, :te, :subj, :html, :plain, :mid, :now)
        """),
        {
            'cid': conv_id, 'fe': from_email, 'te': recipient,
            'subj': final_subject[:500], 'html': body_html, 'plain': body_plain,
            'mid': result.get('mandrill_message_id'), 'now': now,
        },
    )
    db.execute(
        text("""
            UPDATE crm_conversations
            SET last_message_at = :now, updated_date = :now
            WHERE id = :cid
        """),
        {'cid': conv_id, 'now': now},
    )
    db.commit()

    return {
        'sent': bool(result.get('success')),
        'mandrillMessageId': result.get('mandrill_message_id'),
        'recipient': recipient,
        'conversationId': conv_id,
    }


# ── Mark read / close ────────────────────────────────────────────────────────

def mark_read(db: Session, conv_id: int, org_id: int) -> Dict[str, Any]:
    affected = db.execute(
        text("""
            UPDATE crm_conversations
            SET unread_count = 0, updated_date = NOW()
            WHERE id = :id AND organization_id = :org
        """),
        {'id': conv_id, 'org': org_id},
    ).rowcount
    if not affected:
        raise NotFoundException(f"Conversation {conv_id} not found")
    db.commit()
    return {'id': conv_id, 'unreadCount': 0}


def set_status(db: Session, conv_id: int, org_id: int, status: str) -> Dict[str, Any]:
    status = (status or '').strip().lower()
    if status not in ('open', 'closed', 'spam'):
        raise BadRequestException("status must be one of: open, closed, spam")
    affected = db.execute(
        text("""
            UPDATE crm_conversations
            SET status = :status, updated_date = NOW()
            WHERE id = :id AND organization_id = :org
        """),
        {'id': conv_id, 'org': org_id, 'status': status},
    ).rowcount
    if not affected:
        raise NotFoundException(f"Conversation {conv_id} not found")
    db.commit()
    return {'id': conv_id, 'status': status}


# ── Inbound message insert (called by mailchimp inbound webhook) ────────────

def insert_inbound_message(
    db: Session,
    *,
    thread_token: str,
    from_email: str,
    to_email: Optional[str],
    subject: Optional[str],
    body_html: Optional[str],
    body_plain: Optional[str],
    mandrill_message_id: Optional[str],
) -> Optional[int]:
    """
    Match thread_token → conversation, insert an inbound message,
    bump unread_count + last_message_at.

    Returns the new message id, or None if no conversation matched.
    """
    conv = db.execute(
        text("""
            SELECT id, organization_id, lead_id, user_location_id
            FROM crm_conversations
            WHERE thread_token = :tok
            LIMIT 1
        """),
        {'tok': thread_token},
    ).fetchone()
    if not conv:
        return None

    conv_id = conv[0]
    now = datetime.now(timezone.utc)

    new_id = db.execute(
        text("""
            INSERT INTO crm_conversation_messages
              (conversation_id, direction, from_email, to_email, subject,
               body_html, body_plain, mandrill_message_id, received_at)
            VALUES
              (:cid, 'inbound', :fe, :te, :subj, :html, :plain, :mid, :now)
            RETURNING id
        """),
        {
            'cid': conv_id, 'fe': from_email, 'te': to_email,
            'subj': subject[:500] if subject else None,
            'html': body_html, 'plain': body_plain,
            'mid': mandrill_message_id, 'now': now,
        },
    ).scalar()

    db.execute(
        text("""
            UPDATE crm_conversations
            SET unread_count = unread_count + 1,
                last_message_at = :now,
                updated_date = :now,
                status = CASE WHEN status = 'closed' THEN 'open' ELSE status END
            WHERE id = :cid
        """),
        {'cid': conv_id, 'now': now},
    )

    # Emit a crm_event so analytics + drip scheduler can react to replies.
    try:
        crm_service.emit_event(
            db,
            event_type='email_reply_received',
            event_category='email',
            organization_id=conv[1],
            user_location_id=conv[3],
            properties={
                'conversation_id': conv_id,
                'lead_id': conv[2],
                'thread_token': thread_token,
                'mandrill_message_id': mandrill_message_id,
            },
            event_source='email_provider',
        )
    except Exception:
        # Logging only — never fail the webhook insert because of analytics.
        pass

    return new_id
