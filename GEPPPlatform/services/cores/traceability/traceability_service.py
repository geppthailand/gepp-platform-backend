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

        # 2) Legacy backfill: ensure every record in org/month/year is in some group
        self._backfill_traceability_groups_for_month(organization_id, year, month, kwargs)

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

        # 6) Records in this month for summary
        records = self._records_for_org_month_year(organization_id, year, month, kwargs)
        path_map: Dict[int, str] = {}
        location_ids = set()
        for r in records:
            if r.created_transaction and getattr(r.created_transaction, "origin_id", None):
                location_ids.add(r.created_transaction.origin_id)
            if getattr(r, "destination_id", None):
                location_ids.add(r.destination_id)
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            path_map = user_service._build_location_paths(organization_id, [{"id": lid} for lid in location_ids]) or {}

        all_txn_ids = set()
        for r in records:
            if r.created_transaction_id:
                all_txn_ids.add(r.created_transaction_id)
            for tid in (r.traceability or []):
                all_txn_ids.add(tid)
        txn_map = {}
        if all_txn_ids:
            txns = self.db.query(Transaction).filter(Transaction.id.in_(all_txn_ids)).all()
            txn_map = {t.id: t for t in txns}
        transport_txn_ids = {tid for tid, t in txn_map.items() if getattr(t, "transaction_method", None) == "transport"}

        def get_display_transport_txn(record: TransactionRecord):
            if record.created_transaction_id and record.created_transaction_id in transport_txn_ids:
                return record.created_transaction
            candidate_ids = [tid for tid in (record.traceability or []) if tid in transport_txn_ids]
            if not candidate_ids:
                return None
            return txn_map.get(max(candidate_ids))

        total_waste_weight = sum(float(getattr(r, "origin_weight_kg", None) or 0) for r in records)
        total_disposal = 0.0
        total_treatment = 0.0
        for r in records:
            txn = get_display_transport_txn(r)
            if txn:
                if getattr(txn, "disposal_method", None):
                    total_disposal += float(getattr(r, "origin_weight_kg", None) or 0)
                if getattr(txn, "treatment_method", None):
                    total_treatment += float(getattr(r, "origin_weight_kg", None) or 0)
        total_managed_waste = total_disposal + total_treatment

        return {
            "data": [arr0, arr1, arr2],
            "summary": {
                "total_waste_weight": total_waste_weight,
                "total_disposal": total_disposal,
                "total_treatment": total_treatment,
                "total_managed_waste": total_managed_waste,
            },
        }

    def get_traceability_hierarchy(self, organization_id: Optional[int] = None, **kwargs: Any) -> Dict[str, Any]:
        """
        Get full hierarchy for the tree chart: transaction groups for the month, each with a tree of
        TransportTransactions (root = parent_id null, then children recursively to leaf).
        Same query params as get_traceability: date_from, date_to (1-month), material_id, origin_id.
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

        groups = self.db.query(TraceabilityTransactionGroup).filter(and_(*group_filters)).all()
        if not groups:
            return {"data": []}

        group_ids = [g.id for g in groups]
        all_transports = (
            self.db.query(TransportTransaction)
            .filter(
                TransportTransaction.transaction_group_id.in_(group_ids),
                TransportTransaction.organization_id == organization_id,
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            )
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
                "origin": origin,
                "destination": destination,
                "material": material,
                "children": [],
            }

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
            Transaction.status != TransactionStatus.rejected,
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
            record_ids = [r.id for r in group_records]
            key = (origin_id, material_id, location_tag_id, tenant_id, year, month)
            existing = key_to_existing_group.get(key)
            if existing and existing.id not in group_ids_already_processed:
                existing_record_ids = list(existing.transaction_record_id or [])
                for rid in record_ids:
                    if rid not in existing_record_ids:
                        existing_record_ids.append(rid)
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
                TransactionRecord.id.in_(record_ids)
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
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            out.append({
                "id": r.id,
                "transaction_group_id": r.transaction_group_id,
                "origin_id": r.origin_id,
                "destination_id": getattr(r, "destination_id", None),
                "material_id": r.material_id,
                "weight": float(r.weight) if r.weight is not None else None,
                "meta_data": r.meta_data or {},
                "organization_id": r.organization_id,
                "disposal_method": r.disposal_method,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "status": r.status,
                "is_root": r.is_root,
                "parent_id": r.parent_id,
                "created_date": r.created_date.isoformat() if r.created_date else None,
                "updated_date": r.updated_date.isoformat() if r.updated_date else None,
                "origin": origin,
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
            material = None
            if r.material_id and r.material_id in material_map:
                material = self._material_to_dict(material_map[r.material_id])
            out.append({
                "id": r.id,
                "transaction_group_id": r.transaction_group_id,
                "origin_id": r.origin_id,
                "destination_id": getattr(r, "destination_id", None),
                "material_id": r.material_id,
                "weight": float(r.weight) if r.weight is not None else None,
                "meta_data": r.meta_data or {},
                "organization_id": r.organization_id,
                "disposal_method": r.disposal_method,
                "arrival_date": r.arrival_date.isoformat() if r.arrival_date else None,
                "status": r.status,
                "is_root": r.is_root,
                "parent_id": r.parent_id,
                "created_date": r.created_date.isoformat() if r.created_date else None,
                "updated_date": r.updated_date.isoformat() if r.updated_date else None,
                "origin": origin,
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

        return {
            "success": True,
            "message": "Transport transactions created",
            "ids": created_ids,
        }

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
        self.db.flush()
        return {
            "success": True,
            "message": "Arrival confirmed",
            "transaction_id": transaction_id,
            "arrival_date": row.arrival_date.isoformat(),
            "status": row.status,
        }

    def go_back_one_step(
        self,
        transaction_id: int,
        organization_id: int,
    ) -> Dict[str, Any]:
        """
        Go back one step for a transport transaction. Same path, two cases:
        - If transaction has arrival_date: remove it (set to None).
        - If transaction does not have arrival_date: soft delete the transaction, and for each
          record in transaction_records remove this txn from traceability and set destination_id to None.
        """
        transaction = (
            self.db.query(Transaction)
            .filter(
                Transaction.id == transaction_id,
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None),
            )
            .first()
        )
        if not transaction:
            return {"success": False, "message": "Transaction not found or access denied", "transaction_id": transaction_id}
        if getattr(transaction, "transaction_method", None) != "transport":
            return {"success": False, "message": "Transaction is not a transport transaction", "transaction_id": transaction_id}

        has_arrival = getattr(transaction, "arrival_date", None) is not None
        if has_arrival:
            transaction.arrival_date = None
            self.db.flush()
            return {
                "success": True,
                "message": "Arrival date removed",
                "transaction_id": transaction_id,
                "action": "removed_arrival_date",
            }
        # No arrival_date: soft delete transaction and revert records
        transaction.deleted_date = datetime.now(timezone.utc)
        record_ids = list(transaction.transaction_records or [])
        for record_id in record_ids:
            record = (
                self.db.query(TransactionRecord)
                .filter(
                    TransactionRecord.id == record_id,
                    TransactionRecord.is_active == True,
                    TransactionRecord.deleted_date.is_(None),
                )
                .first()
            )
            if record:
                traceability = list(record.traceability or [])
                if transaction_id in traceability:
                    traceability.remove(transaction_id)
                    record.traceability = sorted(traceability) if traceability else []
                record.destination_id = None
        self.db.flush()
        return {
            "success": True,
            "message": "Transport transaction removed and record(s) reverted",
            "transaction_id": transaction_id,
            "action": "soft_deleted_transaction",
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
