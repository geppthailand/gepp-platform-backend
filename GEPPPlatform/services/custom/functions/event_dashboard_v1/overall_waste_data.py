"""
GET /overall-waste-data — Waste statistics for an event dashboard

Returns total weight, recycling rate, GHG reduction, tree equivalent,
material breakdown by category/sub-category, timeseries, and tenant split.

Weight formula: origin_quantity × Material.unit_weight (fallback: origin_weight_kg)
Date filtering: based on TransactionRecord.transaction_date (not Transaction.transaction_date)
Recycling rate: Tier 3 category-based (category_id in {1, 3})
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Set
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)

_RECYCLABLE_CATEGORIES = {1, 3}
_TZ_BKK = timezone(timedelta(hours=7))


def handle_overall_waste_data(
    db_session: Session,
    organization_id: int,
    query_params: Dict[str, Any],
) -> Dict[str, Any]:
    # --- Validate params ---
    user_location_id = query_params.get('user_location_id')
    start_date_str = query_params.get('start_date')
    end_date_str = query_params.get('end_date')
    interval_str = query_params.get('interval')

    if not user_location_id or not start_date_str or not end_date_str:
        return {
            "success": False,
            "error": "MISSING_PARAM",
            "message": "user_location_id, start_date, and end_date are required"
        }

    try:
        user_location_id = int(user_location_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "INVALID_PARAM", "message": "user_location_id must be an integer"}

    try:
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
    except ValueError:
        return {"success": False, "error": "INVALID_PARAM", "message": "start_date and end_date must be ISO format (YYYY-MM-DD)"}

    interval_seconds = int(interval_str) if interval_str else 86400

    # --- Resolve descendant location IDs ---
    descendant_ids = _resolve_descendant_locations(db_session, organization_id, user_location_id)

    empty_response = {
        "success": True,
        "user_location_id": user_location_id,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_weight_kg": 0,
        "recycling_rate": 0,
        "ghg_reduction_kg": 0,
        "tree_equivalent": 0,
        "material_breakdown": [],
        "timeseries": {"timestamp": [], "sum_weight": [], "recycling_rate": []},
        "tenant_split": [],
    }

    if not descendant_ids:
        return empty_response

    # --- Fetch data via JOIN (same approach as reports_handlers) ---
    from GEPPPlatform.models.transactions.transactions import Transaction, TransactionStatus
    from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
    from GEPPPlatform.models.cores.references import Material, MaterialCategory
    from GEPPPlatform.models.users.user_related import UserTenant

    # Query: TransactionRecord JOIN Transaction JOIN Material
    # Matches reports_handlers.get_overview_data approach
    rows = db_session.query(
        TransactionRecord.origin_quantity,       # 0
        TransactionRecord.transaction_date,      # 1
        TransactionRecord.created_transaction_id,# 2
        Transaction.origin_id,                   # 3
        Transaction.status,                      # 4
        Material.unit_weight,                    # 5
        Material.calc_ghg,                       # 6
        Material.category_id,                    # 7
        TransactionRecord.origin_weight_kg,      # 8
        TransactionRecord.category_id.label('record_category_id'),  # 9
        TransactionRecord.material_id,           # 10
        Material.name_en,                        # 11
        Material.name_th,                        # 12
        Transaction.tenant_id,                   # 13
    ).join(
        Transaction,
        TransactionRecord.created_transaction_id == Transaction.id
    ).outerjoin(
        Material,
        TransactionRecord.material_id == Material.id
    ).filter(
        Transaction.organization_id == organization_id,
        Transaction.origin_id.in_(list(descendant_ids)),
        Transaction.deleted_date.is_(None),
        TransactionRecord.deleted_date.is_(None),
        # Date filter on TransactionRecord.transaction_date (same as reports)
        TransactionRecord.transaction_date >= start_date,
        TransactionRecord.transaction_date <= end_date,
        # Exclude rejected records at record level
        or_(TransactionRecord.status != 'rejected', TransactionRecord.status.is_(None)),
    ).all()

    if not rows:
        return empty_response

    # --- Pre-load categories ---
    cat_ids_in_data = set()
    for row in rows:
        cat_id = row[7] or row[9]  # Material.category_id or record_category_id
        if cat_id:
            cat_ids_in_data.add(cat_id)

    categories_map: Dict[int, MaterialCategory] = {}
    if cat_ids_in_data:
        cats = db_session.query(MaterialCategory).filter(MaterialCategory.id.in_(list(cat_ids_in_data))).all()
        categories_map = {c.id: c for c in cats}

    # --- Calculate totals ---
    total_weight_kg = 0.0
    recyclable_weight_kg = 0.0
    total_ghg_kg = 0.0

    # Material breakdown: {category_id: {material_id: {"weight_kg": float, "ghg_kg": float}}}
    cat_mat_data: Dict[int, Dict[int, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"weight_kg": 0.0, "ghg_kg": 0.0}))

    # Timeseries: {bucket_key: {"total": float, "recyclable": float}}
    timeseries_data: Dict[int, Dict[str, float]] = defaultdict(lambda: {"total": 0.0, "recyclable": 0.0})

    # Tenant split: {tenant_id: {"weight": float, "recyclable": float}}
    tenant_data: Dict[int, Dict[str, float]] = defaultdict(lambda: {"weight": 0.0, "recyclable": 0.0})

    seen_txn_statuses = {}

    for row in rows:
        origin_quantity = float(row[0] or 0)
        record_date = row[1]
        txn_id = row[2]
        txn_status = row[4]
        unit_weight = float(row[5] or 0)
        calc_ghg = float(row[6] or 0)
        mat_category_id = row[7]
        origin_weight_kg = float(row[8] or 0)
        record_category_id = row[9]
        material_id = row[10]
        mat_name_en = row[11]
        mat_name_th = row[12]
        tenant_id = row[13]

        # Skip rejected/cancelled transactions (same as reports Python-level filter)
        if txn_status in (TransactionStatus.rejected, TransactionStatus.cancelled):
            continue

        # Weight: origin_quantity × unit_weight (fallback: origin_weight_kg)
        weight = origin_quantity * unit_weight if unit_weight > 0 else origin_weight_kg

        # Category: prefer Material.category_id, fallback to record.category_id
        cat_id = mat_category_id or record_category_id

        # GHG
        ghg = weight * calc_ghg
        total_ghg_kg += ghg

        # Totals
        total_weight_kg += weight

        # Recycling rate (Tier 3)
        is_recyclable = cat_id in _RECYCLABLE_CATEGORIES if cat_id else False
        if is_recyclable:
            recyclable_weight_kg += weight

        # Material breakdown
        if cat_id and material_id:
            cat_mat_data[cat_id][material_id]["weight_kg"] += weight
            cat_mat_data[cat_id][material_id]["ghg_kg"] += ghg
            # Store names for later
            cat_mat_data[cat_id][material_id]["name_en"] = mat_name_en
            cat_mat_data[cat_id][material_id]["name_th"] = mat_name_th

        # Timeseries (use record_date, not transaction_date)
        if record_date:
            epoch = int(record_date.timestamp())
            bucket = (epoch // interval_seconds) * interval_seconds
            timeseries_data[bucket]["total"] += weight
            if is_recyclable:
                timeseries_data[bucket]["recyclable"] += weight

        # Tenant split
        if tenant_id:
            tenant_data[tenant_id]["weight"] += weight
            if is_recyclable:
                tenant_data[tenant_id]["recyclable"] += weight

    recycling_rate = (recyclable_weight_kg / total_weight_kg) if total_weight_kg > 0 else 0.0
    tree_equivalent = total_ghg_kg / 9.5 if total_ghg_kg > 0 else 0.0

    # --- Build material breakdown response ---
    material_breakdown = []
    for cat_id, mat_dict in sorted(cat_mat_data.items()):
        cat = categories_map.get(cat_id)
        cat_total_weight = sum(v["weight_kg"] for v in mat_dict.values())

        mat_list = []
        for mat_id, vals in sorted(mat_dict.items()):
            pct = (vals["weight_kg"] / total_weight_kg) if total_weight_kg > 0 else 0.0
            mat_list.append({
                "material_id": mat_id,
                "name_th": vals.get("name_th"),
                "name_en": vals.get("name_en"),
                "weight_kg": round(vals["weight_kg"], 4),
                "percentage": round(pct, 6),
                "ghg_kg": round(vals["ghg_kg"], 4),
            })

        material_breakdown.append({
            "category_id": cat_id,
            "category_name_th": cat.name_th if cat else None,
            "category_name_en": cat.name_en if cat else None,
            "color": cat.color if cat else None,
            "total_weight_kg": round(cat_total_weight, 4),
            "materials": mat_list,
        })

    # --- Build timeseries response (parallel arrays for easy plotting) ---
    timestamps = []
    sum_weights = []
    recycling_rates = []
    for bucket_ts in sorted(timeseries_data.keys()):
        vals = timeseries_data[bucket_ts]
        timestamps.append(datetime.fromtimestamp(bucket_ts, tz=_TZ_BKK).isoformat())
        sum_weights.append(round(vals["total"], 4))
        bucket_rate = (vals["recyclable"] / vals["total"]) if vals["total"] > 0 else 0.0
        recycling_rates.append(round(bucket_rate, 6))

    # --- Build tenant split response ---
    tenant_split = []
    if tenant_data:
        tenant_ids = list(tenant_data.keys())
        tenants = db_session.query(UserTenant).filter(
            UserTenant.id.in_(tenant_ids),
            UserTenant.deleted_date.is_(None),
        ).all()
        tenant_name_map = {t.id: t.name for t in tenants}

        for tid in sorted(tenant_data.keys()):
            td = tenant_data[tid]
            tw = td["weight"]
            tr = (td["recyclable"] / tw) if tw > 0 else 0.0
            tenant_split.append({
                "tenant_id": tid,
                "tenant_name": tenant_name_map.get(tid, f"Tenant {tid}"),
                "sum_weight": round(tw, 4),
                "recycling_rate": round(tr, 6),
            })

    return {
        "success": True,
        "user_location_id": user_location_id,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_weight_kg": round(total_weight_kg, 4),
        "recycling_rate": round(recycling_rate, 6),
        "ghg_reduction_kg": round(total_ghg_kg, 4),
        "tree_equivalent": round(tree_equivalent, 2),
        "material_breakdown": material_breakdown,
        "timeseries": {
            "timestamp": timestamps,
            "sum_weight": sum_weights,
            "recycling_rate": recycling_rates,
        },
        "tenant_split": tenant_split,
    }


def _resolve_descendant_locations(
    db_session: Session,
    organization_id: int,
    user_location_id: int,
) -> Set[int]:
    from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup

    setup = db_session.query(OrganizationSetup).filter(
        OrganizationSetup.organization_id == organization_id,
        OrganizationSetup.is_active == True,
        OrganizationSetup.deleted_date.is_(None),
    ).order_by(OrganizationSetup.id.desc()).first()

    if not setup:
        return set()

    target_id = str(user_location_id)
    root_nodes = setup.root_nodes or []
    hub_node = setup.hub_node or {}

    target_node = _find_node(root_nodes, target_id)
    if not target_node and hub_node.get('children'):
        target_node = _find_node(hub_node['children'], target_id)

    if not target_node:
        return {user_location_id}

    ids: Set[int] = set()
    _collect_ids(target_node, ids)
    return ids


def _find_node(nodes: list, target_id: str) -> dict:
    for node in nodes:
        if str(node.get('nodeId', '')) == target_id:
            return node
        children = node.get('children') or []
        found = _find_node(children, target_id)
        if found:
            return found
    return None


def _collect_ids(node: dict, ids: Set[int]) -> None:
    nid = node.get('nodeId', '')
    if nid and str(nid).isdigit():
        ids.add(int(nid))
    for child in (node.get('children') or []):
        _collect_ids(child, ids)
