"""Resolve an organization's usage limits for a given date.

**This is the only place the precedence question is answered.** Four call sites
ask it — presigned upload, the base64/QR upload, the backoffice, and the usage
report — and drifting copies of the rule would stay invisible until an invoice
came out wrong.

Precedence, most specific first:

    1. the subscription period covering the date  (the contract)
    1b. its most recent period that has ended     (only when the global access
                                                   gate is OFF — a lapsed org
                                                   that is still allowed to work
                                                   keeps its last agreed terms
                                                   instead of gaining the more
                                                   permissive defaults)
    2. the organization's default                 (house standard)
    3. the system default                         (last resort)

A NULL at any layer falls through to the next. A deliberate ``0`` does NOT: it
is a real value meaning "none allowed", which is why every column is nullable
rather than defaulted in the schema.

The two limits are not symmetric, and callers must not treat them alike:

    transactions_per_month   ADVISORY. Never blocks. Feeds billing.
    max_file_size_mb         ENFORCED, and a TOTAL: the combined size of all
                             files on one transaction. Over it, the whole
                             transaction is refused.

`max_image_dimension_px` has no period layer by design — it is a storage
concern, not a billed one, and per-period values would mean the same photo is
kept at different resolutions depending on when it was sent.
"""

from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import or_

# ── System defaults ───────────────────────────────────────────────────
#
# Chosen to be permissive: this feature must not tighten anything for an org
# nobody has configured yet. The file-size default matches the 50 MB that
# `presigned_url_service` hardcoded before this existed, so behaviour for
# unconfigured orgs is unchanged rather than newly restricted (it was a
# per-object cap there and is a per-transaction total now, which is
# stricter in principle but not for any org at the default).

DEFAULT_TRANSACTIONS_PER_MONTH = 100
DEFAULT_MAX_FILE_SIZE_MB = 50.0
DEFAULT_MAX_IMAGE_DIMENSION_PX = 1920

#: Floor for the image cap. Below this a photo of a weighing-scale display stops
#: being legible, which defeats the point of collecting it.
MIN_IMAGE_DIMENSION_PX = 320


@dataclass(frozen=True)
class OrgLimits:
    """Effective limits for one org at one date, plus where each came from."""

    organization_id: int
    #: Transactions allowed per month. ADVISORY — see module docstring.
    transactions_per_month: int
    #: Max COMBINED attachment size for one transaction, MB. ENFORCED.
    max_file_size_mb: float
    #: Longest-edge cap for re-encoded images, px.
    max_image_dimension_px: int

    #: The period row that supplied values, if any. None = no period covers the
    #: date, so the org/system defaults are in force.
    subscription_id: Optional[int] = None
    plan_id: Optional[int] = None
    #: 'period' | 'last_period' | 'organization' | 'system', per limit. Ops asks
    #: "why is this number what it is?" often enough that guessing is not good
    #: enough. `last_period` means no period covers the date and the global
    #: access gate is off, so the org is running on its most recent terms.
    transactions_source: str = 'system'
    file_size_source: str = 'system'
    image_dimension_source: str = 'system'
    #: True when the values above came from a period that has already ended.
    from_expired_period: bool = False

    @property
    def max_file_size_bytes(self) -> int:
        """The enforced value, in the unit S3 and byte-length checks need."""
        return int(self.max_file_size_mb * 1024 * 1024)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['max_file_size_bytes'] = self.max_file_size_bytes
        return d


def _first_not_none(*candidates):
    """(value, source) for the first candidate whose value is not None.

    Explicitly not `or`-chaining: 0 and 0.0 are meaningful values here, and
    `a or b` would skip right past them.
    """
    for value, source in candidates:
        if value is not None:
            return value, source
    return None, 'system'


def find_period(db, organization_id: int, at: Optional[date] = None):
    """The subscription period covering `at`, or None.

    Overlaps are possible (nothing in the schema forbids two periods sharing a
    day, and back-dated corrections are a legitimate reason to allow it), so the
    tie is broken deterministically: latest start wins, then highest id. That
    makes the most recently agreed contract authoritative, which is what ops
    means by "the current one".

    A period with a NULL end is open-ended. A period with a NULL start is
    ignored rather than treated as beginning at the epoch — an unbounded row
    would otherwise silently capture every date.
    """
    from ...models.subscriptions.subscription_models import Subscription

    at = at or datetime.now(timezone.utc).date()

    return (
        db.query(Subscription)
        .filter(
            Subscription.organization_id == organization_id,
            Subscription.deleted_date.is_(None),
            Subscription.current_period_starts_at.isnot(None),
            Subscription.current_period_starts_at <= _end_of_day(at),
            or_(
                Subscription.current_period_ends_at.is_(None),
                Subscription.current_period_ends_at >= _start_of_day(at),
            ),
        )
        .order_by(
            Subscription.current_period_starts_at.desc(),
            Subscription.id.desc(),
        )
        .first()
    )


def latest_started_period(db, organization_id: int, at: Optional[date] = None):
    """The most recent period that has BEGUN by `at`, expired or not.

    Used when no period covers the date and the global subscription gate is
    switched off: the org keeps working, and this is whose terms it works
    under. Falling through to the org/system defaults instead would silently
    *loosen* the limits of a lapsed customer — the system file-size default is
    50 MB, so an org contracted to 5 MB would gain ten times the allowance by
    letting its subscription expire. That is the wrong direction for a lapse.

    Deliberately ignores periods that start in the FUTURE, even though they may
    be the latest by start date: a scheduled contract has not been agreed to
    take effect yet, and applying its terms early is the same class of mistake
    as inventing them.
    """
    from ...models.subscriptions.subscription_models import Subscription

    at = at or datetime.now(timezone.utc).date()

    return (
        db.query(Subscription)
        .filter(
            Subscription.organization_id == organization_id,
            Subscription.deleted_date.is_(None),
            Subscription.current_period_starts_at.isnot(None),
            Subscription.current_period_starts_at <= _end_of_day(at),
        )
        .order_by(
            Subscription.current_period_starts_at.desc(),
            Subscription.id.desc(),
        )
        .first()
    )


def _start_of_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _end_of_day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def resolve_org_limits(db, organization_id: int, at: Optional[date] = None,
                       period=None,
                       fall_back_to_last_period: Optional[bool] = None) -> OrgLimits:
    """Effective limits for `organization_id` on `at`.

    Pass `period` when the caller already has the row (the backoffice detail
    view does) to skip the lookup; it is not re-validated against `at`.

    `fall_back_to_last_period` decides what happens when NO period covers `at`:

        None   read the global subscription gate — fall back whenever the gate
               is OFF, because then a lapsed org is still working and has to
               work under *some* agreed terms. This is the default and the only
               value any production call site passes.
        True   force the fallback.
        False  no fallback: the org/system defaults apply.

    Tied to the gate rather than being its own switch on purpose — one operator
    decision ("do lapsed orgs keep working?") should not need a second one
    ("...and under which limits?") to be coherent.
    """
    from ...models.subscriptions.organizations import Organization

    org = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )

    period_source = 'period'
    from_expired = False

    if period is None:
        period = find_period(db, organization_id, at)

        if period is None:
            if fall_back_to_last_period is None:
                from .access import gate_enabled
                fall_back_to_last_period = not gate_enabled(db)

            if fall_back_to_last_period:
                period = latest_started_period(db, organization_id, at)
                if period is not None:
                    period_source = 'last_period'
                    from_expired = True

    txn, txn_src = _first_not_none(
        (getattr(period, 'create_transaction_limit', None), period_source),
        (getattr(org, 'default_transaction_limit_per_month', None), 'organization'),
        (DEFAULT_TRANSACTIONS_PER_MONTH, 'system'),
    )
    size, size_src = _first_not_none(
        (getattr(period, 'max_file_size_mb', None), period_source),
        (getattr(org, 'default_max_file_size_mb', None), 'organization'),
        (DEFAULT_MAX_FILE_SIZE_MB, 'system'),
    )
    dim, dim_src = _first_not_none(
        (getattr(org, 'max_image_dimension_px', None), 'organization'),
        (DEFAULT_MAX_IMAGE_DIMENSION_PX, 'system'),
    )

    return OrgLimits(
        organization_id=organization_id,
        transactions_per_month=int(txn),
        max_file_size_mb=float(size),
        max_image_dimension_px=max(int(dim), MIN_IMAGE_DIMENSION_PX),
        subscription_id=getattr(period, 'id', None),
        plan_id=getattr(period, 'plan_id', None),
        transactions_source=txn_src,
        file_size_source=size_src,
        image_dimension_source=dim_src,
        # Only true if a limit actually came from that row: a period with both
        # limits NULL contributes nothing, so flagging it would misreport where
        # the numbers came from.
        from_expired_period=from_expired and 'last_period' in (txn_src, size_src),
    )


def months_in_period(start: Optional[date], end: Optional[date],
                     cap_at: Optional[date] = None) -> int:
    """Whole calendar months a period touches, inclusive of both ends.

    A period is billed per month, so a range of 2026-01-15 → 2026-03-02 covers
    THREE months (Jan, Feb, Mar) — it drew on the January allowance and the
    March one, however few days it used of each. Counting 30-day blocks instead
    would bill 1.5 months and satisfy nobody.

    An open-ended period is capped at `cap_at` (default today) so a running
    contract reports what it has consumed so far rather than nothing.
    """
    if start is None:
        return 0
    cap_at = cap_at or datetime.now(timezone.utc).date()
    end = end or cap_at
    if end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def period_transaction_allowance(period, cap_at: Optional[date] = None,
                                 per_month: Optional[int] = None) -> Optional[int]:
    """Total transactions allowed across a whole period.

    ``per_month x months touched``. Derived on every read rather than stored, so
    editing the date range can never leave a stale total behind. None when
    there is no monthly allowance to multiply.
    """
    if period is None:
        return None
    monthly = per_month if per_month is not None else getattr(
        period, 'create_transaction_limit', None)
    if monthly is None:
        return None
    start = _as_date(getattr(period, 'current_period_starts_at', None))
    end = _as_date(getattr(period, 'current_period_ends_at', None))
    return int(monthly) * months_in_period(start, end, cap_at)


def _as_date(value) -> Optional[date]:
    """Coerce a column that has been a str in this schema's past to a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except (TypeError, ValueError):
        return None
