"""Collection points ("ถัง") — the one predicate the tank model hangs on.

A collection point is a location that material is gathered AT before being
weighed OUT again: the building's waste room, a floor's sorting corner. Two
configurations make a location one, and only these two:

  • it is some location's ห้องขยะ target (user_locations.waste_room_location_id), or
  • an ACTIVE user sorts there (user_locations.sorter_location_id).

Deliberately NOT membership-based: dataInput members exist on ordinary
destinations too, and a scrap dealer with a data-entry account must never be
classified as a tank — that is exactly the misclassification that would turn a
terminal leg into a "delivered to collection" one and lose the disposal method.

Everything that creates or repoints a traceability leg asks this predicate and
stamps ``delivered_to_collection`` accordingly (design §3, channel-independent:
scale auto-hops, web drags and consolidation results all get the same answer).
Reads are raw SQL with explicit column lists so a session running ahead of
migration 079/081 degrades to "not a collection point" instead of failing the
caller's write.
"""

import logging
from typing import Any, Iterable, Optional, Set

from sqlalchemy import text

logger = logging.getLogger(__name__)


def collection_point_ids(db_session, organization_id: Any, candidate_ids: Optional[Iterable[Any]] = None) -> Set[int]:
    """The org's collection points, optionally intersected with candidates.

    One query for a whole batch of hops — callers with several destinations in
    flight (the auto-hop bucket loop, a consolidation request list) must not
    pay a query per leg.
    """
    if not organization_id:
        return set()

    cands: Optional[Set[int]] = None
    if candidate_ids is not None:
        cands = set()
        for c in candidate_ids:
            try:
                cands.add(int(c))
            except (TypeError, ValueError):
                continue
        if not cands:
            return set()

    found: Set[int] = set()

    # ห้องขยะ targets. Separate best-effort reads: the two bindings arrived in
    # different migrations and must degrade independently.
    try:
        rows = db_session.execute(text(
            "SELECT DISTINCT waste_room_location_id FROM user_locations "
            "WHERE organization_id = :org_id "
            "  AND waste_room_location_id IS NOT NULL "
            "  AND is_active = TRUE AND deleted_date IS NULL"
        ), {'org_id': organization_id}).fetchall()
        found.update(int(r[0]) for r in rows if r[0] is not None)
    except Exception as exc:  # noqa: BLE001 — column added by migration 081
        logger.warning("[collection_points] waste-room read failed for org %s: %s", organization_id, exc)

    # Active sorters' stations.
    try:
        rows = db_session.execute(text(
            "SELECT DISTINCT sorter_location_id FROM user_locations "
            "WHERE organization_id = :org_id "
            "  AND sorter_location_id IS NOT NULL "
            "  AND is_active = TRUE AND deleted_date IS NULL"
        ), {'org_id': organization_id}).fetchall()
        found.update(int(r[0]) for r in rows if r[0] is not None)
    except Exception as exc:  # noqa: BLE001 — column added by migration 079
        logger.warning("[collection_points] sorter read failed for org %s: %s", organization_id, exc)

    return found if cands is None else (found & cands)


def is_collection_point(db_session, location_id: Any, organization_id: Any) -> bool:
    """Single-location convenience over collection_point_ids."""
    if not location_id:
        return False
    return bool(collection_point_ids(db_session, organization_id, [location_id]))
