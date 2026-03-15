"""
Debug Handlers - Development utilities for debugging and testing
WARNING: These endpoints should only be available in development environments
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import update

from ...models.transactions.transactions import Transaction, TransactionStatus
from ...database import get_session
from ...exceptions import APIException

logger = logging.getLogger(__name__)

def handle_debug_routes(event: Dict[str, Any], data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """
    Route handler for debug endpoints
    """
    try:
        path = event.get("rawPath", "")
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

        logger.info(f"Debug route: {method} {path}")

        # Get current user from commonParams
        current_user = kwargs.get('current_user', {})
        user_id = current_user.get('user_id')
        organization_id = current_user.get('organization_id')

        if not user_id or not organization_id:
            raise APIException(
                message="User authentication required",
                status_code=401,
                error_code="AUTHENTICATION_REQUIRED"
            )

        # Route to specific handlers
        if path == "/api/debug/transaction/reset_pending_all" and method == "POST":
            return reset_all_transactions_to_pending(user_id, organization_id, **kwargs)

        elif path == "/api/debug/traceability/backfill_percentages" and method == "POST":
            return backfill_traceability_percentages(organization_id, **kwargs)

        elif path == "/api/debug/traceability/backfill_group_ids" and method == "POST":
            return backfill_traceability_group_ids(organization_id, **kwargs)

        elif path.startswith("/api/debug/traceability/diagnose_group/") and method == "GET":
            group_id = int(path.split("/")[-1])
            return diagnose_traceability_group(group_id, **kwargs)

        else:
            raise APIException(
                message=f"Debug endpoint not found: {method} {path}",
                status_code=404,
                error_code="DEBUG_ENDPOINT_NOT_FOUND"
            )

    except APIException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in debug route handler: {str(e)}")
        raise APIException(
            message="Internal server error in debug handlers",
            status_code=500,
            error_code="DEBUG_HANDLER_ERROR"
        )

def reset_all_transactions_to_pending(user_id: int, organization_id: int, **kwargs) -> Dict[str, Any]:
    """
    DEBUG: Reset all transactions of current user's organization to pending status
    WARNING: This is a destructive operation that should only be used for testing
    """
    try:
        # Get database session - use the one passed in kwargs if available
        session = kwargs.get('session')

        if session:
            # Use existing session
            try:
                # Find all transactions for the organization that are NOT already pending
                transactions_to_reset = session.query(Transaction).filter(
                    Transaction.organization_id == organization_id,
                    Transaction.status != TransactionStatus.pending,
                    Transaction.is_active == True
                ).all()

                # Count of transactions that will be updated
                update_count = len(transactions_to_reset)

                if update_count == 0:
                    return {
                        "success": True,
                        "message": "No transactions to reset - all are already pending",
                        "data": {
                            "updated_count": 0,
                            "organization_id": organization_id,
                            "reset_by": user_id,
                            "reset_at": datetime.now(timezone.utc).isoformat()
                        }
                    }

                # Collect transaction IDs and old statuses
                updated_transactions = []
                transaction_ids = []
                for transaction in transactions_to_reset:
                    old_status = transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status)
                    transaction_ids.append(transaction.id)

                    updated_transactions.append({
                        "transaction_id": transaction.id,
                        "old_status": old_status,
                        "new_status": "pending"
                    })

                    logger.info(f"Reset transaction {transaction.id} from {old_status} to pending")

                # Use SQL UPDATE to reset all transactions at once
                # This ensures ai_audit_status is explicitly set to NULL
                session.execute(
                    update(Transaction)
                    .where(Transaction.id.in_(transaction_ids))
                    .values(
                        status=TransactionStatus.pending,
                        updated_date=datetime.now(timezone.utc),
                        notes=None,
                        ai_audit_status=None,
                        ai_audit_note=None
                    )
                )

                # Commit the changes
                session.commit()

                logger.info(f"DEBUG: Reset {update_count} transactions to pending for organization {organization_id} by user {user_id}")

                return {
                    "success": True,
                    "message": f"Successfully reset {update_count} transactions to pending status",
                    "data": {
                        "updated_count": update_count,
                        "organization_id": organization_id,
                        "reset_by": user_id,
                        "reset_at": datetime.now(timezone.utc).isoformat(),
                        "updated_transactions": updated_transactions
                    }
                }

            except Exception as e:
                session.rollback()
                raise e
        else:
            # Create new session using context manager
            with get_session() as session:
                # Find all transactions for the organization that are NOT already pending
                transactions_to_reset = session.query(Transaction).filter(
                    Transaction.organization_id == organization_id,
                    Transaction.status != TransactionStatus.pending,
                    Transaction.is_active == True
                ).all()

                # Count of transactions that will be updated
                update_count = len(transactions_to_reset)

                if update_count == 0:
                    return {
                        "success": True,
                        "message": "No transactions to reset - all are already pending",
                        "data": {
                            "updated_count": 0,
                            "organization_id": organization_id,
                            "reset_by": user_id,
                            "reset_at": datetime.now(timezone.utc).isoformat()
                        }
                    }

                # Collect transaction IDs and old statuses
                updated_transactions = []
                transaction_ids = []
                for transaction in transactions_to_reset:
                    old_status = transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status)
                    transaction_ids.append(transaction.id)

                    updated_transactions.append({
                        "transaction_id": transaction.id,
                        "old_status": old_status,
                        "new_status": "pending"
                    })

                    logger.info(f"Reset transaction {transaction.id} from {old_status} to pending")

                # Use SQL UPDATE to reset all transactions at once
                # This ensures ai_audit_status is explicitly set to NULL
                session.execute(
                    update(Transaction)
                    .where(Transaction.id.in_(transaction_ids))
                    .values(
                        status=TransactionStatus.pending,
                        updated_date=datetime.now(timezone.utc),
                        notes=None,
                        ai_audit_status=None,
                        ai_audit_note=None
                    )
                )

                # Commit the changes
                session.commit()

                logger.info(f"DEBUG: Reset {update_count} transactions to pending for organization {organization_id} by user {user_id}")

                return {
                    "success": True,
                    "message": f"Successfully reset {update_count} transactions to pending status",
                    "data": {
                        "updated_count": update_count,
                        "organization_id": organization_id,
                        "reset_by": user_id,
                        "reset_at": datetime.now(timezone.utc).isoformat(),
                        "updated_transactions": updated_transactions
                    }
                }

    except SQLAlchemyError as e:
        logger.error(f"Database error in reset_all_transactions_to_pending: {str(e)}")
        raise APIException(
            message="Database error while resetting transactions",
            status_code=500,
            error_code="DATABASE_ERROR"
        )
    except Exception as e:
        logger.error(f"Unexpected error in reset_all_transactions_to_pending: {str(e)}")
        raise APIException(
            message="Failed to reset transactions",
            status_code=500,
            error_code="RESET_TRANSACTIONS_ERROR"
        )


def backfill_traceability_percentages(organization_id: int, **kwargs) -> Dict[str, Any]:
    """
    DEBUG: Backfill absolute_percentage for all traceability transport transactions in the organization.
    """
    try:
        session = kwargs.get('session')
        if not session:
            raise APIException(message="No database session", status_code=500, error_code="NO_SESSION")

        from ..cores.traceability.traceability_service import TraceabilityService
        service = TraceabilityService(session)
        count = service.backfill_absolute_percentages(organization_id)
        session.commit()

        return {
            "success": True,
            "message": f"Backfilled absolute_percentage for {count} groups",
            "data": {"groups_processed": count, "organization_id": organization_id},
        }
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error in backfill_traceability_percentages: {str(e)}")
        raise APIException(
            message="Failed to backfill traceability percentages",
            status_code=500,
            error_code="BACKFILL_PERCENTAGES_ERROR",
        )


def backfill_traceability_group_ids(organization_id: int, **kwargs) -> Dict[str, Any]:
    """
    DEBUG: Merge duplicate traceability groups and set traceability_group_id on records.

    For each unique key (origin_id, material_id, location_tag_id, tenant_id, year, month):
    - If multiple groups exist, keep the one WITH transport transactions
    - Merge all record IDs into the surviving group
    - Soft-delete duplicate groups
    - Set traceability_group_id on all records pointing to the surviving group
    """
    try:
        session = kwargs.get('session')
        if not session:
            raise APIException(message="No database session", status_code=500, error_code="NO_SESSION")

        from ...models.transactions.traceability_transaction_group import TraceabilityTransactionGroup
        from ...models.transactions.transaction_records import TransactionRecord
        from ...models.transactions.transport_transaction import TransportTransaction
        from collections import defaultdict

        groups = session.query(TraceabilityTransactionGroup).filter(
            TraceabilityTransactionGroup.organization_id == organization_id,
            TraceabilityTransactionGroup.is_active == True,
            TraceabilityTransactionGroup.deleted_date.is_(None),
        ).all()

        # Find which groups have transport transactions
        group_ids_all = [g.id for g in groups]
        groups_with_transport = set()
        if group_ids_all:
            tt_rows = session.query(TransportTransaction.transaction_group_id).filter(
                TransportTransaction.transaction_group_id.in_(group_ids_all),
                TransportTransaction.is_active == True,
                TransportTransaction.deleted_date.is_(None),
            ).distinct().all()
            groups_with_transport = {r[0] for r in tt_rows if r[0] is not None}

        print(f"[BACKFILL] Total groups: {len(groups)}, groups with transport: {groups_with_transport}")

        # Group by key
        key_to_groups = defaultdict(list)
        for g in groups:
            key = (g.origin_id, g.material_id, g.location_tag_id, g.tenant_id,
                   g.transaction_year, g.transaction_month)
            key_to_groups[key].append(g)

        records_updated = 0
        groups_merged = 0
        groups_deleted = 0

        for key, group_list in key_to_groups.items():
            # Pick survivor: prefer group WITH transport, otherwise first
            survivor = None
            for g in group_list:
                if g.id in groups_with_transport:
                    survivor = g
                    break
            if survivor is None:
                survivor = group_list[0]

            # Merge all record IDs into survivor
            all_record_ids = set()
            for g in group_list:
                for rid in (g.transaction_record_id or []):
                    all_record_ids.add(rid)
            # Also merge carried_over
            all_carried_over = set()
            for g in group_list:
                for rid in (g.transaction_carried_over or []):
                    all_carried_over.add(rid)

            survivor.transaction_record_id = list(all_record_ids)
            survivor.transaction_carried_over = list(all_carried_over)
            survivor.updated_date = datetime.now(timezone.utc)

            # Soft-delete duplicates
            for g in group_list:
                if g.id != survivor.id:
                    g.is_active = False
                    g.deleted_date = datetime.now(timezone.utc)
                    groups_deleted += 1
                    print(f"[BACKFILL] Soft-deleted duplicate group {g.id} (key={key}), survivor={survivor.id}")

            if len(group_list) > 1:
                groups_merged += 1
                print(f"[BACKFILL] Merged {len(group_list)} groups into {survivor.id} (key={key}), {len(all_record_ids)} records")

            # Set traceability_group_id on all records
            if all_record_ids:
                updated = session.query(TransactionRecord).filter(
                    TransactionRecord.id.in_(list(all_record_ids))
                ).update(
                    {TransactionRecord.traceability_group_id: survivor.id},
                    synchronize_session=False
                )
                records_updated += updated or 0

        session.commit()

        return {
            "success": True,
            "message": f"Backfilled {records_updated} records, merged {groups_merged} duplicate groups, deleted {groups_deleted} duplicates",
            "data": {
                "records_updated": records_updated,
                "groups_processed": len(groups),
                "groups_merged": groups_merged,
                "groups_deleted": groups_deleted,
                "organization_id": organization_id,
            },
        }
    except APIException:
        raise
    except Exception as e:
        print(f"Error in backfill_traceability_group_ids: {str(e)}")
        raise APIException(
            message=f"Failed to backfill: {str(e)}",
            status_code=500,
            error_code="BACKFILL_GROUP_IDS_ERROR",
        )


def diagnose_traceability_group(group_id: int, **kwargs) -> Dict[str, Any]:
    """DEBUG: Diagnose recycling rate calculation for a specific traceability group."""
    try:
        session = kwargs.get('session')
        if not session:
            raise APIException(message="No database session", status_code=500, error_code="NO_SESSION")

        from ...models.transactions.traceability_transaction_group import TraceabilityTransactionGroup
        from ...models.transactions.transaction_records import TransactionRecord
        from ...models.transactions.transport_transaction import TransportTransaction

        # 1. Get the group
        group = session.query(TraceabilityTransactionGroup).filter(
            TraceabilityTransactionGroup.id == group_id
        ).first()
        if not group:
            return {"success": False, "message": f"Group {group_id} not found"}

        group_info = {
            "id": group.id,
            "origin_id": group.origin_id,
            "material_id": group.material_id,
            "is_active": group.is_active,
            "deleted_date": str(group.deleted_date) if group.deleted_date else None,
            "transaction_record_id": group.transaction_record_id,
            "transaction_carried_over": group.transaction_carried_over,
        }

        # 2. Check records pointing to this group via traceability_group_id
        records_with_group_id = session.query(
            TransactionRecord.id,
            TransactionRecord.traceability_group_id,
            TransactionRecord.status,
            TransactionRecord.origin_weight_kg,
            TransactionRecord.material_id,
            TransactionRecord.category_id,
        ).filter(
            TransactionRecord.traceability_group_id == group_id,
        ).all()

        records_in_array = session.query(
            TransactionRecord.id,
            TransactionRecord.traceability_group_id,
            TransactionRecord.status,
            TransactionRecord.origin_weight_kg,
        ).filter(
            TransactionRecord.id.in_(group.transaction_record_id or []),
        ).all()

        # 3. Get transport transactions for this group
        transports = session.query(
            TransportTransaction.id,
            TransportTransaction.transaction_group_id,
            TransportTransaction.status,
            TransportTransaction.disposal_method,
            TransportTransaction.absolute_percentage,
            TransportTransaction.is_root,
            TransportTransaction.parent_id,
            TransportTransaction.is_active,
        ).filter(
            TransportTransaction.transaction_group_id == group_id,
            TransportTransaction.is_active == True,
            TransportTransaction.deleted_date.is_(None),
        ).all()

        # 4. Build leaf analysis (same logic as fetch_group_leaf_data)
        has_children = set()
        all_nodes = []
        for tid, gid, status, method, abs_pct, is_root, parent_id, is_active in transports:
            all_nodes.append({
                "id": tid, "status": status, "disposal_method": method,
                "absolute_percentage": float(abs_pct or 0), "is_root": is_root, "parent_id": parent_id,
            })
            if parent_id is not None:
                has_children.add(parent_id)

        leaves = [n for n in all_nodes if n["id"] not in has_children and not n["is_root"]]
        total_leaf_pct = sum(n["absolute_percentage"] for n in leaves)
        completed_pct = sum(
            n["absolute_percentage"] for n in leaves
            if n["status"] == "arrived" and n["disposal_method"]
        )
        completion = (completed_pct / total_leaf_pct) if total_leaf_pct > 0 else 0.0

        from ..cores.reports.recycling_rate_helper import DIVERTED_METHODS
        diverted_pct = sum(
            n["absolute_percentage"] for n in leaves
            if n["status"] == "arrived" and (n["disposal_method"] or "").strip() in DIVERTED_METHODS
        )

        return {
            "success": True,
            "group": group_info,
            "records_with_traceability_group_id": [
                {"id": r[0], "traceability_group_id": r[1], "status": r[2],
                 "weight_kg": float(r[3] or 0), "material_id": r[4], "category_id": r[5]}
                for r in records_with_group_id
            ],
            "records_in_group_array": [
                {"id": r[0], "traceability_group_id": r[1], "status": r[2], "weight_kg": float(r[3] or 0)}
                for r in records_in_array
            ],
            "transport_transactions": all_nodes,
            "leaf_analysis": {
                "total_nodes": len(all_nodes),
                "leaf_count": len(leaves),
                "leaves": leaves,
                "total_leaf_pct": total_leaf_pct,
                "completed_pct": completed_pct,
                "completion_rate": completion,
                "diverted_pct": diverted_pct,
                "diverted_methods_matched": DIVERTED_METHODS,
            },
            "diagnosis": {
                "records_have_traceability_group_id": len(records_with_group_id) > 0,
                "group_has_transport": len(all_nodes) > 0,
                "has_leaves": len(leaves) > 0,
                "is_fully_traced": completion == 1.0,
                "recycling_pct_from_traceability": diverted_pct,
            },
        }
    except APIException:
        raise
    except Exception as e:
        print(f"Error in diagnose_traceability_group: {str(e)}")
        raise APIException(message=f"Diagnosis failed: {str(e)}", status_code=500, error_code="DIAGNOSE_ERROR")