"""Platform-wide settings — one switch, one truth, read from `system_settings`.

**Every global setting is declared in `REGISTRY` below.** Nothing else can be
read or written. The registry is not ceremony: a settings page that accepts any
key would let a typo become a row that nothing honours, which presents to ops as
"I turned it off and nothing happened" — the worst possible failure mode for a
switch whose whole purpose is to stop an outage.

Three rules the call sites depend on:

  * **A missing row is not an error.** Every key has a code default, so a fresh
    database, a half-applied migration and a deleted row all behave identically.
    The table holds deliberate overrides only.
  * **A read never raises.** These are consulted on the request path, including
    inside the subscription gate. If this module cannot answer, the caller gets
    the default — a broken settings table must not decide who can log in.
  * **Values are typed by the registry, not by whatever is in the column.** A
    boolean setting coerces to a real bool on the way out, so no call site has
    to wonder whether the string "false" is truthy.

Caching: results are held for `CACHE_TTL_SECONDS` because Lambda containers are
reused and the subscription gate reads a setting on *every* request. The cost is
staleness — after flipping a switch, up to that many seconds of old behaviour
per warm container. Kept short deliberately: this switch exists to end a
lockout, and "wait a minute" is a very different promise from "wait a while".
`invalidate_cache()` is called on write so the container that made the change is
consistent immediately.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

#: How long a read is reused within one warm container.
CACHE_TTL_SECONDS = 30


def _as_bool(value: Any) -> bool:
    """Coerce whatever is in the column to a bool.

    JSONB gives back a real bool for `true`/`false`, but a hand-written row or
    an older client may hold the string. Anything unrecognised is False rather
    than truthy-by-accident: for a switch that restricts access, the safe
    reading of a corrupt value is "not enabled".
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'on')
    return False


_RECIPIENT = re.compile(r'^(?:[^@\s,;]+@)?@?[a-z0-9.-]+\.[a-z]{2,}$')


def _as_recipient_list(value: Any) -> List[str]:
    """A list of email addresses and/or domains ("@gepp.me"), lower-cased.

    Accepts a JSON list or free text separated by commas / spaces / new lines (what
    a textarea submits). Entries that are neither an address nor a domain are
    dropped rather than kept: an allowlist entry that can never match is a typo
    the operator should see disappear, not a silent no-op.
    """
    if isinstance(value, str):
        items = re.split(r'[\s,;]+', value)
    elif isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        return []
    out: List[str] = []
    for item in items:
        item = item.strip().lower()
        if item and _RECIPIENT.match(item) and item not in out:
            out.append(item)
    return out


def running_in_production() -> bool:
    """True on the PROD Lambdas (PROD-GEPPPlatform, its crons). DEV Lambdas and a
    local server (no AWS_LAMBDA_FUNCTION_NAME) are not production."""
    return os.environ.get('AWS_LAMBDA_FUNCTION_NAME', '').upper().startswith('PROD-')


def _email_default() -> bool:
    """Default for "Send emails" when no row is stored: EMAIL_SENDING_DEFAULT=on|off on the
    function wins; otherwise ON on production Lambdas, OFF everywhere else."""
    override = os.environ.get('EMAIL_SENDING_DEFAULT', '').strip().lower()
    if override in ('on', 'true', '1', 'yes'):
        return True
    if override in ('off', 'false', '0', 'no'):
        return False
    return running_in_production()


@dataclass(frozen=True)
class SettingSpec:
    """One declared global setting."""

    key: str
    #: Applies when no row exists. Also the value returned on any read failure.
    default: Any
    #: Coerces the stored value to the type call sites expect.
    coerce: Callable[[Any], Any]
    #: Backoffice tab this belongs to (the dotted key's first segment).
    section: str
    #: Shown next to the control. Says what happens when it is ON.
    label: str
    help_text: str = ''
    #: 'boolean' or 'string_list'; the UI switches on this.
    value_type: str = 'boolean'


#: The subscription access gate. ON = the policy from migration 088 (no period
#: covering today, no access at all). OFF = access continues, with the LAST
#: period's commercial terms still applied — see `limits.resolve_org_limits`.
SUBSCRIPTION_DISABLE_WHEN_NOT_IN_PERIOD = 'subscription.disable_when_not_in_period'

#: Outgoing email (every send path goes through `email_gate`). OFF = nothing is sent
#: except to the test recipients below — so testing on DEV cannot mail real users.
NOTIFICATION_EMAIL_ENABLED = 'notification.email_enabled'
#: Addresses / @domains that still receive email while sending is OFF.
NOTIFICATION_EMAIL_TEST_RECIPIENTS = 'notification.email_test_recipients'

REGISTRY: Dict[str, SettingSpec] = {
    SUBSCRIPTION_DISABLE_WHEN_NOT_IN_PERIOD: SettingSpec(
        key=SUBSCRIPTION_DISABLE_WHEN_NOT_IN_PERIOD,
        # OFF by default. Turning this on is a lockout, and a default that
        # locks people out on deploy is a default that gets reverted in a panic.
        default=False,
        coerce=_as_bool,
        section='subscription',
        label='Disable platform access when not in a subscription period',
        help_text=(
            'ON — an organization with no subscription period covering today '
            'cannot log in, and existing sessions stop working. Its QR forms '
            'stop accepting submissions too. '
            'OFF — access continues, and the organization keeps the limits from '
            'its most recent period rather than falling back to the more '
            'permissive system defaults.'
        ),
    ),
    NOTIFICATION_EMAIL_ENABLED: SettingSpec(
        key=NOTIFICATION_EMAIL_ENABLED,
        # Per environment: ON on production (deploying this must not silence real
        # mail), OFF on DEV / local (their data holds real users' addresses).
        default=_email_default(),
        coerce=_as_bool,
        section='notification',
        label='Send emails',
        help_text=(
            'ON — the platform sends every email (transaction notifications and '
            'approval digests, scheduled reports, password and invitation emails, '
            'location sharing, CRM). '
            'OFF — no email leaves the platform, except to the test recipients below; '
            'skipped emails are logged. Default: ON on production, OFF on DEV and '
            'local servers, so testing there cannot mail real users.'
        ),
    ),
    NOTIFICATION_EMAIL_TEST_RECIPIENTS: SettingSpec(
        key=NOTIFICATION_EMAIL_TEST_RECIPIENTS,
        default=[],
        coerce=_as_recipient_list,
        section='notification',
        label='Test recipients while sending is off',
        help_text=(
            'Email addresses or whole domains (e.g. tester@gepp.me, @gepp.me), one per '
            'line or comma-separated. While "Send emails" is OFF, only these receive '
            'mail, so emails can be tested without reaching customers. Ignored while '
            'sending is ON.'
        ),
        value_type='string_list',
    ),
}


# ── Cache ──────────────────────────────────────────────────────────────

_cache: Dict[str, Any] = {}
_cache_at: float = 0.0


def invalidate_cache() -> None:
    """Drop the cache. Called after a write, and available to tests."""
    global _cache, _cache_at
    _cache = {}
    _cache_at = 0.0


def _cache_valid() -> bool:
    return bool(_cache) and (time.monotonic() - _cache_at) < CACHE_TTL_SECONDS


# ── Reads ──────────────────────────────────────────────────────────────

def _load_all(db) -> Dict[str, Any]:
    """Raw stored values by key. Only registry keys; unknown rows are ignored.

    An unknown row is left in place rather than deleted: it is most likely a
    setting from a newer deploy that has since been rolled back, and destroying
    the operator's choice on a downgrade would be worse than ignoring it.
    """
    from sqlalchemy import text

    rows = db.execute(text('SELECT key, value FROM system_settings')).fetchall()
    out: Dict[str, Any] = {}
    for key, value in rows:
        if key not in REGISTRY:
            continue
        # psycopg2 decodes JSONB for us, so `value` is already a Python object
        # in the normal case. A str shows up when the stored JSON value IS a
        # string ('"true"' comes back as 'true'), or when something outside this
        # module wrote the column as text.
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                # Not JSON — keep the raw string and let the registry's
                # `coerce` decide. Parsing per row and tolerating a bad one
                # matters: raising here would abort the whole SELECT and reset
                # EVERY setting to its default, so one malformed row could
                # silently switch off an unrelated feature.
                pass
        out[key] = value
    return out


def get_all(db, use_cache: bool = True) -> Dict[str, Any]:
    """Every registry key resolved to its effective, coerced value.

    Never raises: on any failure every key resolves to its default and the
    reason is logged.
    """
    global _cache, _cache_at

    if use_cache and _cache_valid():
        stored = _cache
    else:
        try:
            stored = _load_all(db)
            if use_cache:
                _cache = stored
                _cache_at = time.monotonic()
        except Exception:
            logger.warning(
                'Could not read system_settings — using code defaults',
                exc_info=True)
            stored = {}

    return {
        key: spec.coerce(stored[key]) if key in stored else spec.default
        for key, spec in REGISTRY.items()
    }


def get_setting(db, key: str, use_cache: bool = True) -> Any:
    """One setting's effective value. Unknown key → None (not an exception).

    Deliberately quiet for an unknown key on the READ side, because reads happen
    on the request path; writes are strict instead, so a typo is caught where a
    human is watching.
    """
    spec = REGISTRY.get(key)
    if spec is None:
        logger.warning('Unknown global setting requested: %s', key)
        return None
    return get_all(db, use_cache=use_cache).get(key, spec.default)


def subscription_gate_enabled(db) -> bool:
    """Is the "no period, no access" policy currently switched on?"""
    return bool(get_setting(db, SUBSCRIPTION_DISABLE_WHEN_NOT_IN_PERIOD))


# ── Writes ─────────────────────────────────────────────────────────────

def set_setting(db, key: str, value: Any, updated_by: Optional[int] = None) -> Any:
    """Upsert one setting. Returns the coerced value now in force.

    Raises ValueError for a key not in the registry — see the module docstring.
    Does NOT commit: the caller owns the transaction, so a settings change can
    be rolled back with whatever else it was batched with.
    """
    from sqlalchemy import text

    spec = REGISTRY.get(key)
    if spec is None:
        raise ValueError(f'Unknown global setting: {key}')

    coerced = spec.coerce(value)

    db.execute(text("""
        INSERT INTO system_settings (key, value, updated_by, updated_date)
        VALUES (:key, CAST(:value AS jsonb), :updated_by, NOW())
        ON CONFLICT (key) DO UPDATE
           SET value        = EXCLUDED.value,
               updated_by   = EXCLUDED.updated_by,
               updated_date = NOW()
    """), {
        'key': key,
        # json.dumps, not str(): Python's `True` is not valid JSON.
        'value': json.dumps(coerced),
        'updated_by': updated_by,
    })

    invalidate_cache()
    return coerced


def set_many(db, values: Dict[str, Any],
             updated_by: Optional[int] = None) -> Dict[str, Any]:
    """Upsert several settings. Unknown keys are REJECTED, not skipped.

    Validated up front so a payload with one bad key writes nothing: a partial
    save on a settings form leaves the operator unable to tell what took effect.
    """
    unknown = [k for k in values if k not in REGISTRY]
    if unknown:
        raise ValueError(f'Unknown global setting(s): {", ".join(sorted(unknown))}')

    return {key: set_setting(db, key, value, updated_by=updated_by)
            for key, value in values.items()}


def describe(db) -> Dict[str, Any]:
    """Registry + current values + audit info, for the backoffice page.

    Grouped by section so the UI renders one tab per section without holding a
    second copy of the grouping.
    """
    from sqlalchemy import text

    current = get_all(db, use_cache=False)

    meta: Dict[str, Dict[str, Any]] = {}
    try:
        rows = db.execute(text("""
            SELECT key, updated_by, updated_date FROM system_settings
        """)).fetchall()
        for key, updated_by, updated_date in rows:
            meta[key] = {
                'updatedBy': updated_by,
                'updatedAt': updated_date.isoformat() if updated_date else None,
            }
    except Exception:
        logger.warning('Could not read system_settings audit columns',
                       exc_info=True)

    sections: Dict[str, Dict[str, Any]] = {}
    for key, spec in REGISTRY.items():
        section = sections.setdefault(
            spec.section, {'section': spec.section, 'settings': []})
        section['settings'].append({
            'key': key,
            'value': current[key],
            'default': spec.default,
            'valueType': spec.value_type,
            'label': spec.label,
            'helpText': spec.help_text,
            # Two independent facts, both worth showing and easy to conflate:
            #   isDefault  — the value in force equals the shipped default
            #   updatedAt  — somebody has written this key at some point
            # A key explicitly set back to its default is `isDefault: true`
            # AND has an `updatedAt`; "never touched" is isDefault with no
            # updatedAt. Deriving one from the other got this wrong.
            'isDefault': current[key] == spec.default,
            'everSet': key in meta,
            **meta.get(key, {}),
        })

    return {'sections': list(sections.values()), 'values': current}
