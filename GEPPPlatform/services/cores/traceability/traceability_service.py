"""
Traceability Service
Business logic for traceability.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.users.user_location import UserLocation


class TraceabilityService:
    """
    Service for traceability operations.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_traceability(self, organization_id: Optional[int] = None, **kwargs: Any) -> List[List[Dict[str, Any]]]:
        """
        Get transaction records for the organization. Returns three arrays:
        - [0]: records without transport
        - [1]: transport records with vehicle_info, driver_info (no arrival_date yet)
        - [2]: transport records with arrival_date

        Query string filters: date_from, date_to (record transaction_date), material_id (comma-separated),
        origin_id (comma-separated, creating transaction's origin).
        """
        if organization_id is None:
            return [[], [], []]

        filters = [
            Transaction.organization_id == organization_id,
            TransactionRecord.is_active == True,
            TransactionRecord.deleted_date.is_(None),
            Transaction.status != TransactionStatus.rejected,
        ]

        # date_from / date_to: filter on record's transaction_date
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        if date_from:
            try:
                dt = datetime.fromisoformat(str(date_from).replace("Z", "+00:00"))
                if dt.tzinfo:
                    dt = dt.astimezone(timezone.utc)
                filters.append(TransactionRecord.transaction_date >= dt)
            except (ValueError, TypeError):
                pass
        if date_to:
            try:
                dt = datetime.fromisoformat(str(date_to).replace("Z", "+00:00"))
                if dt.tzinfo:
                    dt = dt.astimezone(timezone.utc)
                filters.append(TransactionRecord.transaction_date <= dt)
            except (ValueError, TypeError):
                pass

        # material_id: comma-separated, filter record.material_id
        material_id_param = kwargs.get("material_id")
        if material_id_param:
            try:
                material_ids = [int(x.strip()) for x in str(material_id_param).split(",") if x.strip()]
                if material_ids:
                    filters.append(TransactionRecord.material_id.in_(material_ids))
            except ValueError:
                pass

        # origin_id: format "origin|tag|tenant" (e.g. 4427|69|12) - filter creating transaction's origin_id, location_tag_id, tenant_id
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

        query = (
            self.db.query(TransactionRecord)
            .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
            .options(
                joinedload(TransactionRecord.material),
                joinedload(TransactionRecord.created_transaction).joinedload(Transaction.origin),
                joinedload(TransactionRecord.destination),
            )
            .filter(and_(*filters))
        )
        records = query.all()

        # Build location path map (same as transaction_handlers / user_service._build_location_paths)
        location_ids = set()
        for r in records:
            if r.created_transaction and getattr(r.created_transaction, "origin_id", None):
                location_ids.add(r.created_transaction.origin_id)
            if getattr(r, "destination_id", None):
                location_ids.add(r.destination_id)
        path_map: Dict[int, str] = {}
        if location_ids:
            from ..users.user_service import UserService
            user_service = UserService(self.db)
            location_data = [{"id": lid} for lid in location_ids]
            path_map = user_service._build_location_paths(organization_id, location_data) or {}

        # Load all transactions that appear as created_transaction or in traceability (so we can find transport txns)
        all_txn_ids = set()
        for r in records:
            if r.created_transaction_id:
                all_txn_ids.add(r.created_transaction_id)
            for tid in (r.traceability or []):
                all_txn_ids.add(tid)
        txn_map: Dict[int, Any] = {}
        if all_txn_ids:
            txns = self.db.query(Transaction).filter(Transaction.id.in_(all_txn_ids)).all()
            txn_map = {t.id: t for t in txns}
        transport_method = "transport"
        transport_txn_ids = {tid for tid, t in txn_map.items() if getattr(t, "transaction_method", None) == transport_method}

        # Records that have a transport: created by transport OR have a transport in traceability
        def get_display_transport_txn(record: TransactionRecord):
            if record.created_transaction_id and record.created_transaction_id in transport_txn_ids:
                return record.created_transaction
            candidate_ids = [tid for tid in (record.traceability or []) if tid in transport_txn_ids]
            if not candidate_ids:
                return None
            return txn_map.get(max(candidate_ids))

        records_from_transport = [
            r for r in records
            if r.created_transaction_id in transport_txn_ids
            or any(tid in transport_txn_ids for tid in (r.traceability or []))
        ]
        transport_record_ids = {r.id for r in records_from_transport}

        # data[0]: records without transport (exclude those in data[1]/data[2])
        records_without_transport = [r for r in records if r.id not in transport_record_ids]
        arr0 = [self._record_to_dict(r, path_map, include_info=False, include_arrival=False) for r in records_without_transport]
        # data[1]: transport records with vehicle_info, driver_info but no arrival_date yet (exclude if in data[2])
        arr1 = []
        arr2 = []
        for r in records_from_transport:
            transport_txn = get_display_transport_txn(r)
            if not transport_txn:
                continue
            has_arrival = getattr(transport_txn, "arrival_date", None) is not None
            if has_arrival:
                arr2.append(self._record_to_dict(r, path_map, include_info=True, include_arrival=True, transport_txn=transport_txn))
            else:
                arr1.append(self._record_to_dict(r, path_map, include_info=True, include_arrival=False, transport_txn=transport_txn))
        return [arr0, arr1, arr2]

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
    ) -> Dict[str, Any]:
        """
        Create a transport transaction for an existing record and link it.
        - Creates a Transaction with status=pending, transaction_method='transport',
          vehicle_info, driver_info (from messenger_info), transaction_records=[record_id],
          destination_ids=[destination_id], weight_kg, origin_id.
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

    def confirm_arrival(
        self,
        transaction_id: int,
        organization_id: int,
    ) -> Dict[str, Any]:
        """
        Set arrival_date on a transaction (for confirm-arrival). Transaction must belong to the organization.
        """
        transaction = (
            self.db.query(Transaction)
            .filter(
                Transaction.id == transaction_id,
                Transaction.organization_id == organization_id,
            )
            .first()
        )
        if not transaction:
            return {"success": False, "message": "Transaction not found or access denied", "transaction_id": transaction_id}
        transaction.arrival_date = datetime.now(timezone.utc)
        self.db.flush()
        return {
            "success": True,
            "message": "Arrival confirmed",
            "transaction_id": transaction_id,
            "arrival_date": transaction.arrival_date.isoformat(),
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
