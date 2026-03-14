"""
Recycling Rate Helper — 3-tier calculation integrating traceability data.

Tier 1: Record has traceability_group_id AND group is fully traced
        → Use leaf disposal_method classification weighted by absolute_percentage
Tier 2: Record has traceability_group_id BUT group is NOT fully traced
        → Traced portion uses disposal methods, untraced falls back to category
Tier 3: Record has NO traceability_group_id
        → Old category-based: cat_id in (1, 3) = recyclable
"""

from typing import Dict, List, Optional, Set, Tuple

# "Diverted from Disposal" = recyclable
DIVERTED_METHODS = {
    "Preparation for reuse",
    "Recycling (Own)",
    "Other recover operation",
    "Recycle",
}

# "Directed to Disposal" = non-recyclable
DIRECTED_METHODS = {
    "Composted by municipality",
    "Municipality receive",
    "Incineration without energy",
    "Incineration with energy",
}

_RECYCLABLE_CATEGORIES = {1, 3}


def compute_recycling_rate(
    record_weights: List[Tuple[float, float, Optional[int], Optional[int]]],
    group_leaf_data: Dict[int, List[dict]],
    group_completion: Dict[int, float],
) -> Tuple[float, float, float, bool]:
    """
    3-tier recycling rate calculation.

    Parameters:
    - record_weights: list of (weight, calc_ghg_per_kg, category_id, traceability_group_id)
    - group_leaf_data: {group_id: [{"disposal_method", "absolute_percentage", "status"}]}
    - group_completion: {group_id: completion_rate_0_to_1}

    Returns: (recyclable_weight, recyclable_ghg, total_weight, all_fully_traced)
    - all_fully_traced: True only if EVERY record has a traceability_group_id
      with completion == 1.0. False if any record lacks a group or has incomplete tracing.
    """
    total_weight = 0.0
    recyclable_weight = 0.0
    recyclable_ghg = 0.0
    has_untraced = False
    has_incomplete = False

    for weight, calc_ghg, cat_id, group_id in record_weights:
        total_weight += weight

        if group_id is not None and group_id in group_leaf_data:
            completion = group_completion.get(group_id, 0.0)
            if completion < 1.0:
                has_incomplete = True
            leaves = group_leaf_data[group_id]

            # Traced portion: sum absolute_percentage of diverted leaves
            traced_recyclable_pct = 0.0
            for leaf in leaves:
                method = (leaf.get("disposal_method") or "").strip()
                abs_pct = float(leaf.get("absolute_percentage") or 0)
                status = leaf.get("status") or ""
                if status == "arrived" and method and method in DIVERTED_METHODS:
                    traced_recyclable_pct += abs_pct

            recyclable_from_traced = weight * (traced_recyclable_pct / 100.0)
            ghg_from_traced = recyclable_from_traced * calc_ghg

            # Untraced portion: fallback to category
            untraced_fraction = 1.0 - completion
            recyclable_from_untraced = 0.0
            ghg_from_untraced = 0.0
            if untraced_fraction > 0 and cat_id in _RECYCLABLE_CATEGORIES:
                recyclable_from_untraced = weight * untraced_fraction
                ghg_from_untraced = recyclable_from_untraced * calc_ghg

            recyclable_weight += recyclable_from_traced + recyclable_from_untraced
            recyclable_ghg += ghg_from_traced + ghg_from_untraced
        else:
            # Tier 3: no traceability → old category method
            has_untraced = True
            if cat_id in _RECYCLABLE_CATEGORIES:
                recyclable_weight += weight
                recyclable_ghg += weight * calc_ghg

    all_fully_traced = not has_untraced and not has_incomplete
    return recyclable_weight, recyclable_ghg, total_weight, all_fully_traced


def is_record_recyclable(
    weight: float,
    cat_id: Optional[int],
    group_id: Optional[int],
    group_leaf_data: Dict[int, List[dict]],
    group_completion: Dict[int, float],
) -> float:
    """
    Determine recyclable weight for a single record using the 3-tier logic.
    Used for per-record attribution (e.g. origin_waste_map).

    Returns the recyclable portion of weight.
    """
    if group_id is not None and group_id in group_leaf_data:
        completion = group_completion.get(group_id, 0.0)
        leaves = group_leaf_data[group_id]

        traced_recyclable_pct = 0.0
        for leaf in leaves:
            method = (leaf.get("disposal_method") or "").strip()
            abs_pct = float(leaf.get("absolute_percentage") or 0)
            status = leaf.get("status") or ""
            if status == "arrived" and method and method in DIVERTED_METHODS:
                traced_recyclable_pct += abs_pct

        recyclable = weight * (traced_recyclable_pct / 100.0)

        untraced_fraction = 1.0 - completion
        if untraced_fraction > 0 and cat_id in _RECYCLABLE_CATEGORIES:
            recyclable += weight * untraced_fraction

        return recyclable
    else:
        if cat_id in _RECYCLABLE_CATEGORIES:
            return weight
        return 0.0


def fetch_group_leaf_data(db, group_ids: Set[int]) -> Tuple[Dict[int, List[dict]], Dict[int, float]]:
    """
    For a set of group_ids, fetch all leaf transport_transactions
    and compute completion rate per group.

    Returns:
    - group_leaf_data: {group_id: [{"disposal_method", "absolute_percentage", "status"}]}
    - group_completion: {group_id: completion_0_to_1}
    """
    if not group_ids:
        print(f"[RECYCLE_DEBUG] fetch_group_leaf_data: no group_ids provided")
        return {}, {}

    from ....models.transactions.transport_transaction import TransportTransaction

    print(f"[RECYCLE_DEBUG] fetch_group_leaf_data: querying TransportTransaction for group_ids={group_ids}")

    rows = db.query(
        TransportTransaction.transaction_group_id,
        TransportTransaction.disposal_method,
        TransportTransaction.absolute_percentage,
        TransportTransaction.status,
        TransportTransaction.is_root,
        TransportTransaction.parent_id,
        TransportTransaction.id,
    ).filter(
        TransportTransaction.transaction_group_id.in_(list(group_ids)),
        TransportTransaction.is_active == True,
        TransportTransaction.deleted_date.is_(None),
    ).all()

    print(f"[RECYCLE_DEBUG] fetch_group_leaf_data: query returned {len(rows)} rows")
    for r in rows[:10]:
        print(f"[RECYCLE_DEBUG]   row: group_id={r[0]}, disposal={r[1]}, abs_pct={r[2]}, status={r[3]}, is_root={r[4]}, parent_id={r[5]}, id={r[6]}")

    # Also check: are there ANY transport transactions for these groups (including deleted)?
    all_rows_count = db.query(TransportTransaction.id, TransportTransaction.transaction_group_id, TransportTransaction.is_active, TransportTransaction.deleted_date).filter(
        TransportTransaction.transaction_group_id.in_(list(group_ids)),
    ).all()
    print(f"[RECYCLE_DEBUG] fetch_group_leaf_data: ALL rows (incl deleted) for these groups: {len(all_rows_count)}")
    for ar in all_rows_count[:10]:
        print(f"[RECYCLE_DEBUG]   all_row: id={ar[0]}, group_id={ar[1]}, is_active={ar[2]}, deleted_date={ar[3]}")

    # Build tree to find leaves (nodes with no children)
    by_group: Dict[int, List] = {}
    has_children: Set[int] = set()
    for gid, method, abs_pct, status, is_root, parent_id, tid in rows:
        by_group.setdefault(gid, []).append({
            "id": tid,
            "disposal_method": method,
            "absolute_percentage": abs_pct,
            "status": status,
            "is_root": is_root,
            "parent_id": parent_id,
        })
        if parent_id is not None:
            has_children.add(parent_id)

    group_leaf_data: Dict[int, List[dict]] = {}
    group_completion: Dict[int, float] = {}

    for gid, nodes in by_group.items():
        # A leaf is any node that has no children.
        # For single-hop transports, the root IS also the leaf (no children).
        leaves = [n for n in nodes if n["id"] not in has_children]
        group_leaf_data[gid] = leaves

        total_leaf_pct = sum(float(l.get("absolute_percentage") or 0) for l in leaves)
        completed_pct = sum(
            float(l.get("absolute_percentage") or 0)
            for l in leaves
            if l.get("status") == "arrived" and l.get("disposal_method")
        )
        group_completion[gid] = (completed_pct / total_leaf_pct) if total_leaf_pct > 0 else 0.0

    return group_leaf_data, group_completion
