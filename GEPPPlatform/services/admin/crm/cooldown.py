"""
CRM cooldown enforcement — reusable check extracted from delivery_sender.

Public API:
    check_cooldown(db, campaign_id, user_location_id, cooldown_days) -> (bool, datetime|None)

The inline query that lived in delivery_sender.py step 2 is lifted here so the
scheduler and any future code can call it independently.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

_DEFAULT_COOLDOWN_DAYS = 7


def check_cooldown(
    db: Session,
    campaign_id: int,
    user_location_id: Optional[int],
    cooldown_days: int = _DEFAULT_COOLDOWN_DAYS,
) -> Tuple[bool, Optional[datetime]]:
    """
    Return (is_blocked, last_sent_at).

    is_blocked = True when the most recent successful delivery for (campaign, user)
    occurred less than cooldown_days ago.

    Args:
        db:               Active SQLAlchemy session.
        campaign_id:      crm_campaigns.id
        user_location_id: user_locations.id; None → never blocked (list-only sends).
        cooldown_days:    Minimum gap in days between sends.  0 disables cooldown.

    Returns:
        (False, None)              — no prior send, or cooldown expired → allow send.
        (True,  <last_sent_at>)    — within cooldown window → skip.
    """
    if user_location_id is None:
        # List-only sends (no specific user) are never cooldown-blocked
        return False, None

    if cooldown_days <= 0:
        return False, None

    row = db.execute(
        text("""
            SELECT MAX(sent_at)
            FROM crm_campaign_deliveries
            WHERE campaign_id        = :cid
              AND user_location_id   = :uid
              AND status IN ('sent', 'delivered', 'opened', 'clicked')
        """),
        {"cid": campaign_id, "uid": user_location_id},
    ).fetchone()

    last_sent: Optional[datetime] = row[0] if row else None

    if last_sent is None:
        return False, None

    # Normalise to tz-aware
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)

    age = datetime.now(timezone.utc) - last_sent
    is_blocked = age < timedelta(days=cooldown_days)

    if is_blocked:
        logger.debug(
            "cooldown: blocked campaign=%s user=%s last_sent=%s cooldown=%sd",
            campaign_id, user_location_id, last_sent, cooldown_days,
        )

    return is_blocked, last_sent
