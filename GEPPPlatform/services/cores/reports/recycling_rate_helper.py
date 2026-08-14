"""Recycling Rate Helper — 3-tier calculation integrating traceability data.

Tier 1: record group is fully traced
        → use terminal disposal_method classification only.
Tier 2: record group is partially traced
        → traced portion uses terminal disposal methods; untraced remainder
          falls back to material category.
Tier 3: record has no usable traceability
        → category-based fallback: cat_id in (1, 3) = recyclable.

Consolidation note:
Traceability consolidation stores one downstream transport under a primary
group/transport, plus source rows that point back to every contributing origin
group/transport. Reports must attribute that downstream method back to each
source contribution; otherwise non-primary sources incorrectly fall back to
material category even after the consolidated flow is complete.
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
    supersede_delivered: bool = False,
    superseded_by_record: Optional[Dict[int, float]] = None,
) -> Tuple[float, float, float, bool, float]:
    """
    3-tier recycling rate calculation.

    Parameters:
    - record_weights: list of (weight, calc_ghg_per_kg, category_id, traceability_group_id)
    - group_leaf_data: {group_id: [{"disposal_method", "absolute_percentage", "status"}]}
    - group_completion: {group_id: completion_rate_0_to_1}
    - supersede_delivered: hand material delivered to a collection point over to
      that point's OWN outbound records instead of guessing it from the material
      category. OFF by default, so every existing caller keeps today's numbers
      byte for byte.
    - superseded_by_record: {index_into_record_weights: kg} for piles that have
      no legs at all — material weighed in AT a collection point, which sits in
      the room with nothing to trace. Only consulted when supersede_delivered.

    Returns: (recyclable_weight, recyclable_ghg, total_weight, all_fully_traced,
              rate_total)
    - all_fully_traced: True only if EVERY record has a traceability_group_id
      with completion == 1.0. False if any record lacks a group or has incomplete tracing.
    - rate_total: the denominator the rate must use — the weight actually
      ACCOUNTED FOR (traced outcomes + category-guessed remainder), summed the
      same way the numerator is, so recyclable <= rate_total always holds even
      when a leaf over-attributes. Equals the plain total when nothing is
      superseded and no leaf over-attributes, which is every legacy caller.

    Superseding is what makes the two-scope model add up. A tenant's kilograms
    are REAL at the origin (they appear in "waste generated") but their FATE is
    unknowable from their own chain — the material went into a shared room and
    came out re-sorted. Counting them again by material-category guess, while
    the room's weigh-outs report what actually happened, would count the same
    kilograms twice and let a guess outvote a measurement.
    """
    total_weight = 0.0
    recyclable_weight = 0.0
    recyclable_ghg = 0.0
    superseded_total = 0.0
    rate_total = 0.0
    has_untraced = False
    has_incomplete = False

    for idx, (weight, calc_ghg, cat_id, group_id) in enumerate(record_weights):
        total_weight += weight

        if group_id is not None and group_id in group_leaf_data:
            completion = group_completion.get(group_id, 0.0)
            leaves = group_leaf_data[group_id]
            # A pile handed to a collection point IS accounted for — the tenant's
            # part is finished and the room's ledger carries it from here — but
            # `completion` counts disposal outcomes only, because it is shared
            # with callers that do not supersede. Re-read it here, where the flag
            # is known, so a scale site is not badged "partially traced" forever.
            if completion < 1.0 and not (
                supersede_delivered
                and any(
                    l.get("status") == "arrived"
                    and (l.get("disposal_method") or l.get("delivered"))
                    for l in leaves
                )
                and not any(
                    l.get("status") != "arrived"
                    or not (l.get("disposal_method") or l.get("delivered"))
                    for l in leaves
                )
            ):
                has_incomplete = True

            # Completed traceability uses destination leaf weights. When a
            # group has multiple source records, allocate each terminal leaf
            # back to the record by its share of the group's origin weight.
            completed_weight = 0.0
            traced_recyclable_weight = 0.0
            delivered_weight = 0.0

            def _record_share_of(leaf: dict) -> float:
                """This record's slice of a leaf, by its share of the pile."""
                group_total = float(leaf.get("group_total_weight") or 0)
                leaf_weight = leaf.get("leaf_weight")
                if leaf_weight is None:
                    return weight * (float(leaf.get("absolute_percentage") or 0) / 100.0)
                record_share = (weight / group_total) if group_total > 0 else 1.0
                return float(leaf_weight or 0) * record_share

            for leaf in leaves:
                status = leaf.get("status") or ""
                if status != "arrived":
                    continue
                method = (leaf.get("disposal_method") or "").strip()
                if supersede_delivered and leaf.get("delivered"):
                    # Handed over to a collection point: no outcome here, and
                    # by construction no method either.
                    delivered_weight += _record_share_of(leaf)
                    continue
                if not method:
                    continue
                record_leaf_weight = _record_share_of(leaf)
                completed_weight += record_leaf_weight
                if method in DIVERTED_METHODS:
                    traced_recyclable_weight += record_leaf_weight

            # ORDER MATTERS: completed first, then superseded clamped against
            # what is left. The other order lets an over-attributed delivered
            # leaf drive the denominator below the numerator.
            if supersede_delivered:
                pile_less = float((superseded_by_record or {}).get(idx, 0.0))
                delivered_weight = max(delivered_weight, pile_less)
                delivered_weight = min(delivered_weight, max(0.0, weight - completed_weight))
            else:
                delivered_weight = 0.0

            recyclable_from_traced = traced_recyclable_weight
            ghg_from_traced = recyclable_from_traced * calc_ghg

            # Untraced portion: fallback to category
            untraced_weight = max(0.0, weight - completed_weight - delivered_weight)
            recyclable_from_untraced = 0.0
            ghg_from_untraced = 0.0
            if untraced_weight > 0 and cat_id in _RECYCLABLE_CATEGORIES:
                recyclable_from_untraced = untraced_weight
                ghg_from_untraced = recyclable_from_untraced * calc_ghg

            recyclable_weight += recyclable_from_traced + recyclable_from_untraced
            recyclable_ghg += ghg_from_traced + ghg_from_untraced
            superseded_total += delivered_weight
            # The denominator is built from what was actually ACCOUNTED FOR, not
            # from the record's own weight. Leaf weights and record weights come
            # from different columns and a leaf can over-attribute (a group whose
            # records have no origin_weight_kg gives every record the whole leaf),
            # so clamping the numerator down to the record weight would leave a
            # numerator larger than a denominator built from that weight — a rate
            # above 100%. Adding the leaf weight to BOTH sides keeps the ratio
            # meaningful whatever the leaf says, because the diverted share can
            # never exceed the completed share it is drawn from.
            rate_total += completed_weight + untraced_weight
        else:
            # Tier 3: no traceability → old category method, unless the record
            # belongs to a hopless pile sitting inside a collection point.
            pile_less = 0.0
            if supersede_delivered:
                pile_less = min(float((superseded_by_record or {}).get(idx, 0.0)), weight)
            if pile_less > 0:
                superseded_total += pile_less
            remaining = weight - pile_less
            rate_total += remaining
            if remaining > 0:
                has_untraced = True
                if cat_id in _RECYCLABLE_CATEGORIES:
                    recyclable_weight += remaining
                    recyclable_ghg += remaining * calc_ghg

    all_fully_traced = not has_untraced and not has_incomplete
    rate_total = max(0.0, rate_total)
    return recyclable_weight, recyclable_ghg, total_weight, all_fully_traced, rate_total


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

        completed_weight = 0.0
        traced_recyclable_weight = 0.0
        for leaf in leaves:
            method = (leaf.get("disposal_method") or "").strip()
            status = leaf.get("status") or ""
            if status != "arrived" or not method:
                continue
            group_total = float(leaf.get("group_total_weight") or 0)
            leaf_weight = leaf.get("leaf_weight")
            if leaf_weight is None:
                record_leaf_weight = weight * (float(leaf.get("absolute_percentage") or 0) / 100.0)
            else:
                record_share = (weight / group_total) if group_total > 0 else 1.0
                record_leaf_weight = float(leaf_weight or 0) * record_share
            completed_weight += record_leaf_weight
            if method in DIVERTED_METHODS:
                traced_recyclable_weight += record_leaf_weight

        recyclable = traced_recyclable_weight

        untraced_weight = max(0.0, weight - completed_weight)
        if untraced_weight > 0 and cat_id in _RECYCLABLE_CATEGORIES:
            recyclable += untraced_weight

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
    group_ids = {int(gid) for gid in (group_ids or set()) if gid is not None}
    if not group_ids:
        return {}, {}

    from ....models.transactions.transport_transaction import TransportTransaction
    from ....models.transactions.traceability_consolidation import (
        TraceabilityConsolidation,
        TraceabilityConsolidationSource,
    )
    from ....models.transactions.traceability_transaction_group import TraceabilityTransactionGroup
    from ....models.transactions.transaction_records import TransactionRecord
    from sqlalchemy import or_

    rows = db.query(
        TransportTransaction.transaction_group_id,
        TransportTransaction.disposal_method,
        TransportTransaction.absolute_percentage,
        TransportTransaction.status,
        TransportTransaction.is_root,
        TransportTransaction.parent_id,
        TransportTransaction.id,
        TransportTransaction.weight,
        TransportTransaction.delivered_to_collection,
    ).filter(
        TransportTransaction.transaction_group_id.in_(list(group_ids)),
        TransportTransaction.is_active == True,
        TransportTransaction.deleted_date.is_(None),
    ).all()

    # Build tree to find leaves (nodes with no children). We keep transport
    # metadata because consolidation source rows can point at a transport leaf.
    by_group: Dict[int, List] = {}
    has_children: Set[int] = set()
    transport_meta: Dict[int, dict] = {}
    for gid, method, abs_pct, status, is_root, parent_id, tid, weight, delivered in rows:
        by_group.setdefault(gid, []).append({
            "id": tid,
            "disposal_method": method,
            "absolute_percentage": abs_pct,
            "status": status,
            "is_root": is_root,
            "parent_id": parent_id,
            "weight": float(weight or 0),
            "delivered": bool(delivered),
        })
        transport_meta[int(tid)] = {
            "group_id": int(gid),
            "absolute_percentage": float(abs_pct or 0),
            "weight": float(weight or 0),
        }
        if parent_id is not None:
            has_children.add(int(parent_id))

    source_transport_ids = set(transport_meta.keys())
    consolidation_rows = []
    if source_transport_ids:
        consolidation_rows = db.query(
            TraceabilityConsolidation.consolidated_transport_id,
            TraceabilityConsolidationSource.source_transport_id,
            TraceabilityConsolidationSource.source_group_id,
            TraceabilityConsolidationSource.contributed_weight,
        ).join(
            TraceabilityConsolidationSource,
            TraceabilityConsolidationSource.consolidation_id == TraceabilityConsolidation.id,
        ).filter(
            TraceabilityConsolidation.is_active == True,
            TraceabilityConsolidation.deleted_date.is_(None),
            TraceabilityConsolidationSource.is_active == True,
            TraceabilityConsolidationSource.deleted_date.is_(None),
            or_(
                TraceabilityConsolidationSource.source_group_id.in_(list(group_ids)),
                TraceabilityConsolidationSource.source_transport_id.in_(list(source_transport_ids)),
            ),
        ).all()
    else:
        consolidation_rows = db.query(
            TraceabilityConsolidation.consolidated_transport_id,
            TraceabilityConsolidationSource.source_transport_id,
            TraceabilityConsolidationSource.source_group_id,
            TraceabilityConsolidationSource.contributed_weight,
        ).join(
            TraceabilityConsolidationSource,
            TraceabilityConsolidationSource.consolidation_id == TraceabilityConsolidation.id,
        ).filter(
            TraceabilityConsolidation.is_active == True,
            TraceabilityConsolidation.deleted_date.is_(None),
            TraceabilityConsolidationSource.is_active == True,
            TraceabilityConsolidationSource.deleted_date.is_(None),
            TraceabilityConsolidationSource.source_group_id.in_(list(group_ids)),
        ).all()

    consolidated_transport_ids = {
        int(row[0]) for row in consolidation_rows if row[0] is not None
    }
    consumed_source_pcts_by_transport: Dict[int, float] = {}
    consolidated_descendant_ids: Set[int] = set()

    def _group_weights_for_source_groups(source_group_ids: Set[int]) -> Dict[int, float]:
        if not source_group_ids:
            return {}
        groups = db.query(
            TraceabilityTransactionGroup.id,
            TraceabilityTransactionGroup.transaction_record_id,
        ).filter(
            TraceabilityTransactionGroup.id.in_(list(source_group_ids)),
            TraceabilityTransactionGroup.is_active == True,
            TraceabilityTransactionGroup.deleted_date.is_(None),
        ).all()
        record_ids = []
        group_record_ids: Dict[int, list] = {}
        for gid, rec_ids in groups:
            ids = list(rec_ids or [])
            group_record_ids[int(gid)] = ids
            record_ids.extend(ids)
        weights_by_record = {}
        if record_ids:
            rec_rows = db.query(
                TransactionRecord.id,
                TransactionRecord.origin_weight_kg,
            ).filter(
                TransactionRecord.id.in_(list(set(record_ids))),
                TransactionRecord.is_active == True,
                TransactionRecord.deleted_date.is_(None),
            ).all()
            weights_by_record = {int(rid): float(w or 0) for rid, w in rec_rows}
        return {
            gid: sum(weights_by_record.get(int(rid), 0.0) for rid in rec_ids)
            for gid, rec_ids in group_record_ids.items()
        }

    group_total_weights = _group_weights_for_source_groups(group_ids)

    def _terminal_leaves_for_consolidated_roots(root_ids: Set[int]) -> Dict[int, List[dict]]:
        if not root_ids:
            return {}
        root_rows = db.query(
            TransportTransaction.id,
            TransportTransaction.transaction_group_id,
            TransportTransaction.weight,
        ).filter(
            TransportTransaction.id.in_(list(root_ids)),
            TransportTransaction.is_active == True,
            TransportTransaction.deleted_date.is_(None),
        ).all()
        root_group_ids = {int(gid) for _, gid, _ in root_rows if gid is not None}
        root_weights = {int(tid): float(weight or 0) for tid, _, weight in root_rows}
        if not root_group_ids:
            return {}
        branch_rows = db.query(
            TransportTransaction.id,
            TransportTransaction.parent_id,
            TransportTransaction.transaction_group_id,
            TransportTransaction.disposal_method,
            TransportTransaction.status,
            TransportTransaction.weight,
            TransportTransaction.delivered_to_collection,
        ).filter(
            TransportTransaction.transaction_group_id.in_(list(root_group_ids)),
            TransportTransaction.is_active == True,
            TransportTransaction.deleted_date.is_(None),
        ).all()
        by_parent: Dict[Optional[int], List[dict]] = {}
        by_id: Dict[int, dict] = {}
        for tid, parent_id, gid, method, status, weight, delivered in branch_rows:
            node = {
                "id": int(tid),
                "parent_id": int(parent_id) if parent_id is not None else None,
                "transaction_group_id": int(gid) if gid is not None else None,
                "disposal_method": method,
                "status": status,
                "weight": float(weight or 0),
                "delivered": bool(delivered),
            }
            by_id[int(tid)] = node
            by_parent.setdefault(node["parent_id"], []).append(node)

        leaves_by_root: Dict[int, List[dict]] = {}

        def walk(root_id: int, node_id: int) -> None:
            consolidated_descendant_ids.add(node_id)
            children = by_parent.get(node_id) or []
            if not children:
                node = by_id.get(node_id)
                if not node:
                    return
                root_weight = root_weights.get(root_id) or node.get("weight") or 0
                fraction = (float(node.get("weight") or 0) / root_weight) if root_weight > 0 else 0.0
                leaves_by_root.setdefault(root_id, []).append({
                    "disposal_method": node.get("disposal_method"),
                    "status": node.get("status"),
                    "downstream_fraction": max(0.0, min(1.0, fraction)),
                    # The WALKED leaf's own flag, not the consolidation result's.
                    # A result leg that is itself terminal carries its own answer;
                    # one that was shipped onward into a collection point hands
                    # the flag down from that onward hop. Reading the result leg
                    # instead would leave the sources category-guessed while the
                    # tank counted the same kilograms — a double count.
                    "delivered": bool(node.get("delivered")),
                })
                return
            for child in children:
                walk(root_id, child["id"])

        for root_id in root_ids:
            if root_id in by_id:
                walk(root_id, root_id)
        return leaves_by_root

    group_source_ids = {
        int(row[2]) for row in consolidation_rows
        if row[2] is not None and int(row[2]) in group_ids
    }
    group_weights = _group_weights_for_source_groups(group_source_ids)
    consolidated_leaves = _terminal_leaves_for_consolidated_roots(consolidated_transport_ids)

    pseudo_leaves_by_group: Dict[int, List[dict]] = {}
    for consolidated_tid, source_tid, source_gid, contributed_weight in consolidation_rows:
        if consolidated_tid is None:
            continue
        downstream_leaves = consolidated_leaves.get(int(consolidated_tid)) or []
        if not downstream_leaves:
            continue
        contributed = float(contributed_weight or 0)
        source_pct = 0.0
        target_gid = None
        if source_gid is not None and int(source_gid) in group_ids:
            target_gid = int(source_gid)
            group_weight = group_weights.get(target_gid, 0.0)
            source_pct = (contributed / group_weight * 100.0) if group_weight > 0 else 0.0
        elif source_tid is not None and int(source_tid) in transport_meta:
            meta = transport_meta[int(source_tid)]
            target_gid = int(meta["group_id"])
            source_weight = float(meta.get("weight") or 0)
            transport_pct = float(meta.get("absolute_percentage") or 0)
            consumed_fraction = (contributed / source_weight) if source_weight > 0 else 0.0
            consumed_fraction = max(0.0, min(1.0, consumed_fraction))
            source_pct = transport_pct * consumed_fraction
            consumed_source_pcts_by_transport[int(source_tid)] = (
                consumed_source_pcts_by_transport.get(int(source_tid), 0.0) + source_pct
            )
        if target_gid is None or source_pct <= 0:
            continue
        for leaf in downstream_leaves:
            pseudo_leaves_by_group.setdefault(target_gid, []).append({
                "id": f"consolidation:{int(consolidated_tid)}",
                "disposal_method": leaf.get("disposal_method"),
                "absolute_percentage": source_pct * float(leaf.get("downstream_fraction") or 0),
                "leaf_weight": contributed * float(leaf.get("downstream_fraction") or 0),
                "group_total_weight": group_total_weights.get(target_gid, 0.0),
                "status": leaf.get("status"),
                "delivered": bool(leaf.get("delivered")),
                "is_consolidation": True,
            })

    group_leaf_data: Dict[int, List[dict]] = {}
    group_completion: Dict[int, float] = {}

    for gid, nodes in by_group.items():
        # A leaf is any node that has no children.
        # For single-hop transports, the root IS also the leaf (no children).
        leaves = []
        for n in nodes:
            tid = int(n["id"])
            if tid in has_children:
                continue
            if tid in consolidated_descendant_ids:
                continue
            leaf = dict(n)
            consumed_pct = consumed_source_pcts_by_transport.get(tid, 0.0)
            if consumed_pct > 0:
                remaining_pct = max(0.0, float(leaf.get("absolute_percentage") or 0) - consumed_pct)
                if remaining_pct <= 0.0001:
                    continue
                original_pct = float(leaf.get("absolute_percentage") or 0)
                leaf["absolute_percentage"] = remaining_pct
                if original_pct > 0:
                    leaf["leaf_weight"] = float(leaf.get("weight") or 0) * (remaining_pct / original_pct)
                else:
                    leaf["leaf_weight"] = float(leaf.get("weight") or 0)
            else:
                leaf["leaf_weight"] = float(leaf.get("weight") or 0)
            leaf["group_total_weight"] = group_total_weights.get(int(gid), 0.0)
            leaves.append(leaf)
        leaves.extend(pseudo_leaves_by_group.get(gid, []))
        total_known_pct = sum(float(l.get("absolute_percentage") or 0) for l in leaves)
        if 0 < total_known_pct < 99.99:
            leaves.append({
                "id": f"untraced:{gid}",
                "disposal_method": None,
                "absolute_percentage": 100.0 - total_known_pct,
                "leaf_weight": max(0.0, group_total_weights.get(int(gid), 0.0) * ((100.0 - total_known_pct) / 100.0)),
                "group_total_weight": group_total_weights.get(int(gid), 0.0),
                "status": "untraced",
            })
        group_leaf_data[gid] = leaves

        group_total_weight = group_total_weights.get(int(gid), 0.0)
        # Completion counts DISPOSAL outcomes only. Delivered-to-collection legs
        # are deliberately excluded here: this value is shared with callers that
        # do not supersede (the performance tab), and for them a delivered pile
        # really is being category-guessed — badging it "fully traced" would
        # claim a measurement nobody made. The overview's own badge is repaired
        # inside compute_recycling_rate, where the supersede flag is known.
        completed_weight = sum(
            float(l.get("leaf_weight") or 0)
            for l in leaves
            if l.get("status") == "arrived" and l.get("disposal_method")
        )
        if group_total_weight > 0:
            group_completion[gid] = min(1.0, max(0.0, completed_weight / group_total_weight))
        else:
            total_leaf_pct = sum(float(l.get("absolute_percentage") or 0) for l in leaves)
            completed_pct = sum(
                float(l.get("absolute_percentage") or 0)
                for l in leaves
                if l.get("status") == "arrived" and l.get("disposal_method")
            )
            group_completion[gid] = (completed_pct / total_leaf_pct) if total_leaf_pct > 0 else 0.0

    # Groups that only appear as direct consolidation sources may have no
    # transport rows of their own. They still need leaf data so records in those
    # groups use the downstream method instead of legacy category fallback.
    for gid, leaves in pseudo_leaves_by_group.items():
        if gid in group_leaf_data:
            continue
        total_known_pct = sum(float(l.get("absolute_percentage") or 0) for l in leaves)
        if 0 < total_known_pct < 99.99:
            leaves = leaves + [{
                "id": f"untraced:{gid}",
                "disposal_method": None,
                "absolute_percentage": 100.0 - total_known_pct,
                "leaf_weight": max(0.0, group_total_weights.get(int(gid), 0.0) * ((100.0 - total_known_pct) / 100.0)),
                "group_total_weight": group_total_weights.get(int(gid), 0.0),
                "status": "untraced",
            }]
        group_leaf_data[gid] = leaves
        group_total_weight = group_total_weights.get(int(gid), 0.0)
        # Completion counts DISPOSAL outcomes only. Delivered-to-collection legs
        # are deliberately excluded here: this value is shared with callers that
        # do not supersede (the performance tab), and for them a delivered pile
        # really is being category-guessed — badging it "fully traced" would
        # claim a measurement nobody made. The overview's own badge is repaired
        # inside compute_recycling_rate, where the supersede flag is known.
        completed_weight = sum(
            float(l.get("leaf_weight") or 0)
            for l in leaves
            if l.get("status") == "arrived" and l.get("disposal_method")
        )
        if group_total_weight > 0:
            group_completion[gid] = min(1.0, max(0.0, completed_weight / group_total_weight))
        else:
            total_leaf_pct = sum(float(l.get("absolute_percentage") or 0) for l in leaves)
            completed_pct = sum(
                float(l.get("absolute_percentage") or 0)
                for l in leaves
                if l.get("status") == "arrived" and l.get("disposal_method")
            )
            group_completion[gid] = (completed_pct / total_leaf_pct) if total_leaf_pct > 0 else 0.0

    return group_leaf_data, group_completion
