"""
Manual Transaction Audit Service - Human-driven transaction auditing
Handles manual approval/rejection of pending transactions by auditors
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from ....models.transactions.transactions import Transaction, TransactionStatus
from ....models.transactions.transaction_records import TransactionRecord
from ....models.transactions.transaction_audits import TransactionAudit
from ....models.cores.references import MainMaterial, Material
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

            # Get transaction with origin relationship loaded
            transaction = db.query(Transaction).options(
                joinedload(Transaction.origin)
            ).filter(Transaction.id == transaction_id).first()

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
                transaction_records = db.query(TransactionRecord, MainMaterial, Material).join(
                    MainMaterial, TransactionRecord.main_material_id == MainMaterial.id
                ).outerjoin(
                    Material, TransactionRecord.material_id == Material.id
                ).filter(
                    TransactionRecord.created_transaction_id == transaction.id
                ).all()

                records_data = []
                for record, main_material, material in transaction_records:
                    record_data = self._serialize_transaction_record(record, main_material, material)
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

            # Update transaction status to approved (allow re-auditing regardless of current status)
            transaction.status = TransactionStatus.approved
            transaction.approved_by_id = auditor_user_id
            transaction.updated_by_id = auditor_user_id
            transaction.updated_date = datetime.now(timezone.utc)
            transaction.is_user_audit = True  # Mark as manually audited by user
            transaction.audit_date = datetime.now(timezone.utc)  # Set audit date when manual audit is performed

            # Add audit notes
            audit_note = f"Manual Audit - APPROVED by User #{auditor_user_id} at {datetime.now(timezone.utc).isoformat()}"
            if notes:
                audit_note += f"\nAuditor Notes: {notes}"

            if transaction.notes:
                transaction.notes += f"\n\n{audit_note}"
            else:
                transaction.notes = audit_note

            # Create audit_notes in standard format
            audit_notes = {
                's': 'approved',  # status
                'v': []  # No violations for manual approval
            }

            # Save to BOTH places:
            # 1. Existing field (backward compatibility)
            transaction.ai_audit_notes = audit_notes

            # 2. New audit history table
            transaction_audit = TransactionAudit(
                transaction_id=transaction_id,
                audit_notes=audit_notes,
                by_human=True,  # Manual audit
                auditor_id=auditor_user_id,
                organization_id=transaction.organization_id,
                audit_type='manual',
                processing_time_ms=None,
                token_usage=None,
                model_version=None,
                created_date=int(datetime.now(timezone.utc).timestamp() * 1000),
                created_by_id=auditor_user_id
            )
            db.add(transaction_audit)

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

            # Update transaction status to rejected (allow re-auditing regardless of current status)
            transaction.status = TransactionStatus.rejected
            transaction.approved_by_id = auditor_user_id  # Track who made the decision
            transaction.updated_by_id = auditor_user_id
            transaction.updated_date = datetime.now(timezone.utc)
            transaction.is_user_audit = True  # Mark as manually audited by user
            transaction.audit_date = datetime.now(timezone.utc)  # Set audit date when manual audit is performed

            # Add rejection notes
            rejection_note = f"Manual Audit - REJECTED by User #{auditor_user_id} at {datetime.now(timezone.utc).isoformat()}"
            if rejection_reason:
                rejection_note += f"\nRejection Reason: {rejection_reason}"

            if transaction.notes:
                transaction.notes += f"\n\n{rejection_note}"
            else:
                transaction.notes = rejection_note

            # Create audit_notes in standard format
            audit_notes = {
                's': 'rejected',  # status
                'v': [  # violations
                    {
                        'id': None,  # No rule ID for manual rejection
                        'm': rejection_reason if rejection_reason else 'Manually rejected by auditor'
                    }
                ]
            }

            # Save to BOTH places:
            # 1. Existing field (backward compatibility)
            transaction.ai_audit_notes = audit_notes

            # 2. New audit history table
            transaction_audit = TransactionAudit(
                transaction_id=transaction_id,
                audit_notes=audit_notes,
                by_human=True,  # Manual audit
                auditor_id=auditor_user_id,
                organization_id=transaction.organization_id,
                audit_type='manual',
                processing_time_ms=None,
                token_usage=None,
                model_version=None,
                created_date=int(datetime.now(timezone.utc).timestamp() * 1000),
                created_by_id=auditor_user_id
            )
            db.add(transaction_audit)

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

    def approve_transaction_record(
        self,
        db: Session,
        record_id: int,
        auditor_user_id: int,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Manually approve a pending transaction record

        Args:
            db: Database session
            record_id: Transaction record ID to approve
            auditor_user_id: ID of the user performing the audit
            notes: Optional audit notes

        Returns:
            Dict containing operation result
        """
        try:
            logger.info(f"Approving transaction record {record_id} by user {auditor_user_id}")

            # Get transaction record
            record = db.query(TransactionRecord).filter(TransactionRecord.id == record_id).first()

            if not record:
                return {
                    'success': False,
                    'error': f'Transaction record {record_id} not found',
                    'data': None
                }

            # Update transaction record status to approved
            record.status = 'approved'
            # Note: approved_by_id expects user_location_id, not user_id
            # For now, we skip setting it as we only have user_id from the JWT token

            # Add audit notes to the record
            if notes:
                audit_note = f"Manual Audit - APPROVED by User #{auditor_user_id} at {datetime.now(timezone.utc).isoformat()}"
                audit_note += f"\nAuditor Notes: {notes}"
                if record.notes:
                    record.notes += f"\n\n{audit_note}"
                else:
                    record.notes = audit_note

            # Flush changes to the record
            db.flush()

            # Check if all records for this transaction are now approved
            # If so, update the parent transaction status
            transaction = db.query(Transaction).filter(
                Transaction.id == record.created_transaction_id
            ).first()

            transaction_status_updated = False
            if transaction:
                # Get all records for this transaction
                all_records = db.query(TransactionRecord).filter(
                    TransactionRecord.created_transaction_id == transaction.id
                ).all()

                # Check statuses
                all_approved = all(r.status == 'approved' for r in all_records)
                any_rejected = any(r.status == 'rejected' for r in all_records)

                if any_rejected:
                    # If any record is rejected, transaction is rejected
                    transaction.status = TransactionStatus.rejected
                    transaction.approved_by_id = auditor_user_id
                    transaction.updated_by_id = auditor_user_id
                    transaction.updated_date = datetime.now(timezone.utc)
                    transaction.is_user_audit = True
                    transaction.audit_date = datetime.now(timezone.utc)
                    transaction_status_updated = True
                    logger.info(f"Transaction {transaction.id} status updated to rejected (has rejected records)")
                elif all_approved:
                    # All records approved, update transaction status
                    transaction.status = TransactionStatus.approved
                    transaction.approved_by_id = auditor_user_id
                    transaction.updated_by_id = auditor_user_id
                    transaction.updated_date = datetime.now(timezone.utc)
                    transaction.is_user_audit = True
                    transaction.audit_date = datetime.now(timezone.utc)
                    transaction_status_updated = True
                    logger.info(f"Transaction {transaction.id} status updated to approved (all records approved)")

                db.flush()

            # Commit all changes
            db.commit()
            db.refresh(record)

            logger.info(f"Transaction record {record_id} approved successfully with status: {record.status}")

            transaction_id = transaction.id if transaction else record.created_transaction_id
            return {
                'success': True,
                'message': f'Transaction record {record_id} approved successfully',
                'data': {
                    'record_id': record_id,
                    'transaction_id': transaction_id,
                    'new_status': 'approved',
                    'approved_by': auditor_user_id,
                    'approved_at': datetime.now(timezone.utc).isoformat(),
                    'transaction_status_updated': transaction_status_updated,
                    'transaction_status': transaction.status.value if transaction and transaction_status_updated else None
                }
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error approving transaction record {record_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error approving transaction record {record_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def reject_transaction_record(
        self,
        db: Session,
        record_id: int,
        auditor_user_id: int,
        rejection_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Manually reject a pending transaction record

        Args:
            db: Database session
            record_id: Transaction record ID to reject
            auditor_user_id: ID of the user performing the audit
            rejection_reason: Optional reason for rejection

        Returns:
            Dict containing operation result
        """
        try:
            logger.info(f"Rejecting transaction record {record_id} by user {auditor_user_id}")

            # Get transaction record
            record = db.query(TransactionRecord).filter(TransactionRecord.id == record_id).first()

            if not record:
                return {
                    'success': False,
                    'error': f'Transaction record {record_id} not found',
                    'data': None
                }

            # Update transaction record status to rejected
            record.status = 'rejected'
            # Note: approved_by_id expects user_location_id, not user_id
            # For now, we skip setting it as we only have user_id from the JWT token

            # Add rejection notes to the record
            rejection_note = f"Manual Audit - REJECTED by User #{auditor_user_id} at {datetime.now(timezone.utc).isoformat()}"
            if rejection_reason:
                rejection_note += f"\nRejection Reason: {rejection_reason}"

            if record.notes:
                record.notes += f"\n\n{rejection_note}"
            else:
                record.notes = rejection_note

            # Flush changes to the record
            db.flush()

            # When a record is rejected, update the parent transaction status to rejected
            transaction = db.query(Transaction).filter(
                Transaction.id == record.created_transaction_id
            ).first()

            transaction_status_updated = False
            if transaction:
                # Any rejected record means the transaction is rejected
                transaction.status = TransactionStatus.rejected
                transaction.approved_by_id = auditor_user_id
                transaction.updated_by_id = auditor_user_id
                transaction.updated_date = datetime.now(timezone.utc)
                transaction.is_user_audit = True
                transaction.audit_date = datetime.now(timezone.utc)
                transaction_status_updated = True
                logger.info(f"Transaction {transaction.id} status updated to rejected")

                db.flush()

            # Commit all changes
            db.commit()
            db.refresh(record)

            logger.info(f"Transaction record {record_id} rejected successfully with status: {record.status}")

            transaction_id = transaction.id if transaction else record.created_transaction_id
            return {
                'success': True,
                'message': f'Transaction record {record_id} rejected successfully',
                'data': {
                    'record_id': record_id,
                    'transaction_id': transaction_id,
                    'new_status': 'rejected',
                    'rejected_by': auditor_user_id,
                    'rejected_at': datetime.now(timezone.utc).isoformat(),
                    'rejection_reason': rejection_reason,
                    'transaction_status_updated': transaction_status_updated,
                    'transaction_status': 'rejected' if transaction_status_updated else None
                }
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error rejecting transaction record {record_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'data': None
            }
        except Exception as e:
            logger.error(f"Unexpected error rejecting transaction record {record_id}: {str(e)}")
            db.rollback()
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'data': None
            }

    def bulk_approve_transactions(
        self,
        db: Session,
        transaction_ids: List[int],
        auditor_user_id: int,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Bulk approve multiple transactions

        Args:
            db: Database session
            transaction_ids: List of transaction IDs to approve
            auditor_user_id: ID of the user performing the audit
            notes: Optional audit notes (applied to all transactions)

        Returns:
            Dict containing operation results with successes and errors
        """
        results = []
        errors = []

        for transaction_id in transaction_ids:
            try:
                result = self.approve_transaction(
                    db=db,
                    transaction_id=transaction_id,
                    auditor_user_id=auditor_user_id,
                    notes=notes
                )
                if result['success']:
                    results.append({
                        'transaction_id': transaction_id,
                        'success': True,
                        'message': result['message'],
                        'data': result['data']
                    })
                else:
                    errors.append({
                        'transaction_id': transaction_id,
                        'error': result.get('error', 'Failed to approve transaction')
                    })
            except Exception as e:
                logger.error(f"Error approving transaction {transaction_id} in bulk operation: {str(e)}")
                errors.append({
                    'transaction_id': transaction_id,
                    'error': str(e)
                })

        return {
            'success': len(errors) == 0,
            'results': results,
            'errors': errors,
            'summary': {
                'total_requested': len(transaction_ids),
                'successful': len(results),
                'failed': len(errors)
            }
        }

    def bulk_reject_transactions(
        self,
        db: Session,
        transaction_ids: List[int],
        auditor_user_id: int,
        rejection_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Bulk reject multiple transactions

        Args:
            db: Database session
            transaction_ids: List of transaction IDs to reject
            auditor_user_id: ID of the user performing the audit
            rejection_reason: Optional rejection reason (applied to all transactions)

        Returns:
            Dict containing operation results with successes and errors
        """
        results = []
        errors = []

        for transaction_id in transaction_ids:
            try:
                result = self.reject_transaction(
                    db=db,
                    transaction_id=transaction_id,
                    auditor_user_id=auditor_user_id,
                    rejection_reason=rejection_reason
                )
                if result['success']:
                    results.append({
                        'transaction_id': transaction_id,
                        'success': True,
                        'message': result['message'],
                        'data': result['data']
                    })
                else:
                    errors.append({
                        'transaction_id': transaction_id,
                        'error': result.get('error', 'Failed to reject transaction')
                    })
            except Exception as e:
                logger.error(f"Error rejecting transaction {transaction_id} in bulk operation: {str(e)}")
                errors.append({
                    'transaction_id': transaction_id,
                    'error': str(e)
                })

        return {
            'success': len(errors) == 0,
            'results': results,
            'errors': errors,
            'summary': {
                'total_requested': len(transaction_ids),
                'successful': len(results),
                'failed': len(errors)
            }
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
            'origin_name': transaction.origin.display_name if transaction.origin else None,
            'origin_name_th': transaction.origin.name_th if transaction.origin else None,
            'origin_name_en': transaction.origin.name_en if transaction.origin else None,
            'destination_ids': transaction.destination_ids if hasattr(transaction, 'destination_ids') else [],
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
            'ai_audit_status': transaction.ai_audit_status.value if hasattr(transaction, 'ai_audit_status') and transaction.ai_audit_status else None,
            'ai_audit_note': transaction.ai_audit_note if hasattr(transaction, 'ai_audit_note') else None,
            'is_user_audit': transaction.is_user_audit if hasattr(transaction, 'is_user_audit') else False,
            'is_active': transaction.is_active,
            'created_date': transaction.created_date.isoformat() if transaction.created_date else None,
            'updated_date': transaction.updated_date.isoformat() if transaction.updated_date else None,
            'deleted_date': transaction.deleted_date.isoformat() if transaction.deleted_date else None
        }

    def _serialize_transaction_record(self, record: TransactionRecord, main_material: MainMaterial, material: Optional[Material] = None) -> Dict[str, Any]:
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
            'material_code': main_material.code,
            'material_unit_weight': float(material.unit_weight) if material and material.unit_weight else None
        }