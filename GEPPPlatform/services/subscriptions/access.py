"""Does this organization have a live subscription right now?

Policy: **no subscription period covering today means no access.** The user
cannot log in to the business platform, and an existing session cannot do
anything either — a token issued yesterday must not outlive the subscription.

This replaced auto-renewal. Rolling a lapsed period forward automatically kept
the platform working but invented commercial terms nobody agreed; refusing
access makes the lapse visible and puts a human in the loop. Staff create the
next period in the backoffice `Subscription` tab.

**The whole policy is behind one global switch**, Global Settings →
Subscription → *disable when not in period* (see
`services/settings/global_settings.py`). Switched off — the shipped default —
nobody is blocked, and a lapsed org instead keeps the commercial terms of its
most recent period (`limits.resolve_org_limits` falls back to it) rather than
silently reverting to the more permissive system defaults. It has to be a
switch and not a constant: on today's data turning it on blocks 237
organizations, and a policy with that blast radius must be reversible by an
operator in seconds, not by a deploy.

**Two things must never be gated by this, or the system deadlocks:**

  * ``/api/admin/*`` — the backoffice is where the period gets created. Gating
    it would mean a lapsed org can only be fixed by someone who cannot log in
    to fix it. Backoffice staff authenticate as platform admins, not as members
    of the customer org, so they are a separate population anyway.
  * the auth routes themselves — logging out, refreshing and validating a token
    have to keep working for a blocked user, or the client cannot even clear
    its session and show the message.

`ALWAYS_ALLOWED_PREFIXES` is the whole allowlist and is deliberately short:
every addition is a hole in the policy.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

#: Paths that stay reachable for an organization with no live subscription.
#: Order matters only for readability; matching is a plain prefix test.
ALWAYS_ALLOWED_PREFIXES = (
    '/api/admin',        # backoffice — creates the period that unblocks the org
    '/api/auth',         # login/logout/refresh/validate must keep answering
    '/health',
)

#: Returned to the client so it can show the right screen rather than parse prose.
BLOCKED_ERROR_CODE = 'NO_ACTIVE_SUBSCRIPTION'


def path_is_always_allowed(path: str) -> bool:
    """True for paths that must never be subscription-gated.

    Matched on a path BOUNDARY, not a bare prefix: `startswith('/api/admin')`
    also accepts `/api/adminfoo`, and an allowlist that can be widened by
    appending characters is not an allowlist.
    """
    if not path:
        return False
    return any(path == prefix or path.startswith(prefix + '/')
               for prefix in ALWAYS_ALLOWED_PREFIXES)


def gate_enabled(db) -> bool:
    """Is the "no period, no access" policy switched on globally?

    Fails OPEN by returning False — an unreadable settings table means nobody
    is blocked, which is the same direction every other failure in this module
    resolves. `global_settings` already swallows its own errors; this second
    guard covers the import itself failing on a partially deployed release.
    """
    try:
        from ..settings.global_settings import subscription_gate_enabled
        return subscription_gate_enabled(db)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'Could not read the subscription gate setting — treating as OFF',
            exc_info=True)
        return False


def subscription_access(db, organization_id: Optional[int],
                        as_of: Optional[date] = None) -> Dict[str, Any]:
    """`{'allowed': bool, 'reason': str, ...}` for one organization.

    Reasons, all distinguishable because they need different messages:

        gate_disabled       the global switch is off — nobody is blocked
        ok                  a period covers today
        no_organization     the caller has no org — cannot be judged, allowed
        never_subscribed    the org has no periods at all
        lapsed              it had one, and it ended (the common case)
        not_started         its only period begins in the future

    Fails OPEN. If the check itself errors — a bad session, a migration not yet
    applied — access is granted rather than denied. A bug in a gate must not
    take every customer offline; the limits and billing paths degrade to
    defaults in the same situation.
    """
    # The switch is checked FIRST, before the org is even looked at: when it is
    # off — the default — this must cost nothing on the request path, and the
    # answer cannot depend on the org's data anyway.
    if not gate_enabled(db):
        return {'allowed': True, 'reason': 'gate_disabled'}

    if not organization_id:
        # No org to judge — service accounts and IoT devices authenticate as
        # themselves. NOT the QR channel: a channel row carries
        # `organization_id`, so it is resolved and gated like any other caller
        # (see `channel_subscription_access`).
        return {'allowed': True, 'reason': 'no_organization'}

    try:
        from .limits import find_period
        from ...models.subscriptions.subscription_models import Subscription

        as_of = as_of or datetime.now(timezone.utc).date()

        if find_period(db, organization_id, at=as_of) is not None:
            return {'allowed': True, 'reason': 'ok'}

        latest = (
            db.query(Subscription)
            .filter(Subscription.organization_id == organization_id,
                    Subscription.deleted_date.is_(None),
                    Subscription.current_period_starts_at.isnot(None))
            .order_by(Subscription.current_period_starts_at.desc(),
                      Subscription.id.desc())
            .first()
        )

        if latest is None:
            return {
                'allowed': False,
                'reason': 'never_subscribed',
                'organization_id': organization_id,
            }

        starts = latest.current_period_starts_at
        ends = latest.current_period_ends_at
        starts_d = starts.date() if hasattr(starts, 'date') else starts

        if starts_d and starts_d > as_of:
            return {
                'allowed': False,
                'reason': 'not_started',
                'organization_id': organization_id,
                'starts_at': starts.isoformat() if starts else None,
            }

        return {
            'allowed': False,
            'reason': 'lapsed',
            'organization_id': organization_id,
            'ended_at': ends.isoformat() if ends else None,
        }

    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'Subscription access check failed for org %s — allowing access',
            organization_id, exc_info=True)
        return {'allowed': True, 'reason': 'check_failed'}


def blocked_message(decision: Dict[str, Any], audience: str = 'member') -> str:
    """English fallback prose. Clients should key off `error_code`/`reason`
    and render their own localized copy.

    `audience` matters because two very different people hit this:

      * `member` — someone logging in to the platform, who can plausibly chase
        a renewal;
      * `channel` — whoever scanned a QR at a collection point. They are site
        staff or a contractor, have no idea what a subscription period is, and
        can do nothing about it. Telling them to "contact GEPP to renew" sends
        them to the wrong place, so they are pointed at the organization that
        gave them the code.
    """
    reason = decision.get('reason')

    if audience == 'channel':
        return ('This QR form is not currently active. Please contact the '
                'organization that provided this code.')

    if reason == 'not_started':
        starts = (decision.get('starts_at') or '')[:10]
        return (f'This organization\'s subscription starts on {starts}. '
                'Please contact GEPP to begin it earlier.')
    if reason == 'never_subscribed':
        return ('This organization does not have a subscription yet. '
                'Please contact GEPP to set one up.')
    ended = (decision.get('ended_at') or '')[:10]
    return (f'This organization\'s subscription ended{" on " + ended if ended else ""}. '
            'Please contact GEPP to renew it.')


def channel_subscription_access(db, channel_hash: Optional[str],
                                as_of: Optional[date] = None) -> Dict[str, Any]:
    """Subscription decision for a QR input channel, resolved from its hash.

    The QR form is unauthenticated, but the channel row it is keyed by carries
    `organization_id` — so "whose subscription is this?" is answerable, and a
    channel belonging to a lapsed organization must stop working like every
    other way into that org. Otherwise the QR is a hole straight past the gate.

    Only `organization_id` is selected: this runs before the channel is loaded
    for real, on every QR request.

    Fails OPEN, like `subscription_access`: an unknown or unreadable hash is
    allowed through, and the route's own 404/401 handling deals with it.
    """
    # Checked here as well as inside `subscription_access` so that with the
    # switch off a QR submission costs zero extra queries — this is the highest
    # volume public path in the platform.
    if not gate_enabled(db):
        return {'allowed': True, 'reason': 'gate_disabled'}

    if not channel_hash:
        return {'allowed': True, 'reason': 'no_channel'}

    try:
        from sqlalchemy import text

        row = db.execute(text("""
            SELECT organization_id
              FROM user_input_channels
             WHERE hash = :hash
               AND deleted_date IS NULL
             LIMIT 1
        """), {'hash': channel_hash}).fetchone()

        if row is None or not row[0]:
            return {'allowed': True, 'reason': 'channel_not_found'}

        decision = subscription_access(db, int(row[0]), as_of=as_of)
        decision['channel_hash'] = channel_hash
        return decision

    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'Channel subscription check failed for hash %s — allowing',
            channel_hash, exc_info=True)
        return {'allowed': True, 'reason': 'check_failed'}
