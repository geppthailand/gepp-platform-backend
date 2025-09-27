"""
Manual Transaction Audit Service - Human-driven transaction auditing
Handles manual approval/rejection of pending transactions by auditors
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.cores.references import MainMaterial
from ....models.users.user_location import UserLocation
from ....models.subscriptions.organizations import Organization

logger = logging.getLogger(__name__)

class ManualAuditService:
    """
    Service for manual transaction auditing operations
    Handles approval/rejection workflows for pending transactions
    """

    def __init__(self):
        """
        Initialize the ManualAuditService
        """
        logger.info("ManualAuditService initialized")

    def get_pending_transactions(
        self,
        db: Session,
        organization_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Get pending transactions for manual audit

        Args:
            db: Database session
            organization_id: Optional organization ID for filtering
            page: Page number for pagination
            page_size: Number of items per page

        Returns:
            Dict containing pending transactions and pagination info
        """
        try:
            logger.info(f"Fetching pending transactions for organization: {organization_id}")

            # Base query for pending transactions
            query = db.query(Transaction).filter(Transaction.status == TransactionStatus.pending)

            if organization_id:
                query = query.filter(Transaction.organization_id == organization_id)

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            transactions = query.offset(offset).limit(page_size).all()

            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size
            has_next = page < total_pages
            has_prev = page > 1

            logger.info(f"Found {total_count} pending transactions, returning page {page} of {total_pages}")

            return {
                'success': True,
                'message': f'Found {total_count} pending transactions',
                'data': {
                    'transactions': self._serialize_transactions(transactions),
                    'pagination': {
                        'page': page,
                        'page_size': page_size,
                        'total': total_count,
                        'pages': total_pages,
                        'has_next': has_next,
                        'has_prev': has_prev
                    }
                }
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error fetching pending transactions: {str(e)}")
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error fetching pending transactions: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def get_transaction_details(
        self,
        db: Session,
        transaction_id: int,
        include_records: bool = True
    ) -> Dict[str, Any]:
        """
        Get detailed information for a specific transaction including records

        Args:
            db: Database session
            transaction_id: Transaction ID
            include_records: Whether to include transaction records

        Returns:
            Dict containing transaction details
        """
        try:
            logger.info(f"Fetching transaction details for ID: {transaction_id}")

            # Get transaction
            transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

            if not transaction:
                return {
                    'success': False,
                    'error': f'Transaction {transaction_id} not found',
                    'data': None
                }

            # Serialize transaction
            transaction_data = self._serialize_transaction(transaction)

            # Include records if requested
            if include_records:
                transaction_records = db.query(TransactionRecord, MainMaterial).join(
                    MainMaterial, TransactionRecord.main_material_id == MainMaterial.id
                ).filter(
                    TransactionRecord.created_transaction_id == transaction.id
                ).all()

                records_data = []
                for record, main_material in transaction_records:
                    record_data = self._serialize_transaction_record(record, main_material)
                    records_data.append(record_data)

                transaction_data['records'] = records_data

            logger.info(f"Successfully fetched transaction {transaction_id} with {len(records_data) if include_records else 0} records")

            return {
                'success': True,
                'message': f'Transaction {transaction_id} retrieved successfully',
                'data': transaction_data
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error fetching transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error fetching transaction {transaction_id}: {str(e)}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def approve_transaction(
        self,
        db: Session,
        transaction_id: int,
        auditor_user_id: int,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Manually approve a pending transaction

        Args:
            db: Database session
            transaction_id: Transaction ID to approve
            auditor_user_id: ID of the user performing the audit
            notes: Optional audit notes

        Returns:
            Dict containing operation result
        """
        try:
            logger.info(f"Approving transaction {transaction_id} by user {auditor_user_id}")

            # Get transaction
            transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

            if not transaction:
                return {
                    'success': False,
                    'error': f'Transaction {transaction_id} not found',
                    'data': None
                }

            # Check if transaction is in pending status
            if transaction.status != TransactionStatus.pending:
                return {
                    'success': False,
                    'error': f'Transaction {transaction_id} is not pending (current status: {transaction.status.value})',
                    'data': None
                }

            # Update transaction status to approved
            transaction.status = TransactionStatus.approved
            transaction.approved_by_id = auditor_user_id
            transaction.updated_by_id = auditor_user_id
            transaction.updated_date = datetime.now(timezone.utc)

            # Add audit notes
            audit_note = f"Manual Audit - APPROVED by User #{auditor_user_id} at {datetime.now(timezone.utc).isoformat()}"
            if notes:
                audit_note += f"\nAuditor Notes: {notes}"

            if transaction.notes:
                transaction.notes += f"\n\n{audit_note}"
            else:
                transaction.notes = audit_note

            # Commit changes
            db.commit()

            logger.info(f"Transaction {transaction_id} approved successfully")

            return {
                'success': True,
                'message': f'Transaction {transaction_id} approved successfully',
                'data': {
                    'transaction_id': transaction_id,
                    'new_status': TransactionStatus.approved.value,
                    'approved_by': auditor_user_id,
                    'approved_at': datetime.now(timezone.utc).isoformat()
                }
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error approving transaction {transaction_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error approving transaction {transaction_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def reject_transaction(
        self,
        db: Session,
        transaction_id: int,
        auditor_user_id: int,
        rejection_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Manually reject a pending transaction

        Args:
            db: Database session
            transaction_id: Transaction ID to reject
            auditor_user_id: ID of the user performing the audit
            rejection_reason: Optional reason for rejection

        Returns:
            Dict containing operation result
        """
        try:
            logger.info(f"Rejecting transaction {transaction_id} by user {auditor_user_id}")

            # Get transaction
            transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()

            if not transaction:
                return {
                    'success': False,
                    'error': f'Transaction {transaction_id} not found',
                    'data': None
                }

            # Check if transaction is in pending status
            if transaction.status != TransactionStatus.pending:
                return {
                    'success': False,
                    'error': f'Transaction {transaction_id} is not pending (current status: {transaction.status.value})',
                    'data': None
                }

            # Update transaction status to rejected
            transaction.status = TransactionStatus.rejected
            transaction.approved_by_id = auditor_user_id  # Track who made the decision
            transaction.updated_by_id = auditor_user_id
            transaction.updated_date = datetime.now(timezone.utc)

            # Add rejection notes
            rejection_note = f"Manual Audit - REJECTED by User #{auditor_user_id} at {datetime.now(timezone.utc).isoformat()}"
            if rejection_reason:
                rejection_note += f"\nRejection Reason: {rejection_reason}"

            if transaction.notes:
                transaction.notes += f"\n\n{rejection_note}"
            else:
                transaction.notes = rejection_note

            # Commit changes
            db.commit()

            logger.info(f"Transaction {transaction_id} rejected successfully")

            return {
                'success': True,
                'message': f'Transaction {transaction_id} rejected successfully',
                'data': {
                    'transaction_id': transaction_id,
                    'new_status': TransactionStatus.rejected.value,
                    'rejected_by': auditor_user_id,
                    'rejected_at': datetime.now(timezone.utc).isoformat(),
                    'rejection_reason': rejection_reason
                }
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error rejecting transaction {transaction_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error rejecting transaction {transaction_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def _serialize_transactions(self, transactions: List[Transaction]) -> List[Dict[str, Any]]:
        """Serialize a list of transactions to dictionaries"""
        return [self._serialize_transaction(transaction) for transaction in transactions]

    def _serialize_transaction(self, transaction: Transaction) -> Dict[str, Any]:
        """Serialize a transaction to dictionary"""
        return {
            'id': transaction.id,
            'transaction_records': transaction.transaction_records or [],
            'transaction_method': transaction.transaction_method,
            'status': transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status),
            'organization_id': transaction.organization_id,
            'origin_id': transaction.origin_id,
            'destination_id': transaction.destination_id,
            'weight_kg': float(transaction.weight_kg) if transaction.weight_kg else 0.0,
            'total_amount': float(transaction.total_amount) if transaction.total_amount else 0.0,
            'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
            'arrival_date': transaction.arrival_date.isoformat() if transaction.arrival_date else None,
            'origin_coordinates': transaction.origin_coordinates,
            'destination_coordinates': transaction.destination_coordinates,
            'notes': transaction.notes,
            'images': transaction.images or [],
            'vehicle_info': transaction.vehicle_info,
            'driver_info': transaction.driver_info,
            'hazardous_level': transaction.hazardous_level,
            'treatment_method': transaction.treatment_method,
            'disposal_method': transaction.disposal_method,
            'created_by_id': transaction.created_by_id,
            'updated_by_id': transaction.updated_by_id,
            'approved_by_id': transaction.approved_by_id,
            'is_active': transaction.is_active,
            'created_date': transaction.created_date.isoformat() if transaction.created_date else None,
            'updated_date': transaction.updated_date.isoformat() if transaction.updated_date else None,
            'deleted_date': transaction.deleted_date.isoformat() if transaction.deleted_date else None
        }

    def _serialize_transaction_record(self, record: TransactionRecord, main_material: MainMaterial) -> Dict[str, Any]:
        """Serialize a transaction record with material information to dictionary"""
        return {
            'id': record.id,
            'status': record.status,
            'created_transaction_id': record.created_transaction_id,
            'traceability': record.traceability or [],
            'transaction_type': record.transaction_type,
            'material_id': record.material_id,
            'main_material_id': record.main_material_id,
            'category_id': record.category_id,
            'tags': record.tags or [],
            'unit': record.unit,
            'origin_quantity': float(record.origin_quantity) if record.origin_quantity else 0.0,
            'origin_weight_kg': float(record.origin_weight_kg) if record.origin_weight_kg else 0.0,
            'origin_price_per_unit': float(record.origin_price_per_unit) if record.origin_price_per_unit else 0.0,
            'total_amount': float(record.total_amount) if record.total_amount else 0.0,
            'currency_id': record.currency_id,
            'notes': record.notes,
            'images': record.images or [],
            'origin_coordinates': record.origin_coordinates,
            'destination_coordinates': record.destination_coordinates,
            'hazardous_level': record.hazardous_level,
            'treatment_method': record.treatment_method,
            'disposal_method': record.disposal_method,
            'created_by_id': record.created_by_id,
            'approved_by_id': record.approved_by_id,
            'completed_date': record.completed_date.isoformat() if record.completed_date else None,
            'is_active': record.is_active,
            'created_date': record.created_date.isoformat() if record.created_date else None,
            'updated_date': record.updated_date.isoformat() if record.updated_date else None,
            'deleted_date': record.deleted_date.isoformat() if record.deleted_date else None,
            # Material information from join
            'material_name_en': main_material.name_en,
            'material_name_th': main_material.name_th,
            'material_code': main_material.code
        }