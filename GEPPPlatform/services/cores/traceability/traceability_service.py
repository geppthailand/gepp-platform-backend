"""
Traceability Service
Business logic for traceability.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, or_

# Timezone for traceability group year/month (same as transaction_service)
TRACEABILITY_DATE_TZ = "Asia/Bangkok"

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.transactions.traceability_transaction_group import TraceabilityTransactionGroup
from ....models.transactions.transport_transaction import TransportTransaction
from ....models.users.user_location import UserLocation


class TraceabilityService:
    """
    Service for traceability operations.
    """

    def __init__(self, db: Session):
        self.db = db

    def _get_assigned_location_ids(self, organization_id: int, current_user_id: int) -> Optional[set]:
        """
        Get the set of location IDs that the user has assigned access to (member + descendants).
        Returns None if user is owner/admin (no filtering needed).
        """
        from ..users.user_service import UserService
        user_service = UserService(self.db)
        locations = user_service.crud.get_user_locations(organization_id=organization_id)
        tiers = user_service._resolve_location_tiers(locations, organization_id, current_user_id)
        if tiers['is_owner']:
            return None  # No filtering needed
        return tiers['assigned_ids']

    def get_traceability(self, organization_id: Optional[int] = None, **kwargs: Any) -> Dict[str, Any]:
        """
        Get traceability for the organization. date_from and date_to define a 1-month range.
        - data[0]: list of traceability_transaction_group for that month/year (with filters).
        - Idle carry-over: idle transport_transactions whose group is last month get their id appended to that group's transaction_carried_over.
        - Legacy backfill: transaction records in that org/month/year not in any group get a new group created.
        - data[1], data[2]: transport records (from Transaction) for backward compatibility.
        - summary: total_waste_weight, total_disposal, total_treatment, total_managed_waste.
        """
        if organization_id is None:
            return {
                "data": [[], [], []],
                "summary": {"total_waste_weight": 0.0, "total_disposal": 0.0, "total_treatment": 0.0, "total_managed_waste": 0.0},
            }

        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        year, month = self._parse_month_range(date_from, date_to)
        if year is None or month is None:
            return {
                "data": [[], [], []],
                "summary": {"total_waste_weight": 0.0, "total_disposal": 0.0, "total_treatment": 0.0, "total_managed_waste": 0.0},
            }

        last_year, last_month = self._last_month(year, month)

        # 1) Idle carry-over: idles whose group is last month -> find or create group in requested (year, month) with same (origin, material, tag, tenant), add idle id to that group's transaction_carried_over
        self._apply_idle_carry_over(organization_id, year, month)

        # 2) Build tentative groups for approved records without an active group (in-memory, not persisted)
        tentative_arr = self._build_tentative_groups(organization_id, year, month, kwargs)

        # 3) Load groups for this month with filters
        group_filters = [
            TraceabilityTransactionGroup.organization_id == organization_id,
            TraceabilityTransactionGroup.transaction_year == year,
            TraceabilityTransactionGroup.transaction_month == month,
            TraceabilityTransactionGroup.deleted_date.is_(None),
            TraceabilityTransactionGroup.is_active == True,
        ]
        material_id_param = kwargs.get("material_id")
        if material_id_param:
            try:
                material_ids = [int(x.strip()) for x in str(material_id_param).split(",") if x.strip()]
                if material_ids:
                    group_filters.append(TraceabilityTransactionGroup.material_id.in_(material_ids))
            except ValueError:
                pass
        origin_id_param = kwargs.get("origin_id")
        if origin_id_param:
            parts = [p.strip() for p in str(origin_id_param).strip().split("|")]
            try:
                if len(parts) >= 1 and parts[0]:
                    group_filters.append(TraceabilityTransactionGroup.origin_id == int(parts[0]))
                if len(parts) >= 2 and parts[1]:
                    group_filters.append(TraceabilityTransactionGroup.location_tag_id == int(parts[1]))
                if len(parts) >= 3 and parts[2]:
                    group_filters.append(TraceabilityTransactionGroup.tenant_id == int(parts[2]))
            except (ValueError, TypeError):
                pass

        # Apply member-based filtering: restrict to user's assigned locations
        current_user_id = kwargs.get("current_user_id")
        if current_user_id and organization_id:
            assigned_ids = self._get_assigned_location_ids(organization_id, int(current_user_id))
            if assigned_ids is not None:
                group_filters.append(TraceabilityTransactionGroup.origin_id.in_(list(assigned_ids)))

        groups = self.db.query(TraceabilityTransactionGroup).filter(and_(*group_filters)).all()
        group_ids = [g.id for g in groups]
        # First array: only groups that do NOT have any traceability_transport_transactions yet
        group_ids_with_transport = set()
        if group_ids:
            rows = (
                self.db.query(TransportTransaction.transaction_group_id)
                .filter(
                    TransportTransaction.transaction_group_id.in_(group_ids),
                    TransportTransaction.is_active == True,
                    TransportTransaction.deleted_date.is_(None),
                )
                .distinct()
                .all()
            )
            group_ids_with_transport = {r[0] for r in rows if r[0] is not None}
        groups_for_first_array = [g for g in groups if g.id not in group_ids_with_transport]
        arr0 = self._groups_to_dict_list(groups_for_first_array, organization_id)
        # Add tentative groups (approved records without active group)
        arr0 = arr0 + tentative_arr
        # Also add arrived TransportTransactions to first array: destination becomes new origin (next leg); include transport_transaction id
        arrived_items = self._arrived_transport_as_first_array(group_ids, organization_id) if group_ids else []
        arr0 = arr0 + arrived_items

        # 4) Second array: traceability_transport_transactions with transaction_group_id in filtered groups, status != idle
        arr1 = self._transport_transactions_for_groups(group_ids, organization_id) if group_ids else []

        # If a child is in the second array, remove its parent from the first array (parent = arrived item with that transport_transaction_id)
        parent_ids_in_arr1 = {item.get("parent_id") for item in arr1 if item.get("parent_id") is not None}
        if parent_ids_in_arr1:
            arr0 = [
                item for item in arr0
                if item.get("transport_transaction_id") not in parent_ids_in_arr1
            ]

        # 5) Third array: traceability_transport_transactions with arrival_date set, status=arrived, have method
        arr2 = self._transport_transactions_with_arrival_for_groups(group_ids, organization_id) if group_ids else []

        # If a child is in the third array (arrived with method), remove its parent from the first array too
        parent_ids_in_arr2 = {item.get("parent_id") for item in arr2 if item.get("parent_id") is not None}
        if parent_ids_in_arr2:
            arr0 = [
                item for item in arr0
                if item.get("transport_transaction_id") not in parent_ids_in_arr2
            ]

        _DIVERTED = {
            "Preparation for reuse", "Recycling (Own)",
            "Other recover operation", "Recycle",
        }
        _DIRECTED = {
            "Composted by municipality", "Municipality receive",
            "Incineration without energy", "Incineration with energy",
        }

        hierarchy_result = self.get_traceability_hierarchy(organization_id, _exclude_idle=True, **kwargs)
        hierarchy_data = hierarchy_result.get("data") or []

        treatment_w = 0.0
        disposal_w = 0.0
        total_group_weight = 0.0

        def _sum_leaves(nodes):
            nonlocal treatment_w, disposal_w
            for t in nodes:
                if not isinstance(t, dict):
                    continue
                children = t.get("children") or []
                if children:
                    _sum_leaves(children)
                else:
                    status = t.get("status") or ""
                    method = t.get("disposal_method") or ""
                    if status != "arrived" or not method:
                        continue
                    w = float(t.get("weight") or 0)
                    if method in _DIVERTED:
                        treatment_w += w
                    elif method in _DIRECTED:
                        disposal_w += w

        for origin_node in hierarchy_data:
            if not isinstance(origin_node, dict):
                continue
            for group_node in origin_node.get("children") or []:
                if not isinstance(group_node, dict):
                    continue
                gw = float(group_node.get("weight") or group_node.get("total_weight_kg") or 0)
                total_group_weight += gw
                _sum_leaves(group_node.get("children") or [])

        # total_waste_weight is the sum of all group weights in this month
        total_waste_weight = round(total_group_weight, 2)
        total_treatment = round(treatment_w, 2)
        total_disposal = round(disposal_w, 2)
        total_managed_waste = round(total_treatment + total_disposal, 2)

        return {
            "data": [arr0, arr1, arr2],
            "summary": {
                "total_waste_weight": round(total_waste_weight, 2),
                "total_disposal": total_disposal,
                "total_treatment": total_treatment,
                "total_managed_waste": total_managed_waste,
            },
        }

    def get_traceability_hierarchy(self, organization_id: Optional[int] = None, _exclude_idle: bool = False, **kwargs: Any) -> Dict[str, Any]:
        """
        Get full hierarchy for the tree chart: transaction groups for the month, each with a tree of
        TransportTransactions (root = parent_id null, then children recursively to leaf).
        Same query params as get_traceability: date_from, date_to (1-month), material_id, origin_id.
        _exclude_idle: when True, filter out idle transport transactions (used for summary calculation).
        """
        if organization_id is None:
            return {"data": []}
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        year, month = self._parse_month_range(date_from, date_to)
        if year is None or month is None:
            return {"data": []}

        self._apply_idle_carry_over(organization_id, year, month)
        self._backfill_traceability_groups_for_month(organization_id, year, month, kwargs)

        group_filters = [
            TraceabilityTransactionGroup.organization_id == organization_id,
            TraceabilityTransactionGroup.transaction_year == year,
            TraceabilityTransactionGroup.transaction_month == month,
            TraceabilityTransactionGroup.deleted_date.is_(None),
            TraceabilityTransactionGroup.is_active == True,
        ]
        material_id_param = kwargs.get("material_id")
        if material_id_param:
            try:
                material_ids = [int(x.strip()) for x in str(material_id_param).split(",") if x.strip()]
                if material_ids:
                    group_filters.append(TraceabilityTransactionGroup.material_id.in_(material_ids))
            except ValueError:
                pass
        origin_id_param = kwargs.get("origin_id")
        if origin_id_param:
            parts = [p.strip() for p in str(origin_id_param).strip().split("|")]
            try:
                if len(parts) >= 1 and parts[0]:
                    group_filters.append(TraceabilityTransactionGroup.origin_id == int(parts[0]))
                if len(parts) >= 2 and parts[1]:
                    group_filters.append(TraceabilityTransactionGroup.location_tag_id == int(parts[1]))
                if len(parts) >= 3 and parts[2]:
                    group_filters.append(TraceabilityTransactionGroup.tenant_id == int(parts[2]))
            except (ValueError, TypeError):
                pass

        # Apply member-based filtering: restrict to user's assigned locations
        current_user_id = kwargs.get("current_user_id")
        if current_user_id and organization_id:
            assigned_ids = self._get_assigned_location_ids(organization_id, int(current_user_id))
            if assigned_ids is not None:
                group_filters.append(TraceabilityTransactionGroup.origin_id.in_(list(assigned_ids)))

        groups = self.db.query(TraceabilityTransactionGroup).filter(and_(*group_filters)).all()
        if not groups:
            return {"data": []}

        group_ids = [g.id for g in groups]
        transport_filters = [
            TransportTransaction.transaction_group_id.in_(group_ids),
            TransportTransaction.organization_id == organization_id,
            TransportTransaction.is_active == True,
            TransportTransaction.deleted_date.is_(None),
        ]
        if _exclude_idle:
            transport_filters.append(TransportTransaction.status != "idle")
        all_transports = (
            self.db.query(TransportTransaction)
            .filter(*transport_filters)
            .all()
        )
        by_group: Dict[int, List[Any]] = {}
        for t in all_transports:
            gid = t.transaction_group_id
            if gid is not None:
                by_group.setdefault(gid, []).append(t)
        location_ids = set()
        material_ids = set()
        for g in groups:
            if g.origin_id is not None and by_group.get(g.id):
                location_ids.add(g.origin_id)
        for t in all_transports:
            if t.origin_id is not None:
                location_ids.add(t.origin_id)
            if getattr(t, "destination_id", None) is not None:
                location_ids.add(t.destination_id)
            if t.material_id is not None:
                material_ids.add(t.material_id)
        path_map: Dict[int, str] = {}
        location_map: Dict[int, Any] = {}
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in location_ids]) or {}
            locs = self.db.query(UserLocation).filter(UserLocation.id.in_(location_ids)).all()
            location_map = {loc.id: loc for loc in locs}
        from ....models.cores.references import Material
        material_map: Dict[int, Any] = {}
        if material_ids:
            mats = self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            material_map = {m.id: m for m in mats}

        def transport_to_node(r: Any) -> Dict[str, Any]:
            origin = None
            if r.origin_id and r.origin_id in location_map:
                origin = self._location_to_dict(location_map[r.origin_id], path=path_map.get(r.origin_id, ""))
            destination = None
            dest_id = getattr(r, "destination_id", None)
            if dest_id and dest_id in location_map:
                destination = self._location_to_dict(location_map[dest_id], path=path_map.get(dest_id, ""))
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            return {
                "id": r.id,
                "transport_transaction_id": r.id,
                "parent_id": r.parent_id,
                "origin_id": r.origin_id,
                "destination_id": dest_id,
                "weight": float(r.weight) if r.weight is not None else None,
                "status": r.status,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "disposal_method": r.disposal_method,
                "meta_data": r.meta_data or {},
                "is_root": r.is_root,
                "absolute_percentage": float(r.absolute_percentage) if r.absolute_percentage is not None else None,
                "origin": origin,
                "destination": destination,
                "material": material,
                "children": [],
            }

        def _annotate_percentages(
            children: List[Dict[str, Any]], parent_pct_of_group: float
        ) -> None:
            siblings_total = sum(float(n.get("weight") or 0) for n in children)
            for node in children:
                w = float(node.get("weight") or 0)
                pct_of_parent = round((w / siblings_total) * 100, 2) if siblings_total else 0.0
                pct_of_group = round(pct_of_parent * parent_pct_of_group / 100, 2)
                node["percentage_of_parent"] = pct_of_parent
                node["percentage_of_group"] = pct_of_group
                if node.get("children"):
                    _annotate_percentages(node["children"], pct_of_group)

        def build_tree(transports: List[Any]) -> List[Dict[str, Any]]:
            if not transports:
                return []
            by_parent: Dict[Optional[int], List[Any]] = {}
            for t in transports:
                pid = t.parent_id
                by_parent.setdefault(pid, []).append(t)
            roots = sorted(by_parent.get(None, []), key=lambda t: t.id)
            id_to_node: Dict[int, Dict[str, Any]] = {}
            for t in transports:
                id_to_node[t.id] = transport_to_node(t)
            for t in transports:
                node = id_to_node[t.id]
                if t.parent_id is not None and t.parent_id in id_to_node:
                    id_to_node[t.parent_id]["children"].append(node)
            for node in id_to_node.values():
                node["children"].sort(key=lambda n: n["id"] or 0)
            return [id_to_node[r.id] for r in roots]

        group_list = self._groups_to_dict_list(groups, organization_id)
        groups_with_children: List[Dict[str, Any]] = []
        for g in groups:
            transports = by_group.get(g.id, [])
            if not transports:
                continue
            group_dict = next((x for x in group_list if x.get("id") == g.id), None)
            if group_dict is None:
                group_dict = {
                    "id": g.id,
                    "group_id": g.id,
                    "origin_id": g.origin_id,
                    "material_id": g.material_id,
                    "transaction_year": g.transaction_year,
                    "transaction_month": g.transaction_month,
                    "transaction_record_id": list(g.transaction_record_id or []),
                    "transaction_carried_over": list(g.transaction_carried_over or []),
                }
            group_dict = dict(group_dict)
            if "weight" not in group_dict and "total_weight_kg" not in group_dict:
                group_dict["weight"] = sum(float(t.weight) if t.weight is not None else 0 for t in transports)
                group_dict["total_weight_kg"] = group_dict["weight"]
            elif "weight" not in group_dict:
                group_dict["weight"] = group_dict.get("total_weight_kg", 0)
            group_dict["children"] = build_tree(transports)
            group_dict["percentage_of_parent"] = 100.0
            group_dict["percentage_of_group"] = 100.0
            _annotate_percentages(group_dict["children"], 100.0)
            groups_with_children.append(group_dict)

        # Hierarchy: Location (origin) -> Group -> TransportTransaction tree
        by_origin: Dict[int, List[Dict[str, Any]]] = {}
        for group_dict in groups_with_children:
            oid = group_dict.get("origin_id")
            if oid is not None:
                by_origin.setdefault(oid, []).append(group_dict)
        out: List[Dict[str, Any]] = []
        for origin_id in sorted(by_origin.keys()):
            group_children = by_origin[origin_id]
            origin_weight = sum(
                float(g.get("weight") or g.get("total_weight_kg") or 0) for g in group_children
            )
            loc = location_map.get(origin_id)
            loc_name = (getattr(loc, "display_name", None) or getattr(loc, "name_en", None) or getattr(loc, "name_th", None) or f"Location {origin_id}") if loc else f"Location {origin_id}"
            origin_obj = self._location_to_dict(loc, path=path_map.get(origin_id, "")) if loc else None
            out.append({
                "id": origin_id,
                "origin_id": origin_id,
                "name": loc_name,
                "display_name": loc_name,
                "weight": origin_weight,
                "origin": origin_obj,
                "children": group_children,
            })
        return {"data": out}

    def get_traceability_hierarchy_per_row(
        self,
        organization_id: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Build a hierarchy for *each* transport transaction row in the database.

        The result is a list where each element corresponds to a single
        TransportTransaction from the organization and date filters.  Every
        returned transaction is treated as a root node and its descendants
        (children, grandchildren, etc.) are nested recursively under it.  This
        is useful when the caller wants a row‑centric view of the traceability
        tree instead of the group/origin grouping provided by
        :meth:`get_traceability_hierarchy`.

        Query parameters accepted through ``kwargs`` are the same as for
        :meth:`get_traceability_hierarchy` with the exception that ``date_from``
        and ``date_to`` filter the *updated_date* of the root transactions
        rather than constraining by calendar month.  The returned list is
        ordered by ``updated_date`` descending.
        """
        if organization_id is None:
            return {"data": []}

        # date filters operate on updated_date
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        def _parse_dt(val: Any) -> Optional[datetime]:
            if not val:
                return None
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        df = _parse_dt(date_from)
        dt = _parse_dt(date_to)

        # load all transports for org so we can build full child trees
        transports = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.organization_id == organization_id,
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .all()
        )
        if not transports:
            return {"data": []}

        # build lookup maps for tree construction
        by_parent: Dict[Optional[int], List[Any]] = {}
        id_map: Dict[int, Any] = {}
        location_ids = set()
        material_ids = set()
        for t in transports:
            id_map[t.id] = t
            pid = t.parent_id
            by_parent.setdefault(pid, []).append(t)
            if t.origin_id:
                location_ids.add(t.origin_id)
            dest = getattr(t, "destination_id", None)
            if dest:
                location_ids.add(dest)
            if t.material_id:
                material_ids.add(t.material_id)

        # gather location/material metadata just as in get_traceability_hierarchy
        path_map: Dict[int, str] = {}
        location_map: Dict[int, Any] = {}
        if location_ids:
            from ..users.user_service import UserService

            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(
                organization_id, [{"id": lid} for lid in location_ids]
            ) or {}
            locs = (
                self.db.query(UserLocation)
                .filter(UserLocation.id.in_(location_ids))
                .all()
            )
            location_map = {loc.id: loc for loc in locs}

        from ....models.cores.references import Material

        material_map: Dict[int, Any] = {}
        if material_ids:
            mats = (
                self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            )
            material_map = {m.id: m for m in mats}

        def transport_to_node(r: Any) -> Dict[str, Any]:
            origin = None
            if r.origin_id and r.origin_id in location_map:
                origin = self._location_to_dict(
                    location_map[r.origin_id], path=path_map.get(r.origin_id, "")
                )
            destination = None
            dest_id = getattr(r, "destination_id", None)
            if dest_id and dest_id in location_map:
                destination = self._location_to_dict(
                    location_map[dest_id], path=path_map.get(dest_id, "")
                )
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            return {
                "id": r.id,
                "transport_transaction_id": r.id,
                "parent_id": r.parent_id,
                "origin_id": r.origin_id,
                "destination_id": dest_id,
                "weight": float(r.weight) if r.weight is not None else None,
                "status": r.status,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "disposal_method": r.disposal_method,
                "meta_data": r.meta_data or {},
                "is_root": r.is_root,
                "absolute_percentage": float(r.absolute_percentage) if r.absolute_percentage is not None else None,
                "origin": origin,
                "destination": destination,
                "material": material,
                "children": [],
            }

        def _build_subtree(root: Any) -> Dict[str, Any]:
            node = transport_to_node(root)
            children = by_parent.get(root.id, [])
            children = sorted(children, key=lambda x: x.id)
            node["children"] = [_build_subtree(child) for child in children]
            return node

        # pick roots using the date filters
        roots = transports
        if df is not None:
            roots = [t for t in roots if t.updated_date and t.updated_date >= df]
        if dt is not None:
            roots = [t for t in roots if t.updated_date and t.updated_date <= dt]
        # order the root list by updated_date descending
        roots = sorted(
            roots, key=lambda x: x.updated_date or datetime.min, reverse=True
        )

        # pagination
        try:
            page = max(1, int(kwargs.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = max(1, min(100, int(kwargs.get("page_size", 10))))
        except (ValueError, TypeError):
            page_size = 20

        total_items = len(roots)
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
        start = (page - 1) * page_size
        end = start + page_size
        paginated_roots = roots[start:end]

        data = [_build_subtree(r) for r in paginated_roots]
        return {
            "data": data,
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        }

    def _parse_month_range(self, date_from: Any, date_to: Any) -> Tuple[Optional[int], Optional[int]]:
        """Parse date_from as start of month; return (year, month) in TRACEABILITY_DATE_TZ so 2026-03-01T00:00:00+07:00 -> (2026, 3)."""
        dt_from = None
        if date_from:
            try:
                dt = datetime.fromisoformat(str(date_from).replace("Z", "+00:00"))
                dt_from = dt
            except (ValueError, TypeError):
                pass
        if dt_from is None:
            return (None, None)
        # Use the calendar month in the request timezone (do not convert to UTC or we get wrong month)
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(TRACEABILITY_DATE_TZ)
        except ImportError:
            import pytz
            tz = pytz.timezone(TRACEABILITY_DATE_TZ)
        if getattr(dt_from, "tzinfo", None) is None:
            dt_from = dt_from.replace(tzinfo=timezone.utc)
        local = dt_from.astimezone(tz)
        return (local.year, local.month)

    def _last_month(self, year: int, month: int) -> Tuple[int, int]:
        """Return (year, month) for the previous month."""
        if month == 1:
            return (year - 1, 12)
        return (year, month - 1)

    def _apply_idle_carry_over(self, organization_id: int, requested_year: int, requested_month: int) -> None:
        """
        Idle carry-over: find idle TransportTransactions whose group is in *last* month (relative to requested).
        For each such idle, find a group in the *requested* month with the same (origin_id, material_id, location_tag_id, tenant_id).
        Append the idle's id to that group's transaction_carried_over. If no such group exists, create one with no records and only this carried_over.
        """
        last_year, last_month = self._last_month(requested_year, requested_month)
        idles = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.status == "idle",
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
                TransportTransaction.transaction_group_id.isnot(None),
                TransportTransaction.organization_id == organization_id,
            )
            .all()
        )
        group_ids = list({t.transaction_group_id for t in idles if t.transaction_group_id is not None})
        if not group_ids:
            return
        groups_last_month = (
            self.db.query(TraceabilityTransactionGroup)
            .filter(
                TraceabilityTransactionGroup.id.in_(group_ids),
                TraceabilityTransactionGroup.transaction_year == last_year,
                TraceabilityTransactionGroup.transaction_month == last_month,
            )
            .all()
        )
        group_by_id = {g.id: g for g in groups_last_month}
        for t in idles:
            if t.transaction_group_id is None:
                continue
            orig_group = group_by_id.get(t.transaction_group_id)
            if orig_group is None:
                continue
            origin_id = orig_group.origin_id
            material_id = orig_group.material_id
            location_tag_id = orig_group.location_tag_id
            tenant_id = orig_group.tenant_id
            target = (
                self.db.query(TraceabilityTransactionGroup)
                .filter(
                    TraceabilityTransactionGroup.organization_id == organization_id,
                    TraceabilityTransactionGroup.origin_id == origin_id,
                    TraceabilityTransactionGroup.material_id == material_id,
                    TraceabilityTransactionGroup.location_tag_id == location_tag_id,
                    TraceabilityTransactionGroup.tenant_id == tenant_id,
                    TraceabilityTransactionGroup.transaction_year == requested_year,
                    TraceabilityTransactionGroup.transaction_month == requested_month,
                    TraceabilityTransactionGroup.deleted_date.is_(None),
                    TraceabilityTransactionGroup.is_active == True,
                )
                .first()
            )
            if target:
                carried = list(target.transaction_carried_over or [])
                if t.id not in carried:
                    carried.append(t.id)
                    target.transaction_carried_over = carried
                    target.updated_date = datetime.now(timezone.utc)
            else:
                new_group = TraceabilityTransactionGroup(
                    origin_id=origin_id,
                    material_id=material_id,
                    organization_id=organization_id,
                    location_tag_id=location_tag_id,
                    tenant_id=tenant_id,
                    transaction_record_id=[],
                    transaction_carried_over=[t.id],
                    transaction_year=requested_year,
                    transaction_month=requested_month,
                    is_active=True,
                )
                self.db.add(new_group)
        self.db.flush()

    def _records_for_org_month_year(
        self, organization_id: int, year: int, month: int, kwargs: Any
    ) -> List[TransactionRecord]:
        """Return transaction records for this org in the given month/year (with optional material_id, origin_id filters). Uses TRACEABILITY_DATE_TZ for year/month so 2026-01-01 00:00+07 is Jan 2026."""
        txn_date_at_tz = TransactionRecord.transaction_date.op("AT TIME ZONE")(TRACEABILITY_DATE_TZ)
        filters = [
            Transaction.organization_id == organization_id,
            TransactionRecord.is_active == True,
            TransactionRecord.deleted_date.is_(None),
            Transaction.status == TransactionStatus.approved,
            TransactionRecord.status == 'approved',
            func.extract("year", txn_date_at_tz) == year,
            func.extract("month", txn_date_at_tz) == month,
        ]
        material_id_param = kwargs.get("material_id")
        if material_id_param:
            try:
                material_ids = [int(x.strip()) for x in str(material_id_param).split(",") if x.strip()]
                if material_ids:
                    filters.append(TransactionRecord.material_id.in_(material_ids))
            except ValueError:
                pass
        origin_id_param = kwargs.get("origin_id")
        if origin_id_param:
            parts = [p.strip() for p in str(origin_id_param).strip().split("|")]
            try:
                if len(parts) >= 1 and parts[0]:
                    filters.append(Transaction.origin_id == int(parts[0]))
                if len(parts) >= 2 and parts[1]:
                    filters.append(Transaction.location_tag_id == int(parts[1]))
                if len(parts) >= 3 and parts[2]:
                    filters.append(Transaction.tenant_id == int(parts[2]))
            except (ValueError, TypeError):
                pass
        return (
            self.db.query(TransactionRecord)
            .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
            .options(
                joinedload(TransactionRecord.material),
                joinedload(TransactionRecord.created_transaction).joinedload(Transaction.origin),
                joinedload(TransactionRecord.destination),
            )
            .filter(and_(*filters))
            .all()
        )

    def _backfill_traceability_groups_for_month(
        self, organization_id: int, year: int, month: int, kwargs: Any
    ) -> None:
        """Create groups for transaction records in this org/month/year that are not in any group yet.
        If an existing group with the same (origin, material, tag, tenant) has already been processed
        (has any TransportTransaction), do not append to it; create a new group for the remaining records.
        """
        records = self._records_for_org_month_year(organization_id, year, month, kwargs)
        if not records:
            return
        existing_groups = (
            self.db.query(TraceabilityTransactionGroup)
            .filter(
                TraceabilityTransactionGroup.organization_id == organization_id,
                TraceabilityTransactionGroup.transaction_year == year,
                TraceabilityTransactionGroup.transaction_month == month,
                TraceabilityTransactionGroup.deleted_date.is_(None),
                TraceabilityTransactionGroup.is_active == True,
            )
            .all()
        )
        existing_group_ids = [g.id for g in existing_groups]
        group_ids_already_processed: set = set()
        if existing_group_ids:
            processed = (
                self.db.query(TransportTransaction.transaction_group_id)
                .filter(
                    TransportTransaction.transaction_group_id.in_(existing_group_ids),
                    TransportTransaction.is_active == True,
                    TransportTransaction.deleted_date.is_(None),
                )
                .distinct()
                .all()
            )
            group_ids_already_processed = {r[0] for r in processed if r[0] is not None}
        record_ids_in_groups = set()
        key_to_existing_group: Dict[Tuple[Any, ...], TraceabilityTransactionGroup] = {}
        for g in existing_groups:
            for rid in g.transaction_record_id or []:
                record_ids_in_groups.add(rid)
            key = (g.origin_id, g.material_id, g.location_tag_id, g.tenant_id, year, month)
            key_to_existing_group[key] = g
        remaining = [r for r in records if r.id not in record_ids_in_groups]
        if not remaining:
            return
        from collections import defaultdict
        key_to_records: Dict[Tuple[Any, ...], List[TransactionRecord]] = defaultdict(list)
        for r in remaining:
            txn = r.created_transaction
            origin_id = txn.origin_id if txn else None
            location_tag_id = getattr(txn, "location_tag_id", None) if txn else None
            tenant_id = getattr(txn, "tenant_id", None) if txn else None
            key = (origin_id, r.material_id, location_tag_id, tenant_id, year, month)
            key_to_records[key].append(r)
        for (origin_id, material_id, location_tag_id, tenant_id, _, _), group_records in key_to_records.items():
            record_ids = list(dict.fromkeys(r.id for r in group_records))
            key = (origin_id, material_id, location_tag_id, tenant_id, year, month)
            existing = key_to_existing_group.get(key)
            if existing and existing.id not in group_ids_already_processed:
                existing_record_ids = list(dict.fromkeys(existing.transaction_record_id or []))
                existing_set = set(existing_record_ids)
                for rid in record_ids:
                    if rid not in existing_set:
                        existing_record_ids.append(rid)
                        existing_set.add(rid)
                existing.transaction_record_id = existing_record_ids
                existing.updated_date = datetime.now(timezone.utc)
            else:
                group = TraceabilityTransactionGroup(
                    origin_id=origin_id,
                    material_id=material_id,
                    organization_id=organization_id,
                    transaction_record_id=record_ids,
                    transaction_carried_over=[],
                    transaction_year=year,
                    transaction_month=month,
                    location_tag_id=location_tag_id,
                    tenant_id=tenant_id,
                    is_active=True,
                )
                self.db.add(group)
        self.db.flush()

    def _build_tentative_groups(
        self, organization_id: int, year: int, month: int, kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Build in-memory tentative groups for approved records that have no active traceability group.
        These appear as normal cards in column 1 but are not persisted until dispatch."""
        records = self._records_for_org_month_year(organization_id, year, month, kwargs)
        if not records:
            return []

        # Batch-check which traceability_group_ids are still active
        group_ids_on_records = {r.traceability_group_id for r in records if r.traceability_group_id is not None}
        active_group_ids: set = set()
        if group_ids_on_records:
            rows = self.db.query(TraceabilityTransactionGroup.id).filter(
                TraceabilityTransactionGroup.id.in_(list(group_ids_on_records)),
                TraceabilityTransactionGroup.is_active == True,
                TraceabilityTransactionGroup.deleted_date.is_(None),
            ).all()
            active_group_ids = {r[0] for r in rows}

        # Filter to orphaned records: no group_id or group is soft-deleted
        orphaned = [
            r for r in records
            if r.traceability_group_id is None or r.traceability_group_id not in active_group_ids
        ]
        if not orphaned:
            return []

        # Group by (origin_id, material_id, location_tag_id, tenant_id)
        from collections import defaultdict
        key_to_records: Dict[Tuple[Any, ...], List[TransactionRecord]] = defaultdict(list)
        for r in orphaned:
            txn = r.created_transaction
            origin_id = txn.origin_id if txn else None
            location_tag_id = getattr(txn, "location_tag_id", None) if txn else None
            tenant_id = getattr(txn, "tenant_id", None) if txn else None
            key = (origin_id, r.material_id, location_tag_id, tenant_id)
            key_to_records[key].append(r)

        # Enrich: collect location/material IDs
        location_ids = set()
        material_ids = set()
        for (origin_id, material_id, _, _) in key_to_records:
            if origin_id is not None:
                location_ids.add(origin_id)
            if material_id is not None:
                material_ids.add(material_id)

        path_map: Dict[int, str] = {}
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in location_ids]) or {}
        from ....models.cores.references import Material
        material_map = {}
        if material_ids:
            mats = self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            material_map = {m.id: m for m in mats}
        location_map = {}
        if location_ids:
            locs = self.db.query(UserLocation).filter(UserLocation.id.in_(location_ids)).all()
            location_map = {loc.id: loc for loc in locs}

        # Build tentative group dicts
        out = []
        for (origin_id, material_id, location_tag_id, tenant_id), recs in key_to_records.items():
            record_ids = list(dict.fromkeys(r.id for r in recs))
            total_weight = sum(float(r.origin_weight_kg or 0) for r in recs)
            tentative_id = f"tentative:{origin_id}:{material_id}:{location_tag_id}:{tenant_id}:{year}:{month}"

            origin = None
            if origin_id and origin_id in location_map:
                origin = self._location_to_dict(location_map[origin_id], path=path_map.get(origin_id, ""))
            material = None
            if material_id and material_id in material_map:
                material = self._material_to_dict(material_map[material_id])

            out.append({
                "id": tentative_id,
                "group_id": tentative_id,
                "origin_id": origin_id,
                "material_id": material_id,
                "organization_id": organization_id,
                "transaction_record_id": record_ids,
                "transaction_carried_over": [],
                "transaction_year": year,
                "transaction_month": month,
                "location_tag_id": location_tag_id,
                "tenant_id": tenant_id,
                "total_weight_kg": total_weight,
                "weight": total_weight,
                "record_ids": record_ids,
                "origin": origin,
                "material": material,
                "source": "tentative",
            })
        return out

    def materialize_tentative_group(
        self, tentative_group_key: str, organization_id: int
    ) -> Dict[str, Any]:
        """Parse tentative key, create real TraceabilityTransactionGroup, link approved records."""
        try:
            parts = tentative_group_key.split(":")
            if len(parts) != 7 or parts[0] != "tentative":
                return {"success": False, "message": "Invalid tentative group key"}

            def _parse(val: str):
                return None if val == "None" else int(val)

            origin_id = _parse(parts[1])
            material_id = _parse(parts[2])
            location_tag_id = _parse(parts[3])
            tenant_id = _parse(parts[4])
            year = int(parts[5])
            month = int(parts[6])

            # Check if a real group already exists for this key
            existing = self.db.query(TraceabilityTransactionGroup).filter(
                TraceabilityTransactionGroup.origin_id == origin_id if origin_id is not None
                    else TraceabilityTransactionGroup.origin_id.is_(None),
                TraceabilityTransactionGroup.material_id == material_id if material_id is not None
                    else TraceabilityTransactionGroup.material_id.is_(None),
                TraceabilityTransactionGroup.organization_id == organization_id,
                TraceabilityTransactionGroup.location_tag_id == location_tag_id if location_tag_id is not None
                    else TraceabilityTransactionGroup.location_tag_id.is_(None),
                TraceabilityTransactionGroup.tenant_id == tenant_id if tenant_id is not None
                    else TraceabilityTransactionGroup.tenant_id.is_(None),
                TraceabilityTransactionGroup.transaction_year == year,
                TraceabilityTransactionGroup.transaction_month == month,
                TraceabilityTransactionGroup.is_active == True,
                TraceabilityTransactionGroup.deleted_date.is_(None),
            ).first()

            # Find all orphaned approved records matching this key
            txn_date_at_tz = TransactionRecord.transaction_date.op("AT TIME ZONE")(TRACEABILITY_DATE_TZ)
            record_query = (
                self.db.query(TransactionRecord)
                .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
                .filter(
                    Transaction.organization_id == organization_id,
                    Transaction.status == TransactionStatus.approved,
                    TransactionRecord.status == 'approved',
                    TransactionRecord.is_active == True,
                    TransactionRecord.deleted_date.is_(None),
                    func.extract("year", txn_date_at_tz) == year,
                    func.extract("month", txn_date_at_tz) == month,
                    TransactionRecord.material_id == material_id if material_id is not None
                        else TransactionRecord.material_id.is_(None),
                    Transaction.origin_id == origin_id if origin_id is not None
                        else Transaction.origin_id.is_(None),
                    Transaction.location_tag_id == location_tag_id if location_tag_id is not None
                        else Transaction.location_tag_id.is_(None),
                    Transaction.tenant_id == tenant_id if tenant_id is not None
                        else Transaction.tenant_id.is_(None),
                    or_(
                        TransactionRecord.traceability_group_id.is_(None),
                        ~TransactionRecord.traceability_group_id.in_(
                            self.db.query(TraceabilityTransactionGroup.id).filter(
                                TraceabilityTransactionGroup.is_active == True,
                                TraceabilityTransactionGroup.deleted_date.is_(None),
                            )
                        ),
                    ),
                )
            )
            orphaned_records = record_query.all()
            record_ids = [r.id for r in orphaned_records]

            if existing:
                # Append orphaned records to existing group
                current_ids = set(existing.transaction_record_id or [])
                new_ids = [rid for rid in record_ids if rid not in current_ids]
                if new_ids:
                    existing.transaction_record_id = list(current_ids) + new_ids
                    existing.updated_date = datetime.now(timezone.utc)
                    self.db.query(TransactionRecord).filter(
                        TransactionRecord.id.in_(new_ids)
                    ).update(
                        {TransactionRecord.traceability_group_id: existing.id},
                        synchronize_session=False,
                    )
                self.db.flush()
                return {"success": True, "group_id": existing.id}

            # Create new group
            group = TraceabilityTransactionGroup(
                origin_id=origin_id,
                material_id=material_id,
                organization_id=organization_id,
                transaction_record_id=record_ids,
                transaction_carried_over=[],
                transaction_year=year,
                transaction_month=month,
                location_tag_id=location_tag_id,
                tenant_id=tenant_id,
                is_active=True,
            )
            self.db.add(group)
            self.db.flush()

            # Set reverse pointer on all records
            if record_ids:
                self.db.query(TransactionRecord).filter(
                    TransactionRecord.id.in_(record_ids)
                ).update(
                    {TransactionRecord.traceability_group_id: group.id},
                    synchronize_session=False,
                )

            return {"success": True, "group_id": group.id}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"materialize_tentative_group failed: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def _groups_to_dict_list(
        self, groups: List[TraceabilityTransactionGroup], organization_id: int
    ) -> List[Dict[str, Any]]:
        """Convert groups to list of dicts with id, origin_id, material_id, transaction_record_id, transaction_carried_over, weights, origin, material."""
        if not groups:
            return []
        location_ids = set()
        material_ids = set()
        for g in groups:
            if g.origin_id is not None:
                location_ids.add(g.origin_id)
            if g.material_id is not None:
                material_ids.add(g.material_id)
        path_map: Dict[int, str] = {}
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in location_ids]) or {}
        from ....models.cores.references import Material
        material_map = {}
        if material_ids:
            mats = self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            material_map = {m.id: m for m in mats}
        location_map = {}
        if location_ids:
            locs = self.db.query(UserLocation).filter(UserLocation.id.in_(location_ids)).all()
            location_map = {loc.id: loc for loc in locs}
        record_ids = []
        carried_over_ids = []
        for g in groups:
            record_ids.extend(g.transaction_record_id or [])
            carried_over_ids.extend(g.transaction_carried_over or [])
        record_ids = list(set(record_ids))
        carried_over_ids = list(set(carried_over_ids))
        weight_by_record: Dict[int, float] = {}
        if record_ids:
            rows = self.db.query(TransactionRecord.id, TransactionRecord.origin_weight_kg).filter(
                TransactionRecord.id.in_(record_ids),
                TransactionRecord.status == 'approved',
            ).all()
            weight_by_record = {r[0]: float(r[1] or 0) for r in rows}
        weight_by_carried_over: Dict[int, float] = {}
        if carried_over_ids:
            transport_rows = self.db.query(TransportTransaction.id, TransportTransaction.weight).filter(
                TransportTransaction.id.in_(carried_over_ids),
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            ).all()
            weight_by_carried_over = {r[0]: float(r[1] or 0) for r in transport_rows}
        out = []
        for g in groups:
            record_ids_g = list(g.transaction_record_id or [])
            record_weight = sum(weight_by_record.get(rid, 0) for rid in record_ids_g)
            carried_weight = sum(weight_by_carried_over.get(tid, 0) for tid in (g.transaction_carried_over or []))
            total_weight = record_weight + carried_weight
            origin = None
            if g.origin_id and g.origin_id in location_map:
                origin = self._location_to_dict(
                    location_map[g.origin_id],
                    path=path_map.get(g.origin_id, ""),
                )
            material = None
            if g.material_id and g.material_id in material_map:
                material = self._material_to_dict(material_map[g.material_id])
            out.append({
                "id": g.id,
                "group_id": g.id,
                "origin_id": g.origin_id,
                "material_id": g.material_id,
                "organization_id": g.organization_id,
                "transaction_record_id": record_ids_g,
                "transaction_carried_over": list(g.transaction_carried_over or []),
                "transaction_year": g.transaction_year,
                "transaction_month": g.transaction_month,
                "location_tag_id": g.location_tag_id,
                "tenant_id": g.tenant_id,
                "total_weight_kg": total_weight,
                "weight": total_weight,
                "record_ids": record_ids_g,
                "origin": origin,
                "material": material,
                "source": "group",
            })
        return out

    def _arrived_transport_as_first_array(
        self, group_ids: List[int], organization_id: int
    ) -> List[Dict[str, Any]]:
        """Return arrived TransportTransactions (status='arrived') that do NOT have disposal_method, as first-array items. Only include the latest (leaf) in each chain: if A->B->C and all are arrived-no-method, only C."""
        rows = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.transaction_group_id.in_(group_ids),
                TransportTransaction.status == "arrived",
                or_(
                    TransportTransaction.disposal_method.is_(None),
                    TransportTransaction.disposal_method == "",
                ),
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .all()
        )
        if not rows:
            return []
        ids_in_set = {r.id for r in rows}
        parent_ids_in_set = {r.parent_id for r in rows if r.parent_id is not None and r.parent_id in ids_in_set}
        rows = [r for r in rows if r.id not in parent_ids_in_set]
        if not rows:
            return []
        destination_ids = set()
        for r in rows:
            dest_id = getattr(r, "destination_id", None)
            if dest_id is None and r.meta_data and isinstance(r.meta_data, dict):
                dest_id = r.meta_data.get("destination_id")
            if dest_id is not None:
                try:
                    destination_ids.add(int(dest_id))
                except (TypeError, ValueError):
                    pass
        path_map: Dict[int, str] = {}
        location_map = {}
        if destination_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in destination_ids]) or {}
            locs = self.db.query(UserLocation).filter(UserLocation.id.in_(destination_ids)).all()
            location_map = {loc.id: loc for loc in locs}
        from ....models.cores.references import Material
        material_ids = {r.material_id for r in rows if r.material_id is not None}
        material_map = {}
        if material_ids:
            mats = self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            material_map = {m.id: m for m in mats}
        out = []
        for r in rows:
            dest_id = getattr(r, "destination_id", None)
            if dest_id is None and r.meta_data and isinstance(r.meta_data, dict):
                raw = r.meta_data.get("destination_id")
                if raw is not None:
                    try:
                        dest_id = int(raw)
                    except (TypeError, ValueError):
                        pass
            origin = None
            if dest_id and dest_id in location_map:
                origin = self._location_to_dict(
                    location_map[dest_id],
                    path=path_map.get(dest_id, ""),
                )
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            out.append({
                "transport_transaction_id": r.id,
                "id": r.id,
                "origin_id": dest_id,
                "origin": origin,
                "material_id": r.material_id,
                "material": material,
                "weight": float(r.weight) if r.weight is not None else None,
                "transaction_group_id": r.transaction_group_id,
                "status": r.status,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "source": "arrived_transport",
            })
        return out

    def _transport_transactions_for_groups(
        self, group_ids: List[int], organization_id: int
    ) -> List[Dict[str, Any]]:
        """Return traceability_transport_transactions where transaction_group_id in group_ids, status != 'idle' and status != 'arrived' (exclude items that appear in first or third array)."""
        rows = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.transaction_group_id.in_(group_ids),
                TransportTransaction.status != "idle",
                TransportTransaction.status != "arrived",
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .all()
        )
        if not rows:
            return []
        location_ids = {r.origin_id for r in rows if r.origin_id is not None}
        for r in rows:
            dest_id = getattr(r, "destination_id", None)
            if dest_id is not None:
                location_ids.add(dest_id)
        material_ids = {r.material_id for r in rows if r.material_id is not None}
        path_map: Dict[int, str] = {}
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in location_ids]) or {}
        location_map = {}
        if location_ids:
            locs = self.db.query(UserLocation).filter(UserLocation.id.in_(location_ids)).all()
            location_map = {loc.id: loc for loc in locs}
        from ....models.cores.references import Material
        material_map = {}
        if material_ids:
            mats = self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            material_map = {m.id: m for m in mats}
        out = []
        for r in rows:
            origin = None
            if r.origin_id and r.origin_id in location_map:
                origin = self._location_to_dict(location_map[r.origin_id], path=path_map.get(r.origin_id, ""))
            dest_id = getattr(r, "destination_id", None)
            destination = None
            if dest_id and dest_id in location_map:
                destination = self._location_to_dict(location_map[dest_id], path=path_map.get(dest_id, ""))
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            out.append({
                "id": r.id,
                "transaction_group_id": r.transaction_group_id,
                "origin_id": r.origin_id,
                "destination_id": dest_id,
                "material_id": r.material_id,
                "weight": float(r.weight) if r.weight is not None else None,
                "meta_data": r.meta_data or {},
                "organization_id": r.organization_id,
                "disposal_method": r.disposal_method,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "status": r.status,
                "is_root": r.is_root,
                "absolute_percentage": float(r.absolute_percentage) if r.absolute_percentage is not None else None,
                "parent_id": r.parent_id,
                "created_date": r.created_date.isoformat() if r.created_date else None,
                "updated_date": r.updated_date.isoformat() if r.updated_date else None,
                "origin": origin,
                "destination": destination,
                "material": material,
            })
        return out

    def _transport_transactions_with_arrival_for_groups(
        self, group_ids: List[int], organization_id: int
    ) -> List[Dict[str, Any]]:
        """Return traceability_transport_transactions where transaction_group_id in group_ids, arrival_date set, status='arrived', and disposal_method present (have the method)."""
        rows = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.transaction_group_id.in_(group_ids),
                TransportTransaction.arrival_date.isnot(None),
                TransportTransaction.status == "arrived",
                TransportTransaction.disposal_method.isnot(None),
                TransportTransaction.disposal_method != "",
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .all()
        )
        if not rows:
            return []
        location_ids = {r.origin_id for r in rows if r.origin_id is not None}
        for r in rows:
            dest_id = getattr(r, "destination_id", None)
            if dest_id is not None:
                location_ids.add(dest_id)
        material_ids = {r.material_id for r in rows if r.material_id is not None}
        path_map: Dict[int, str] = {}
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in location_ids]) or {}
        location_map = {}
        if location_ids:
            locs = self.db.query(UserLocation).filter(UserLocation.id.in_(location_ids)).all()
            location_map = {loc.id: loc for loc in locs}
        from ....models.cores.references import Material
        material_map = {}
        if material_ids:
            mats = self.db.query(Material).filter(Material.id.in_(material_ids)).all()
            material_map = {m.id: m for m in mats}
        out = []
        for r in rows:
            origin = None
            if r.origin_id and r.origin_id in location_map:
                origin = self._location_to_dict(location_map[r.origin_id], path=path_map.get(r.origin_id, ""))
            dest_id = getattr(r, "destination_id", None)
            destination = None
            if dest_id and dest_id in location_map:
                destination = self._location_to_dict(location_map[dest_id], path=path_map.get(dest_id, ""))
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            out.append({
                "id": r.id,
                "transaction_group_id": r.transaction_group_id,
                "origin_id": r.origin_id,
                "destination_id": dest_id,
                "material_id": r.material_id,
                "weight": float(r.weight) if r.weight is not None else None,
                "meta_data": r.meta_data or {},
                "organization_id": r.organization_id,
                "disposal_method": r.disposal_method,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "status": r.status,
                "is_root": r.is_root,
                "absolute_percentage": float(r.absolute_percentage) if r.absolute_percentage is not None else None,
                "parent_id": r.parent_id,
                "created_date": r.created_date.isoformat() if r.created_date else None,
                "updated_date": r.updated_date.isoformat() if r.updated_date else None,
                "origin": origin,
                "destination": destination,
                "material": material,
            })
        return out

    def _group_records_like_traceability_group(
        self,
        records: List[TransactionRecord],
        path_map: Dict[int, str],
    ) -> List[Dict[str, Any]]:
        """
        Group records by (origin_id, material_id, location_tag_id, tenant_id, transaction_year, transaction_month).
        Return one item per group with summed weight and array of record_ids. Same grouping as traceability_transaction_group.
        """
        from collections import defaultdict
        key_to_records: Dict[tuple, List[TransactionRecord]] = defaultdict(list)
        for r in records:
            txn = r.created_transaction
            origin_id = txn.origin_id if txn else None
            location_tag_id = getattr(txn, "location_tag_id", None) if txn else None
            tenant_id = getattr(txn, "tenant_id", None) if txn else None
            rec_date = getattr(r, "transaction_date", None)
            txn_date = getattr(txn, "transaction_date", None) if txn else None
            date_for_ym = rec_date if (rec_date and hasattr(rec_date, "year")) else txn_date
            year = date_for_ym.year if date_for_ym and hasattr(date_for_ym, "year") else None
            month = date_for_ym.month if date_for_ym and hasattr(date_for_ym, "month") else None
            key = (origin_id, r.material_id, location_tag_id, tenant_id, year, month)
            key_to_records[key].append(r)

        out: List[Dict[str, Any]] = []
        for (origin_id, material_id, location_tag_id, tenant_id, year, month), group_records in key_to_records.items():
            total_weight = sum(float(getattr(r, "origin_weight_kg", None) or 0) for r in group_records)
            record_ids = [r.id for r in group_records]
            first = group_records[0]
            origin = None
            if first.created_transaction and first.created_transaction.origin:
                origin = self._location_to_dict(
                    first.created_transaction.origin,
                    path=path_map.get(first.created_transaction.origin.id, "") if path_map else "",
                )
            material = self._material_to_dict(first.material) if first.material else None
            out.append({
                "origin_id": origin_id,
                "material_id": material_id,
                "location_tag_id": location_tag_id,
                "tenant_id": tenant_id,
                "transaction_year": year,
                "transaction_month": month,
                "weight": total_weight,
                "total_weight_kg": total_weight,
                "record_ids": record_ids,
                "origin": origin,
                "material": material,
            })
        return out

    def get_destination_locations(self, organization_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get locations that are destination options: UserLocation with is_location=True and type='hub'.
        Used as options for destination input (e.g. dropdown). Each location includes path.
        """
        if organization_id is None:
            return []

        locations = (
            self.db.query(UserLocation)
            .filter(
                UserLocation.organization_id == organization_id,
                UserLocation.is_location == True,
                UserLocation.type == "hub",
                UserLocation.is_active == True,
                UserLocation.deleted_date.is_(None),
            )
            .all()
        )
        if not locations:
            return []

        location_ids = [loc.id for loc in locations]
        path_map: Dict[int, str] = {}
        from ..users.user_service import UserService
        user_service = UserService(self.db)
        location_data = [{"id": lid} for lid in location_ids]
        path_map = user_service._build_location_paths(organization_id, location_data) or {}

        return [
            self._location_to_dict(loc, path=path_map.get(loc.id, ""))
            for loc in locations
        ]

    # disposal_method body value -> store in Transaction.disposal_method
    _DISPOSAL_METHOD_VALUES = frozenset({
        "Composted by municipality",
        "Municipality receive",
        "Incineration without energy",
        "Incineration with energy",
    })
    # disposal_method body value -> store in Transaction.treatment_method
    _TREATMENT_METHOD_VALUES = frozenset({
        "Preparation for reuse",
        "Recycling (Own)",
        "Other recover operation",
        "Recycle",
    })

    def create_transport_transaction(
        self,
        record_id: int,
        weight: float,
        origin_id: int,
        destination_id: int,
        vehicle_info: Any,
        messenger_info: Any,
        created_by_id: int,
        organization_id: int,
        disposal_method: Any = None,
    ) -> Dict[str, Any]:
        """
        Create a transport transaction for an existing record and link it.
        - Creates a Transaction with status=pending, transaction_method='transport',
          vehicle_info, driver_info (from messenger_info), transaction_records=[record_id],
          destination_ids=[destination_id], weight_kg, origin_id.
        - If disposal_method (body) is provided: stored in Transaction.disposal_method
          or Transaction.treatment_method depending on value (disposal vs treatment set).
        - Updates the record: destination_id = destination_id,
          traceability = record.traceability + [new_transaction_id].
        """
        record = (
            self.db.query(TransactionRecord)
            .options(joinedload(TransactionRecord.created_transaction))
            .filter(
                TransactionRecord.id == record_id,
                TransactionRecord.is_active == True,
                TransactionRecord.deleted_date.is_(None),
            )
            .first()
        )
        if not record:
            return {"success": False, "message": "Record not found", "transaction_id": None}
        if not record.created_transaction:
            return {"success": False, "message": "Record has no creating transaction", "transaction_id": None}
        if record.created_transaction.organization_id != organization_id:
            return {"success": False, "message": "Record does not belong to this organization", "transaction_id": None}

        # Normalize vehicle_info / driver_info to dicts (API may send strings)
        v_info = vehicle_info if isinstance(vehicle_info, dict) else ({"license_plate": str(vehicle_info)} if vehicle_info else None)
        d_info = messenger_info if isinstance(messenger_info, dict) else ({"name": str(messenger_info)} if messenger_info else None)

        # Map body disposal_method to Transaction.disposal_method or Transaction.treatment_method
        disposal_method_val = (disposal_method or "").strip() if isinstance(disposal_method, str) else None
        tx_disposal = disposal_method_val if disposal_method_val in self._DISPOSAL_METHOD_VALUES else None
        tx_treatment = disposal_method_val if disposal_method_val in self._TREATMENT_METHOD_VALUES else None

        transaction = Transaction(
            organization_id=organization_id,
            origin_id=origin_id,
            destination_ids=[destination_id],
            transaction_records=[record_id],
            weight_kg=Decimal(str(weight)),
            total_amount=Decimal("0"),
            status=TransactionStatus.pending,
            transaction_method="transport",
            vehicle_info=v_info,
            driver_info=d_info,
            created_by_id=created_by_id,
            disposal_method=tx_disposal,
            treatment_method=tx_treatment,
        )
        self.db.add(transaction)
        self.db.flush()

        # Update record: append new transaction to traceability, set destination
        existing_traceability = list(record.traceability or [])
        record.traceability = sorted(existing_traceability + [transaction.id])
        record.destination_id = destination_id
        self.db.flush()

        return {
            "success": True,
            "message": "Transport transaction created",
            "transaction_id": transaction.id,
            "record_id": record_id,
        }

    def create_transport_transactions(
        self,
        data: List[Dict[str, Any]],
        organization_id: int,
        transaction_group_id: Optional[int] = None,
        transport_transaction_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create rows in traceability_transport_transactions (no Transaction created).
        Either transaction_group_id (root) or transport_transaction_id (children of an arrived transport).
        When transport_transaction_id is set: use it as parent_id for all new rows and use parent's transaction_group_id.
        - vehicle_info and messenger_info are stored in meta_data.
        - is_root is False when parent_id/transport_transaction_id is set.
        - status is "in_transit" when item has destination_id/vehicle_info/messenger_info/disposal_method; otherwise "idle".
        """
        if not data:
            return {"success": False, "message": "data array is required and must not be empty", "ids": []}
        if transaction_group_id is None and transport_transaction_id is None:
            return {"success": False, "message": "transaction_group_id or transport_transaction_id is required", "ids": []}
        if transaction_group_id is not None and transport_transaction_id is not None:
            return {"success": False, "message": "Provide either transaction_group_id or transport_transaction_id, not both", "ids": []}

        parent_id_override: Optional[int] = None
        if transport_transaction_id is not None:
            parent = (
                self.db.query(TransportTransaction)
                .filter(
                    TransportTransaction.id == transport_transaction_id,
                    TransportTransaction.organization_id == organization_id,
                    TransportTransaction.is_active == True,
                    TransportTransaction.deleted_date.is_(None),
                )
                .first()
            )
            if not parent:
                return {"success": False, "message": "Parent transport transaction not found or access denied", "ids": []}
            transaction_group_id = parent.transaction_group_id
            if transaction_group_id is None:
                return {"success": False, "message": "Parent transport has no transaction_group_id", "ids": []}
            parent_id_override = transport_transaction_id
            group = (
                self.db.query(TraceabilityTransactionGroup)
                .filter(
                    TraceabilityTransactionGroup.id == transaction_group_id,
                    TraceabilityTransactionGroup.organization_id == organization_id,
                )
                .first()
            )
            if not group:
                return {"success": False, "message": "Transaction group not found or access denied", "ids": []}
        else:
            group = (
                self.db.query(TraceabilityTransactionGroup)
                .filter(
                    TraceabilityTransactionGroup.id == transaction_group_id,
                    TraceabilityTransactionGroup.organization_id == organization_id,
                    TraceabilityTransactionGroup.is_active == True,
                    TraceabilityTransactionGroup.deleted_date.is_(None),
                )
                .first()
            )
            if not group:
                return {"success": False, "message": "Transaction group not found or access denied", "ids": []}

        created_ids: List[int] = []
        for item in data:
            weight = item.get("weight")
            origin_id = item.get("origin_id")
            if weight is None or origin_id is None:
                return {
                    "success": False,
                    "message": "Each item must have weight and origin_id",
                    "ids": created_ids,
                }
            try:
                weight_val = Decimal(str(weight))
            except (TypeError, ValueError):
                return {"success": False, "message": "weight must be a number", "ids": created_ids}
            try:
                origin_id_val = int(origin_id)
            except (TypeError, ValueError):
                return {"success": False, "message": "origin_id must be an integer", "ids": created_ids}

            has_destination = item.get("destination_id") is not None
            status = "in_transit" if (has_destination) else "idle"

            meta_data: Dict[str, Any] = {}
            if item.get("vehicle_info") is not None:
                meta_data["vehicle_info"] = item["vehicle_info"]
            if item.get("messenger_info") is not None:
                meta_data["messenger_info"] = item["messenger_info"]
            if item.get("destination_id") is not None:
                meta_data["destination_id"] = int(item["destination_id"])

            parent_id_raw = parent_id_override if parent_id_override is not None else item.get("parent_id")
            parent_id_val = int(parent_id_raw) if parent_id_raw is not None else None
            is_root = parent_id_val is None

            material_id_raw = item.get("material_id")
            material_id_val = int(material_id_raw) if material_id_raw is not None else None
            disposal_method_val = (item.get("disposal_method") or "").strip() or None
            destination_id_val = None
            if item.get("destination_id") is not None:
                try:
                    destination_id_val = int(item["destination_id"])
                except (TypeError, ValueError):
                    pass

            row = TransportTransaction(
                origin_id=origin_id_val,
                destination_id=destination_id_val,
                material_id=material_id_val,
                weight=weight_val,
                meta_data=meta_data if meta_data else None,
                organization_id=organization_id,
                transaction_group_id=transaction_group_id,
                disposal_method=disposal_method_val,
                arrival_date=None,
                status=status,
                is_root=is_root,
                parent_id=parent_id_val,
            )
            self.db.add(row)
            self.db.flush()
            created_ids.append(row.id)

        # IMPORTANT: Recalculate absolute_percentage for the entire group after creating nodes.
        # Any future code that creates transport transactions must also trigger this recalculation.
        if transaction_group_id:
            self._recalculate_absolute_percentage(transaction_group_id)

        return {
            "success": True,
            "message": "Transport transactions created",
            "ids": created_ids,
        }

    def update_transport_transactions(
        self,
        data: List[Dict[str, Any]],
        organization_id: int,
    ) -> Dict[str, Any]:
        """
        Update transport transaction rows.
        Each item must have transport_transaction_id plus optional fields to update.
        If the transaction has descendants (children, grandchildren, etc.), all are soft-deleted first.
        """
        if not data:
            return {"success": False, "message": "data array is required and must not be empty"}

        now = datetime.now(timezone.utc)
        updated_ids: List[int] = []
        affected_group_ids: set = set()

        for item in data:
            tt_id = item.get("transport_transaction_id")
            if tt_id is None:
                return {"success": False, "message": "Each item must have transport_transaction_id", "ids": updated_ids}
            try:
                tt_id = int(tt_id)
            except (TypeError, ValueError):
                return {"success": False, "message": "transport_transaction_id must be an integer", "ids": updated_ids}

            row = (
                self.db.query(TransportTransaction)
                .filter(
                    TransportTransaction.id == tt_id,
                    TransportTransaction.organization_id == organization_id,
                    TransportTransaction.is_active == True,
                    TransportTransaction.deleted_date.is_(None),
                )
                .first()
            )
            if not row:
                return {"success": False, "message": f"Transport transaction {tt_id} not found or access denied", "ids": updated_ids}

            if row.transaction_group_id:
                affected_group_ids.add(row.transaction_group_id)

            # Recursively soft-delete all descendants
            self._soft_delete_descendants(tt_id, now)

            # Update fields
            if "weight" in item and item["weight"] is not None:
                try:
                    row.weight = Decimal(str(item["weight"]))
                except (TypeError, ValueError):
                    return {"success": False, "message": "weight must be a number", "ids": updated_ids}

            if "origin_id" in item and item["origin_id"] is not None:
                try:
                    row.origin_id = int(item["origin_id"])
                except (TypeError, ValueError):
                    return {"success": False, "message": "origin_id must be an integer", "ids": updated_ids}

            if "destination_id" in item:
                if item["destination_id"] is not None:
                    try:
                        row.destination_id = int(item["destination_id"])
                    except (TypeError, ValueError):
                        return {"success": False, "message": "destination_id must be an integer", "ids": updated_ids}
                else:
                    row.destination_id = None

            if "material_id" in item:
                row.material_id = int(item["material_id"]) if item["material_id"] is not None else None

            if "disposal_method" in item:
                row.disposal_method = (item["disposal_method"] or "").strip() or None

            # Update meta_data for vehicle_info / messenger_info
            meta_data = dict(row.meta_data) if row.meta_data else {}
            if "vehicle_info" in item:
                if item["vehicle_info"] is not None:
                    meta_data["vehicle_info"] = item["vehicle_info"]
                else:
                    meta_data.pop("vehicle_info", None)
            if "messenger_info" in item:
                if item["messenger_info"] is not None:
                    meta_data["messenger_info"] = item["messenger_info"]
                else:
                    meta_data.pop("messenger_info", None)
            if "destination_id" in item:
                if item["destination_id"] is not None:
                    meta_data["destination_id"] = int(item["destination_id"])
                else:
                    meta_data.pop("destination_id", None)
            row.meta_data = meta_data if meta_data else None

            # Update status based on destination
            has_destination = row.destination_id is not None
            row.status = "in_transit" if has_destination else "idle"
            row.arrival_date = None

            self.db.flush()
            updated_ids.append(tt_id)

        # IMPORTANT: Recalculate absolute_percentage for all affected groups after updates.
        # Any future code that updates transport transactions must also trigger this recalculation.
        for gid in affected_group_ids:
            self._recalculate_absolute_percentage(gid)

        return {
            "success": True,
            "message": "Transport transactions updated",
            "ids": updated_ids,
        }

    def _soft_delete_descendants(self, parent_id: int, now: datetime) -> None:
        """Recursively soft-delete all descendants of a transport transaction."""
        children = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.parent_id == parent_id,
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .all()
        )
        for child in children:
            self._soft_delete_descendants(child.id, now)
            child.is_active = False
            child.deleted_date = now
        self.db.flush()

    def _recalculate_absolute_percentage(self, transaction_group_id: int) -> None:
        """
        Recalculate absolute_percentage for ALL active transport transactions in the group.

        The calculation is cascading (compound):
          absolute_percentage = parent_absolute_percentage * (node_weight / siblings_total)
        Root-level nodes (parent_id is None) use 100 as the base.

        Example: if a node's parent has absolute_percentage=50 and the node weighs
        14 out of siblings total 16, then: 50 * (14/16) = 43.75%

        IMPORTANT: Any code that creates, updates, or reverts transport transactions
        MUST call this method afterward to keep absolute_percentage in sync.
        This value is used by reports for fast percentage lookups against the
        source group weight, without needing to traverse the tree at query time.
        """
        rows = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.transaction_group_id == transaction_group_id,
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .all()
        )
        if not rows:
            return

        # Index by id for parent lookup; group by parent_id to find sibling sets
        by_id: Dict[int, TransportTransaction] = {r.id: r for r in rows}
        by_parent: Dict[Optional[int], List[TransportTransaction]] = {}
        for r in rows:
            by_parent.setdefault(r.parent_id, []).append(r)

        # Walk the tree top-down (BFS) so parents are calculated before children
        queue: List[Optional[int]] = [None]  # start with root-level nodes (parent_id=None)
        while queue:
            parent_id = queue.pop(0)
            siblings = by_parent.get(parent_id)
            if not siblings:
                continue

            # Parent's absolute_percentage (100 for root level)
            parent_pct = float(by_id[parent_id].absolute_percentage or 100) if parent_id is not None else 100.0

            siblings_total = sum(float(s.weight or 0) for s in siblings)
            for node in siblings:
                w = float(node.weight or 0)
                if siblings_total > 0:
                    node.absolute_percentage = Decimal(str(round(parent_pct * (w / siblings_total), 2)))
                else:
                    node.absolute_percentage = Decimal("0")
                # Enqueue this node's id so its children get processed next
                if node.id in by_parent:
                    queue.append(node.id)

        self.db.flush()

    def confirm_arrival(
        self,
        transaction_id: int,
        organization_id: int,
    ) -> Dict[str, Any]:
        """
        Set arrival_date and status='arrived' on a traceability_transport_transactions row (confirm-arrival).
        Must belong to the organization.
        """
        row = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.id == transaction_id,
                TransportTransaction.organization_id == organization_id,
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .first()
        )
        if not row:
            return {"success": False, "message": "Transport transaction not found or access denied", "transaction_id": transaction_id}
        now = datetime.now(timezone.utc)
        row.arrival_date = now
        row.status = "arrived"
        row.updated_date = now
        self.db.flush()
        return {
            "success": True,
            "message": "Arrival confirmed",
            "transaction_id": transaction_id,
            "arrival_date": row.arrival_date.isoformat(),
            "status": row.status,
        }

    def revert_transaction(
        self,
        transaction_id: int,
        organization_id: int,
    ) -> Dict[str, Any]:
        """
        Revert a transport transaction and its related tree.

        1. Soft-delete the selected TransportTransaction.
        2. Soft-delete all its children/descendants.
        3. Soft-delete all its siblings (same parent_id) and their descendants.
        4. If the selected transaction has a parent, set the parent status to 'idle'
           and clear its arrival evidence (arrival_date).
        """
        row = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.id == transaction_id,
                TransportTransaction.organization_id == organization_id,
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
            .first()
        )
        if not row:
            return {"success": False, "message": "Transport transaction not found or access denied", "transaction_id": transaction_id}

        now = datetime.now(timezone.utc)
        parent_id = row.parent_id
        deleted_ids = []

        # 1. Soft-delete descendants of the selected transaction
        self._soft_delete_descendants(row.id, now)

        # 2. Soft-delete siblings and their descendants
        if parent_id is not None:
            # Siblings share the same parent
            siblings = (
                self.db.query(TransportTransaction)
                .filter(
                    TransportTransaction.parent_id == parent_id,
                    TransportTransaction.id != transaction_id,
                    TransportTransaction.is_active == True,
                    TransportTransaction.deleted_date.is_(None),
                )
                .all()
            )
        else:
            # No parent: siblings are other root transactions in the same group
            siblings = (
                self.db.query(TransportTransaction)
                .filter(
                    TransportTransaction.transaction_group_id == row.transaction_group_id,
                    TransportTransaction.parent_id.is_(None),
                    TransportTransaction.id != transaction_id,
                    TransportTransaction.is_active == True,
                    TransportTransaction.deleted_date.is_(None),
                )
                .all()
            )
        for sibling in siblings:
            self._soft_delete_descendants(sibling.id, now)
            sibling.is_active = False
            sibling.deleted_date = now
            deleted_ids.append(sibling.id)

        # 3. Soft-delete the selected transaction itself
        row.is_active = False
        row.deleted_date = now
        deleted_ids.append(row.id)

        self.db.flush()

        # IMPORTANT: Recalculate absolute_percentage after revert changes sibling structure.
        # Any future code that reverts transport transactions must also trigger this recalculation.
        if row.transaction_group_id:
            self._recalculate_absolute_percentage(row.transaction_group_id)

        return {
            "success": True,
            "message": "Transaction reverted successfully",
            "transaction_id": transaction_id,
            "deleted_ids": deleted_ids,
        }

    def _record_to_dict(
        self,
        record: TransactionRecord,
        path_map: Dict[int, str],
        include_info: bool = False,
        include_arrival: bool = False,
        transport_txn: Any = None,
    ) -> Dict[str, Any]:
        """Convert a TransactionRecord to a dict with id, weight, material obj, origin obj, destination obj.
        When include_info=True, add transaction_id, vehicle_info, driver_info (from transport_txn if given).
        When include_arrival=True, add arrival_date (from transport_txn if given).
        path_map: location_id -> built path string from UserService._build_location_paths.
        transport_txn: when set, used for vehicle_info/driver_info/arrival_date instead of created_transaction.
        """
        origin = None
        if record.created_transaction and record.created_transaction.origin:
            origin = self._location_to_dict(
                record.created_transaction.origin,
                path=path_map.get(record.created_transaction.origin.id, "") if path_map else "",
            )
        destination = None
        if record.destination:
            destination = self._location_to_dict(
                record.destination,
                path=path_map.get(record.destination.id, "") if path_map else "",
            )
        material = self._material_to_dict(record.material) if record.material else None
        weight = float(record.origin_weight_kg) if record.origin_weight_kg else 0
        item: Dict[str, Any] = {
            "id": record.id,
            "weight": weight,
            "material": material,
            "origin": origin,
            "destination": destination,
        }
        txn = transport_txn if transport_txn is not None else (record.created_transaction if record.created_transaction else None)
        if txn:
            if include_info:
                item["transaction_id"] = txn.id
                item["vehicle_info"] = getattr(txn, "vehicle_info", None) or {}
                item["driver_info"] = getattr(txn, "driver_info", None) or {}
            if include_arrival and getattr(txn, "arrival_date", None):
                item["arrival_date"] = txn.arrival_date.isoformat()
        return item

    def _location_to_dict(self, loc: Any, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Convert a UserLocation to a dictionary. path is from UserService._build_location_paths."""
        if loc is None:
            return None
        return {
            "id": loc.id,
            "name_th": getattr(loc, "name_th", None),
            "name_en": getattr(loc, "name_en", None),
            "display_name": getattr(loc, "display_name", None),
            "path": path if path is not None else "",
        }

    def _material_to_dict(self, material: Any) -> Optional[Dict[str, Any]]:
        """Convert a Material to a dictionary."""
        if material is None:
            return None
        return {
            "id": material.id,
            "name_th": getattr(material, "name_th", None),
            "name_en": getattr(material, "name_en", None),
            "category_id": getattr(material, "category_id", None),
            "main_material_id": getattr(material, "main_material_id", None),
            "unit_name_th": getattr(material, "unit_name_th", None),
            "unit_name_en": getattr(material, "unit_name_en", None),
            "unit_weight": float(material.unit_weight) if getattr(material, "unit_weight", None) else 0,
        }

    def backfill_absolute_percentages(self, organization_id: int) -> int:
        """
        One-time backfill: recalculate absolute_percentage for all groups in an organization.
        Returns the number of groups processed.
        """
        groups = (
            self.db.query(TraceabilityTransactionGroup.id)
            .filter(
                TraceabilityTransactionGroup.organization_id == organization_id,
                TraceabilityTransactionGroup.is_active == True,
                TraceabilityTransactionGroup.deleted_date.is_(None),
            )
            .all()
        )
        count = 0
        for (gid,) in groups:
            self._recalculate_absolute_percentage(gid)
            count += 1
        self.db.flush()
        return count
