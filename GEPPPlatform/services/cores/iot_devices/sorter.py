"""
ผู้คัดแยก (sorter) mode for the scale tablet.

A weigher records what arrives at a location. A sorter records what LEAVES one:
they stand at the building's waste room, sort the pile, and weigh each stream out
to where it actually goes. Same tablet, same screen, same app build — the only
difference is that the server hands them a list of DESTINATIONS where a weigher
gets a list of origins, and then reads the posted location back as a destination.

Two rules make that safe:

  1. The binding is a column on the user row (``sorter_location_id``), not a role
     in ``user_locations.members``. The members array is rewritten wholesale by the
     org-chart save and by the org-role cascade, so a role-based binding would be
     silently destroyed. See migration 079.

  2. The destination list the tablet is shown and the destination validated on
     write come from the SAME function here. If they could drift, a tablet could
     post a location it was never offered.

Everything degrades to "not a sorter" on any doubt: a missing binding, a deleted
or cross-org location, or a read failure all fall back to the normal weigher path
rather than guessing.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


def get_sorter_location_id(db_session, user_id: Any, organization_id: Any) -> Optional[int]:
    """The location this user sorts at, or None when they are a normal weigher.

    Validates in the same query that the bound location is still usable: same
    organization, active, not soft-deleted. A sorter whose waste room was deleted
    must fall back to the weigher path — not post material onto a dead location
    that reports will silently drop.

    The USER row is validated the same way: a deactivated sorter's still-live
    token must stop producing weigh-outs for a dead station — the tank balance
    counts every weigh-out as outflow, so a ghost account would silently drain a
    tank nobody can inspect.
    """
    if not user_id or not organization_id:
        return None
    try:
        row = db_session.execute(text(
            "SELECT loc.id "
            "FROM user_locations u "
            "JOIN user_locations loc ON loc.id = u.sorter_location_id "
            "WHERE u.id = :user_id "
            "  AND u.organization_id = :org_id "
            "  AND u.is_active = TRUE "
            "  AND u.deleted_date IS NULL "
            "  AND loc.organization_id = :org_id "
            "  AND loc.is_active = TRUE "
            "  AND loc.deleted_date IS NULL"
        ), {'user_id': user_id, 'org_id': organization_id}).fetchone()
    except Exception as exc:  # noqa: BLE001 — column added by migration 079
        logger.warning("[sorter] binding lookup failed for user %s: %s", user_id, exc)
        return None
    return int(row[0]) if row else None


def list_destinations(db_session, organization_id: Any) -> List[Dict[str, Any]]:
    """Destinations a sorter may ship to, in the EXACT shape the tablet already parses.

    Deliberately NOT ``TraceabilityService.get_destination_locations``: that one
    intersects with the caller's assigned locations, and a sorter is a member of
    their waste room only — the intersection is empty, so the tablet would show an
    empty picker. Authorisation here comes from holding the binding at all; the
    list is the organisation's destinations.

    Two sources, matching the rest of the platform's idea of "a destination":
      • ``type='hub'`` locations — external: recyclers, municipality, landfill
      • origin nodes flagged ``is_destination`` in the active organization_setup —
        internal points the org nominated as somewhere material can be sent

    Returned rows carry ``origin_id`` (not ``id``), plus ``display_name``, ``path``,
    ``tags`` and ``tenants`` — the tablet's location model requires all five and
    throws on a missing key. Tags/tenants are empty for destinations: they describe
    who generated material at an origin, which is meaningless for a drop-off point.
    """
    if not organization_id:
        return []

    hub_rows = []
    try:
        hub_rows = db_session.execute(text(
            "SELECT id, COALESCE(NULLIF(display_name, ''), name_en, name_th, '') AS label "
            "FROM user_locations "
            "WHERE organization_id = :org_id AND is_location = TRUE AND type = 'hub' "
            "  AND is_active = TRUE AND deleted_date IS NULL"
        ), {'org_id': organization_id}).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[sorter] hub destination lookup failed for org %s: %s", organization_id, exc)

    flagged_ids = _flagged_destination_ids(db_session, organization_id)
    flagged_rows = []
    if flagged_ids:
        try:
            flagged_rows = db_session.execute(text(
                "SELECT id, COALESCE(NULLIF(display_name, ''), name_en, name_th, '') AS label "
                "FROM user_locations "
                "WHERE organization_id = :org_id AND id = ANY(:ids) "
                "  AND is_active = TRUE AND deleted_date IS NULL"
            ), {'org_id': organization_id, 'ids': list(flagged_ids)}).fetchall()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[sorter] flagged destination lookup failed for org %s: %s", organization_id, exc)

    by_id: Dict[int, str] = {}
    for row in list(hub_rows) + list(flagged_rows):
        by_id.setdefault(int(row[0]), row[1] or f"Location {row[0]}")

    return [
        {
            'origin_id': loc_id,
            'display_name': label,
            'path': '',
            'tags': [],
            'tenants': [],
        }
        for loc_id, label in sorted(by_id.items(), key=lambda kv: kv[1])
    ]


def is_allowed_destination(db_session, organization_id: Any, location_id: Any) -> bool:
    """Whether a sorter may ship to this location — same list the picker was built from.

    Called on write. Without it the destination is whatever the client posted: the
    record path stores ``destination_id`` verbatim with no existence, org or
    liveness check of its own.
    """
    try:
        target = int(location_id)
    except (TypeError, ValueError):
        return False
    return any(d['origin_id'] == target for d in list_destinations(db_session, organization_id))


def _flagged_destination_ids(db_session, organization_id: Any) -> set:
    """Node ids flagged ``is_destination`` anywhere in the active org setup tree."""
    try:
        row = db_session.execute(text(
            "SELECT root_nodes FROM organization_setup "
            "WHERE organization_id = :org_id AND is_active = TRUE AND deleted_date IS NULL "
            "ORDER BY created_date DESC LIMIT 1"
        ), {'org_id': organization_id}).fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[sorter] setup read failed for org %s: %s", organization_id, exc)
        return set()

    found: set = set()

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get('is_destination'):
                # nodeId is written as int by some paths and str by others.
                try:
                    found.add(int(node.get('nodeId')))
                except (TypeError, ValueError):
                    pass
            walk(node.get('children'))

    walk((row[0] if row else None) or [])
    return found
