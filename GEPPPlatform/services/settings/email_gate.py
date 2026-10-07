"""Email gate: every email the platform sends passes here right before the email Lambda.

`notification.email_enabled` ON → the message goes out unchanged. OFF → only the
recipients matching `notification.email_test_recipients` (addresses or @domains)
stay; if none are left the message is not sent at all. Either way a skipped
recipient is logged, so "why did nobody get the email" has an answer.

Read failures fall back to the code default (ON in production, OFF elsewhere) —
never to "send everything", and a broken settings table never raises into a send.
"""
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from . import global_settings as gs

logger = logging.getLogger(__name__)


def email_lambda_function() -> str:
    """Name of the Mailchimp-wrapper Lambda to invoke.

    `EMAIL_LAMBDA_FUNCTION` wins when set. Otherwise follow the caller's own stage:
    a `DEV-…` Lambda uses DEV-GEPPEmailNotification (the DEV role may invoke only that
    one — invoking PROD-… was AccessDenied on every DEV send), everything else (PROD,
    local) keeps the old PROD-GEPPEmailNotification default.
    """
    explicit = (os.environ.get('EMAIL_LAMBDA_FUNCTION') or '').strip()
    if explicit:
        return explicit
    caller = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', '')
    return 'DEV-GEPPEmailNotification' if caller.upper().startswith('DEV-') else 'PROD-GEPPEmailNotification'


def _settings(db=None) -> Tuple[bool, List[str]]:
    try:
        if db is None and not gs._cache_valid():
            from ...libs.database import get_session
            with get_session() as session:
                values = gs.get_all(session)
        else:
            values = gs.get_all(db)
        return (bool(values.get(gs.NOTIFICATION_EMAIL_ENABLED)),
                list(values.get(gs.NOTIFICATION_EMAIL_TEST_RECIPIENTS) or []))
    except Exception:
        logger.warning('Email gate could not read settings; using the code default', exc_info=True)
        return bool(gs.REGISTRY[gs.NOTIFICATION_EMAIL_ENABLED].default), []


def recipient_allowed(email: str, allowlist: List[str]) -> bool:
    email = (email or '').strip().lower()
    if not email or '@' not in email:
        return False
    domain = email.split('@', 1)[1]
    for entry in allowlist:
        if entry == email or entry.lstrip('@') == domain:
            return True
    return False


def gate_email_message(message: Dict[str, Any], db=None) -> Optional[Dict[str, Any]]:
    """The Mailchimp `message` as it may be sent, or None when nobody may receive it."""
    enabled, allowlist = _settings(db)
    if enabled:
        return message
    to = message.get('to') or []
    kept = [r for r in to if recipient_allowed((r or {}).get('email', ''), allowlist)]
    skipped = [(r or {}).get('email', '') for r in to if r not in kept]
    if skipped:
        # WARNING, not INFO: Lambda only shows WARNING+, and "why did nobody get the email"
        # must be answerable from CloudWatch. Domains only (no full addresses) at this level.
        domains = sorted({e.split('@', 1)[-1].lower() for e in skipped if '@' in e})
        logger.warning('Email gate: sending is OFF, %d of %d recipient(s) not on the test list '
                       'were skipped (domains: %s); %s; subject=%r',
                       len(skipped), len(to), ', '.join(domains) or '-',
                       f'still sent to {len(kept)}' if kept else 'nothing sent',
                       str(message.get('subject', ''))[:120])
        logger.info('Email gate skipped: %s', ', '.join(skipped))
    if not kept:
        return None
    return {**message, 'to': kept}
