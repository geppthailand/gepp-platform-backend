"""Tag/tenant read scope for the daily scale summary.

A member of a location sees that location's whole intake — unchanged, decided by
the route's `member_origin_ids()` gate. Someone who reaches the location ONLY
through a tag/tenant grant (typically a tenant's own PIN user) used to get a 401.
They now get the summary narrowed to the records carrying *their* tag/tenant,
inside each grant's date window — never the other tenants' weights at the same
site, which is why the whole-location gate existed in the first place.

The row filter is `libs.locationAccess.build_visibility_clause()`, the same
predicate the web reports use, so the tablet, the QR page and the web cannot
disagree about who sees what.
"""

from datetime import date, datetime, time
from typing import Any, Dict, Optional

from GEPPPlatform.libs.locationAccess import build_visibility_clause, is_window_active
from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
from GEPPPlatform.models.transactions.transactions import Transaction
from GEPPPlatform.services.cores.users.user_service import UserService

from .scale_report_service import descendant_origin_ids


def grant_covers_day(grant: Dict[str, Any], day: date) -> bool:
    """Does the grant's [start_date, end_date] window overlap the Thai calendar `day`?

    Two single-bound checks instead of one instant: a tenant whose window opens at
    noon must still see that day, and so must one whose window closed that day.
    """
    day_start = datetime.combine(day, time.min)
    day_end = datetime.combine(day, time.max)
    return (
        is_window_active(grant.get('start_date'), None, day_end)
        and is_window_active(None, grant.get('end_date'), day_start)
    )


def resolve_scoped_summary(
    db_session,
    user_id: Any,
    organization_id: Any,
    origin_id: Any,
    day: date,
) -> Optional[Dict[str, Any]]:
    """Narrowed read access to `origin_id`'s summary on `day`, or None.

    Only for callers that are NOT members of the location (members keep the full
    summary). Counts the user's tag/tenant grants attached anywhere in the
    location's subtree whose window overlaps `day`.

    Returns:
        {'clause': <SQLAlchemy predicate for get_daily_summary(visibility=...)>,
         'grants': [{'kind', 'id', 'name'}, ...]}
        or None when there is no such grant — the caller keeps refusing with 401.
    """
    scope = UserService(db_session).resolve_access_scope(int(organization_id), int(user_id))
    if scope.get('is_owner'):
        # Owners are decided by the caller's existing rule; this path is for
        # tag/tenant members only.
        return None

    subtree = set(descendant_origin_ids(db_session, int(organization_id), int(origin_id)))
    grants = [
        g for g in (scope.get('scoped_grants') or [])
        if subtree & set(g.get('location_ids') or ()) and grant_covers_day(g, day)
    ]
    if not grants:
        return None

    clause = build_visibility_clause(
        {**scope, 'scoped_grants': grants},
        Transaction.origin_id,
        Transaction.location_tag_id,
        Transaction.tenant_id,
        TransactionRecord.transaction_date,
    )
    return {
        'clause': clause,
        'grants': [
            {'kind': g.get('kind'), 'id': g.get('id'), 'name': g.get('name')}
            for g in grants
        ],
    }
