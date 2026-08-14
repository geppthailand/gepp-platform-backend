"""Reading node ids out of organization_setup.root_nodes.

The org chart is JSON, not rows, and the web app addresses a node it has just
created with a temporary client-side id — `"2186_1768891622748_hub-child-1"` —
until the save pipeline swaps in the real database id. When one of those
survives into the stored tree, every walker that does `int(node['nodeId'])`
raises ValueError and takes the whole request down with it: a 500 on the
locations list is an empty screen, not a missing node.

Three call sites had already grown their own private copy of this before it was
worth naming. This is that helper, once.
"""

from typing import Any, Optional


def to_node_id(value: Any) -> Optional[int]:
    """Return the node id as an int, or None if it is not one.

    None means "this node cannot be matched against a database id" — a temporary
    id from an unsaved node, a placeholder, or junk. Callers skip it. Skipping is
    right rather than lossy: a node with no real id has no location row behind
    it, so there is nothing to show or match anyway.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
