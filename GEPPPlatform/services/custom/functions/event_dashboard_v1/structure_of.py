"""
GET /structure-of — Extract sub-tree from organization setup

Returns the sub-tree rooted at the given user_location_id,
enriched with location data from the user_locations table.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def handle_structure_of(
    db_session: Session,
    organization_id: int,
    query_params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract sub-tree from organization setup for a given user_location_id.

    Query params:
    - user_location_id (required): Root node to extract
    """
    user_location_id = query_params.get('user_location_id')
    if not user_location_id:
        return {
            "success": False,
            "error": "MISSING_PARAM",
            "message": "user_location_id is required"
        }

    try:
        user_location_id = int(user_location_id)
    except (ValueError, TypeError):
        return {
            "success": False,
            "error": "INVALID_PARAM",
            "message": "user_location_id must be an integer"
        }

    # Fetch latest active organization setup
    from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup

    setup = db_session.query(OrganizationSetup).filter(
        OrganizationSetup.organization_id == organization_id,
        OrganizationSetup.is_active == True,
        OrganizationSetup.deleted_date.is_(None),
    ).order_by(OrganizationSetup.id.desc()).first()

    if not setup:
        return {
            "success": False,
            "error": "NO_SETUP",
            "message": f"No organization setup found for organization_id={organization_id}"
        }

    # DFS to find the target node in root_nodes and hub_node.children
    target_node = None
    root_nodes = setup.root_nodes or []
    hub_node = setup.hub_node or {}

    target_node = _find_node_by_id(root_nodes, str(user_location_id))
    if not target_node and hub_node.get('children'):
        target_node = _find_node_by_id(hub_node['children'], str(user_location_id))

    if not target_node:
        return {
            "success": False,
            "error": "NODE_NOT_FOUND",
            "message": f"Node with nodeId={user_location_id} not found in organization setup"
        }

    # Collect all descendant nodeIds
    descendant_ids = []
    _collect_node_ids(target_node, descendant_ids)

    # Enrich with location data from user_locations
    from GEPPPlatform.models.users.user_location import UserLocation

    location_map = {}
    if descendant_ids:
        int_ids = [int(nid) for nid in descendant_ids if nid and str(nid).isdigit()]
        if int_ids:
            locations = db_session.query(UserLocation).filter(
                UserLocation.id.in_(int_ids),
                UserLocation.deleted_date.is_(None),
            ).all()
            for loc in locations:
                location_map[str(loc.id)] = {
                    "name_en": loc.name_en if hasattr(loc, 'name_en') else None,
                    "display_name": loc.display_name if hasattr(loc, 'display_name') else None,
                    "type": loc.type if hasattr(loc, 'type') else None,
                    "address": loc.address if hasattr(loc, 'address') else None,
                }

    # Enrich nodes with location data
    enriched_node = _enrich_node(target_node, location_map)

    return {
        "success": True,
        "user_location_id": user_location_id,
        "node": enriched_node,
        "descendant_ids": [int(nid) for nid in descendant_ids if str(nid).isdigit()],
    }


def _find_node_by_id(nodes: List[Dict], target_id: str) -> Optional[Dict]:
    """DFS search for a node with matching nodeId."""
    for node in nodes:
        node_id = str(node.get('nodeId', ''))
        if node_id == target_id:
            return node
        children = node.get('children') or []
        found = _find_node_by_id(children, target_id)
        if found:
            return found
    return None


def _collect_node_ids(node: Dict, ids: List[str]) -> None:
    """Recursively collect all nodeIds from a tree node."""
    node_id = node.get('nodeId', '')
    if node_id:
        ids.append(str(node_id))
    for child in (node.get('children') or []):
        _collect_node_ids(child, ids)


def _enrich_node(node: Dict, location_map: Dict[str, Dict]) -> Dict:
    """Recursively enrich tree nodes with location data."""
    node_id = str(node.get('nodeId', ''))
    loc_data = location_map.get(node_id, {})

    enriched = {
        "id": int(node_id) if node_id and str(node_id).isdigit() else node_id,
        "name": loc_data.get("display_name") or loc_data.get("name_en") or node.get("name", ""),
        "name_en": loc_data.get("name_en"),
        "display_name": loc_data.get("display_name"),
        "level": loc_data.get("type") or node.get("type"),
        "address": loc_data.get("address"),
    }

    children = node.get('children') or []
    if children:
        enriched["children"] = [_enrich_node(child, location_map) for child in children]

    # Preserve extra fields from setup
    for key in ('is_destination', 'hub_type', 'hubData', 'edge_to_children'):
        if key in node:
            enriched[key] = node[key]

    return enriched
