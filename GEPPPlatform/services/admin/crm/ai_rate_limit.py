"""
AI template generation rate-limit guard — BE Sonnet 2, Sprint 2.

Limits:
  - Per user:         20 calls / 24 hours
  - Per organisation: 100 calls / 24 hours

Usage in handler:
    from .ai_rate_limit import check_and_increment
    check_and_increment(db, user_id=current_user['id'], org_id=current_user.get('organization_id'))

check_and_increment raises BadRequestException (HTTP 400 / treated as 429 by callers) if
either limit is breached.  On success it does NOT write an event — the caller must emit
crm_events('ai_template_generated') after the actual LLM call succeeds so the count
only increments on real usage.

count_today() is exposed for testing without side-effects.
"""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import BadRequestException

logger = logging.getLogger(__name__)

_EVENT_TYPE       = "ai_template_generated"
_USER_DAILY_LIMIT = 20
_ORG_DAILY_LIMIT  = 100


def count_today(
    db: Session,
    *,
    user_location_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> dict:
    """
    Return {'user': int, 'org': int} counts for the rolling 24-hour window.

    Either argument may be None (count is skipped / returned as 0).
    """
    user_count = 0
    org_count  = 0

    if user_location_id is not None:
        row = db.execute(
            text("""
                SELECT COUNT(*)
                FROM crm_events
                WHERE event_type = :et
                  AND user_location_id = :uid
                  AND occurred_at > NOW() - INTERVAL '24 hours'
            """),
            {'et': _EVENT_TYPE, 'uid': user_location_id},
        ).scalar()
        user_count = int(row or 0)

    if organization_id is not None:
        row = db.execute(
            text("""
                SELECT COUNT(*)
                FROM crm_events
                WHERE event_type = :et
                  AND organization_id = :oid
                  AND occurred_at > NOW() - INTERVAL '24 hours'
            """),
            {'et': _EVENT_TYPE, 'oid': organization_id},
        ).scalar()
        org_count = int(row or 0)

    return {'user': user_count, 'org': org_count}


def check_and_increment(
    db: Session,
    *,
    user_location_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> None:
    """
    Raise BadRequestException if either daily limit is exceeded.

    NOTE: This function only *checks* — it does NOT write an event.
    The caller must call crm_service.emit_event(..., event_type='ai_template_generated')
    after the LLM call succeeds so the counter only grows on real usage.

    Args:
        db:               SQLAlchemy session.
        user_location_id: ID of the acting user_location (may be None for org-scoped keys).
        organization_id:  ID of the organisation (may be None).

    Raises:
        BadRequestException: with a human-readable message including the limit.
    """
    counts = count_today(db, user_location_id=user_location_id, organization_id=organization_id)

    if user_location_id is not None and counts['user'] >= _USER_DAILY_LIMIT:
        raise BadRequestException(
            f"AI rate limit exceeded: user has used {counts['user']} / {_USER_DAILY_LIMIT} "
            "AI template generations today. Limit resets after 24 hours."
        )

    if organization_id is not None and counts['org'] >= _ORG_DAILY_LIMIT:
        raise BadRequestException(
            f"AI rate limit exceeded: organisation has used {counts['org']} / {_ORG_DAILY_LIMIT} "
            "AI template generations today. Limit resets after 24 hours."
        )
