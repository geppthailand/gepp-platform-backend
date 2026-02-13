"""
Manual Audit API handlers for human-driven audit operations
"""

from typing import Dict, Any
import logging
import traceback

from .manual_audit_service import ManualAuditService
from ..transactions.transaction_service import TransactionService

logger = logging.getLogger(__name__)
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_manual_audit_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for manual audit routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})

    # Get database session from commonParams
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    manual_audit_service = ManualAuditService()

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_organization_id = current_user.get('organization_id')

    try:
        # Route to specific handlers
        if path == '/api/audit/manual/pending' and method == 'GET':
            return handle_get_pending_transactions(
                manual_audit_service,
                db_session,
                query_params,
                current_user_organization_id,
                current_user_id
            )

        elif path.startswith('/api/audit/manual/transaction/') and path.endswith('/details') and method == 'GET':
            # Extract transaction ID from path: /api/audit/manual/transaction/{id}/details
            path_parts = path.split('/')
            try:
                transaction_id = int(path_parts[5])  # /api/audit/manual/transaction/{id}/details
            except (IndexError, ValueError):
                raise BadRequestException('Invalid transaction ID in path')

            return handle_get_transaction_details(
                manual_audit_service,
                db_session,
                transaction_id,
                query_params,
                current_user_organization_id,
                current_user_id
            )

        elif path.startswith('/api/audit/manual/transaction/') and path.endswith('/approve') and method == 'POST':
            # Extract transaction ID from path: /api/audit/manual/transaction/{id}/approve
            path_parts = path.split('/')
            try:
                transaction_id = int(path_parts[5])  # /api/audit/manual/transaction/{id}/approve
            except (IndexError, ValueError):
                raise BadRequestException('Invalid transaction ID in path')

            return handle_approve_transaction(
                manual_audit_service,
                db_session,
                transaction_id,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path.startswith('/api/audit/manual/transaction/') and path.endswith('/reject') and method == 'POST':
            # Extract transaction ID from path: /api/audit/manual/transaction/{id}/reject
            path_parts = path.split('/')
            try:
                transaction_id = int(path_parts[5])  # /api/audit/manual/transaction/{id}/reject
            except (IndexError, ValueError):
                raise BadRequestException('Invalid transaction ID in path')

            return handle_reject_transaction(
                manual_audit_service,
                db_session,
                transaction_id,
                data,
                current_user_organization_id,
                current_user_id
            )

        # Transaction Record-level audit routes
        elif path.startswith('/api/audit/manual/record/') and path.endswith('/approve') and method == 'POST':
            # Extract record ID from path: /api/audit/manual/record/{id}/approve
            path_parts = path.split('/')
            try:
                record_id = int(path_parts[5])  # /api/audit/manual/record/{id}/approve
            except (IndexError, ValueError):
                raise BadRequestException('Invalid record ID in path')

            return handle_approve_transaction_record(
                manual_audit_service,
                db_session,
                record_id,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path.startswith('/api/audit/manual/record/') and path.endswith('/reject') and method == 'POST':
            # Extract record ID from path: /api/audit/manual/record/{id}/reject
            path_parts = path.split('/')
            try:
                record_id = int(path_parts[5])  # /api/audit/manual/record/{id}/reject
            except (IndexError, ValueError):
                raise BadRequestException('Invalid record ID in path')

            return handle_reject_transaction_record(
                manual_audit_service,
                db_session,
                record_id,
                data,
                current_user_organization_id,
                current_user_id
            )

        # Bulk transaction audit routes
        elif path == '/api/audit/manual/transactions/bulk/approve' and method == 'POST':
            return handle_bulk_approve_transactions(
                manual_audit_service,
                db_session,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path == '/api/audit/manual/transactions/bulk/reject' and method == 'POST':
            return handle_bulk_reject_transactions(
                manual_audit_service,
                db_session,
                data,
                current_user_organization_id,
                current_user_id
            )

        else:
            # Route not found
            raise NotFoundException(f'Manual audit route not found: {method} {path}')

    except APIException:
        # Re-raise API exceptions as-is
        raise
    except ValidationException:
        # Re-raise validation exceptions as-is
        raise
    except Exception as e:
        # Log unexpected errors and return generic API error
        logger.error(f'Unexpected error in manual audit handler: {str(e)}')
        logger.error(f'Traceback: {traceback.format_exc()}')
        raise APIException(f'Internal server error: {str(e)}')


def handle_get_pending_transactions(
    service: ManualAuditService,
    db_session: Any,
    query_params: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/audit/manual/pending - Get pending transactions for manual audit

    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    - organization_id: Override organization (for multi-org users)
    """
    try:
        logger.info(f"Fetching pending transactions for user {current_user_id}")

        # Parse query parameters
        page = int(query_params.get('page', 1))
        page_size = min(int(query_params.get('page_size', 50)), 100)  # Cap at 100
        request_org_id = query_params.get('organization_id', organization_id)

        # Convert organization_id to int if it's a string
        if isinstance(request_org_id, str):
            try:
                request_org_id = int(request_org_id)
            except ValueError:
                request_org_id = organization_id

        # Authorization check - ensure user can view transactions for the requested organization
        if request_org_id != organization_id and organization_id is not None:
            raise UnauthorizedException('You can only view transactions for your own organization')

        # Get pending transactions
        result = service.get_pending_transactions(
            db=db_session,
            organization_id=request_org_id,
            page=page,
            page_size=page_size
        )

        if not result['success']:
            return {
                'success': False,
                'message': result.get('error', 'Failed to fetch pending transactions'),
                'error': result.get('error'),
                'data': None
            }

        return {
            'success': True,
            'message': result['message'],
            'data': result['data']
        }

    except ValidationException as e:
        logger.warning(f"Validation error fetching pending transactions: {str(e)}")
        return {
            'success': False,
            'message': 'Validation error',
            'error': str(e),
            'data': None
        }

    except UnauthorizedException as e:
        logger.warning(f"Authorization error fetching pending transactions: {str(e)}")
        raise  # Re-raise authorization errors

    except Exception as e:
        logger.error(f"Error fetching pending transactions: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': 'Failed to fetch pending transactions',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def handle_get_transaction_details(
    service: ManualAuditService,
    db_session: Any,
    transaction_id: int,
    query_params: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/audit/manual/transaction/{id}/details - Get transaction details for audit

    Query parameters:
    - include_records: Whether to include transaction records (default: true)
    """
    try:
        logger.info(f"Fetching transaction {transaction_id} details for user {current_user_id}")

        # Parse query parameters
        include_records = query_params.get('include_records', 'true').lower() == 'true'

        # Get transaction details
        result = service.get_transaction_details(
            db=db_session,
            transaction_id=transaction_id,
            include_records=include_records
        )

        if not result['success']:
            if 'not found' in result.get('error', '').lower():
                raise NotFoundException(f'Transaction {transaction_id} not found')

            return {
                'success': False,
                'message': result.get('error', 'Failed to fetch transaction details'),
                'error': result.get('error'),
                'data': None
            }

        # Authorization check - ensure transaction belongs to user's organization
        transaction_data = result['data']
        if transaction_data['organization_id'] != organization_id and organization_id is not None:
            raise UnauthorizedException('You can only view transactions for your own organization')

        return {
            'success': True,
            'message': result['message'],
            'data': result['data']
        }

    except NotFoundException:
        raise  # Re-raise not found errors

    except UnauthorizedException:
        raise  # Re-raise authorization errors

    except Exception as e:
        logger.error(f"Error fetching transaction {transaction_id} details: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': f'Failed to fetch transaction {transaction_id} details',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def handle_approve_transaction(
    service: ManualAuditService,
    db_session: Any,
    transaction_id: int,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/audit/manual/transaction/{id}/approve - Approve a pending transaction

    Expected payload:
    {
        "notes": "Optional audit notes"
    }
    """
    try:
        logger.info(f"Approving transaction {transaction_id} by user {current_user_id}")

        # Parse request data
        notes = data.get('notes')

        # Approve transaction
        result = service.approve_transaction(
            db=db_session,
            transaction_id=transaction_id,
            auditor_user_id=current_user_id,
            notes=notes
        )

        if not result['success']:
            if 'not found' in result.get('error', '').lower():
                raise NotFoundException(f'Transaction {transaction_id} not found')
            elif 'not pending' in result.get('error', '').lower():
                raise BadRequestException(result.get('error', 'Transaction is not in pending status'))

            return {
                'success': False,
                'message': result.get('error', 'Failed to approve transaction'),
                'error': result.get('error'),
                'data': None
            }

        return {
            'success': True,
            'message': result['message'],
            'data': result['data']
        }

    except NotFoundException:
        raise  # Re-raise not found errors

    except BadRequestException:
        raise  # Re-raise bad request errors

    except Exception as e:
        logger.error(f"Error approving transaction {transaction_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': f'Failed to approve transaction {transaction_id}',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def handle_reject_transaction(
    service: ManualAuditService,
    db_session: Any,
    transaction_id: int,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/audit/manual/transaction/{id}/reject - Reject a pending transaction

    Expected payload:
    {
        "rejection_reason": "Optional reason for rejection"
    }
    """
    try:
        logger.info(f"Rejecting transaction {transaction_id} by user {current_user_id}")

        # Parse request data
        rejection_reason = data.get('rejection_reason')

        # Reject transaction
        result = service.reject_transaction(
            db=db_session,
            transaction_id=transaction_id,
            auditor_user_id=current_user_id,
            rejection_reason=rejection_reason
        )

        if not result['success']:
            if 'not found' in result.get('error', '').lower():
                raise NotFoundException(f'Transaction {transaction_id} not found')
            elif 'not pending' in result.get('error', '').lower():
                raise BadRequestException(result.get('error', 'Transaction is not in pending status'))

            return {
                'success': False,
                'message': result.get('error', 'Failed to reject transaction'),
                'error': result.get('error'),
                'data': None
            }

        return {
            'success': True,
            'message': result['message'],
            'data': result['data']
        }

    except NotFoundException:
        raise  # Re-raise not found errors

    except BadRequestException:
        raise  # Re-raise bad request errors

    except Exception as e:
        logger.error(f"Error rejecting transaction {transaction_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': f'Failed to reject transaction {transaction_id}',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def handle_approve_transaction_record(
    service: ManualAuditService,
    db_session: Any,
    record_id: int,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/audit/manual/record/{id}/approve - Approve a pending transaction record

    Expected payload:
    {
        "notes": "Optional audit notes"
    }
    """
    try:
        logger.info(f"Approving transaction record {record_id} by user {current_user_id}")

        # Parse request data
        notes = data.get('notes')

        # Approve transaction record
        result = service.approve_transaction_record(
            db=db_session,
            record_id=record_id,
            auditor_user_id=current_user_id,
            notes=notes
        )

        if not result['success']:
            if 'not found' in result.get('error', '').lower():
                raise NotFoundException(f'Transaction record {record_id} not found')
            elif 'not pending' in result.get('error', '').lower():
                raise BadRequestException(result.get('error', 'Transaction record is not in pending status'))

            return {
                'success': False,
                'message': result.get('error', 'Failed to approve transaction record'),
                'error': result.get('error'),
                'data': None
            }

        transaction_id = result.get('data', {}).get('transaction_id')
        if transaction_id is not None and organization_id is not None:
            try:
                txn_service = TransactionService(db_session)
                txn_service.create_txn_approved_notifications_if_all_records_approved(
                    transaction_id=int(transaction_id),
                    organization_id=organization_id,
                    created_by_id=int(current_user_id),
                )
            except Exception as e:
                logger.warning(
                    "TXN_APPROVED notifications failed for transaction_id=%s: %s",
                    transaction_id,
                    str(e),
                )
        return {
            'success': True,
            'message': result['message'],
            'data': result['data']
        }

    except NotFoundException:
        raise  # Re-raise not found errors

    except BadRequestException:
        raise  # Re-raise bad request errors

    except Exception as e:
        logger.error(f"Error approving transaction record {record_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': f'Failed to approve transaction record {record_id}',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def handle_reject_transaction_record(
    service: ManualAuditService,
    db_session: Any,
    record_id: int,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/audit/manual/record/{id}/reject - Reject a pending transaction record

    Expected payload:
    {
        "rejection_reason": "Optional reason for rejection"
    }
    """
    try:
        logger.info(f"Rejecting transaction record {record_id} by user {current_user_id}")

        # Parse request data
        rejection_reason = data.get('rejection_reason')

        # Reject transaction record
        result = service.reject_transaction_record(
            db=db_session,
            record_id=record_id,
            auditor_user_id=current_user_id,
            rejection_reason=rejection_reason
        )

        if not result['success']:
            if 'not found' in result.get('error', '').lower():
                raise NotFoundException(f'Transaction record {record_id} not found')
            elif 'not pending' in result.get('error', '').lower():
                raise BadRequestException(result.get('error', 'Transaction record is not in pending status'))

            return {
                'success': False,
                'message': result.get('error', 'Failed to reject transaction record'),
                'error': result.get('error'),
                'data': None
            }

        transaction_id = result.get('data', {}).get('transaction_id')
        if transaction_id is not None and organization_id is not None:
            try:
                txn_service = TransactionService(db_session)
                txn_service.create_txn_rejected_notifications_for_record(
                    transaction_id=int(transaction_id),
                    record_id=record_id,
                    organization_id=organization_id,
                    created_by_id=int(current_user_id),
                )
            except Exception as e:
                logger.warning(
                    "TXN_REJECTED (record) notifications failed for record_id=%s: %s",
                    record_id,
                    str(e),
                )
        return {
            'success': True,
            'message': result['message'],
            'data': result['data']
        }

    except NotFoundException:
        raise  # Re-raise not found errors

    except BadRequestException:
        raise  # Re-raise bad request errors

    except Exception as e:
        logger.error(f"Error rejecting transaction record {record_id}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': f'Failed to reject transaction record {record_id}',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def _create_txn_approved_notifications_for_bulk(
    db_session: Any,
    organization_id: int,
    current_user_id: int,
    transaction_ids: list,
) -> None:
    """Create TXN_APPROVED notifications (BELL + EMAIL stub) for each successfully approved transaction."""
    if not transaction_ids or organization_id is None:
        return
    txn_service = TransactionService(db_session)
    for tid in transaction_ids:
        try:
            txn_service.create_txn_approved_notifications(
                transaction_id=int(tid),
                organization_id=organization_id,
                created_by_id=int(current_user_id),
            )
        except Exception as e:
            logger.warning("TXN_APPROVED notifications failed for transaction_id=%s: %s", tid, str(e))


def _create_txn_rejected_notifications_for_bulk(
    db_session: Any,
    organization_id: int,
    current_user_id: int,
    transaction_ids: list,
) -> None:
    """Create TXN_REJECTED notifications (BELL + EMAIL stub) for each successfully rejected transaction."""
    if not transaction_ids or organization_id is None:
        return
    txn_service = TransactionService(db_session)
    for tid in transaction_ids:
        try:
            txn_service.create_txn_rejected_notifications(
                transaction_id=int(tid),
                organization_id=organization_id,
                created_by_id=int(current_user_id),
            )
        except Exception as e:
            logger.warning("TXN_REJECTED notifications failed for transaction_id=%s: %s", tid, str(e))


def handle_bulk_approve_transactions(
    service: ManualAuditService,
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/audit/manual/transactions/bulk/approve - Bulk approve multiple pending transactions

    Expected payload:
    {
        "transaction_ids": [1, 2, 3],  // Required: array of transaction IDs
        "notes": "Optional audit notes applied to all transactions"
    }

    OR with per-item notes:
    {
        "items": [
            {"transaction_id": 1, "notes": "Specific notes for transaction 1"},
            {"transaction_id": 2, "notes": "Specific notes for transaction 2"}
        ]
    }
    """
    try:
        logger.info(f"Bulk approving transactions by user {current_user_id}")

        # Parse request data - support both formats
        transaction_ids = []
        global_notes = data.get('notes')
        items = data.get('items', [])

        if items:
            # Advanced format with per-item notes
            transaction_ids = [item.get('transaction_id') for item in items if item.get('transaction_id')]
            if not transaction_ids:
                raise ValidationException('At least one valid transaction_id is required in items array')
        else:
            # Simple format with transaction_ids array
            transaction_ids = data.get('transaction_ids', [])
            if not transaction_ids:
                raise ValidationException('transaction_ids array is required and cannot be empty')

        # Validate transaction_ids are integers
        try:
            transaction_ids = [int(tid) for tid in transaction_ids]
        except (ValueError, TypeError):
            raise ValidationException('All transaction_ids must be valid integers')

        # If using items format, process with per-item notes
        if items and len(items) > 0:
            results = []
            errors = []
            for item in items:
                transaction_id = item.get('transaction_id')
                if not transaction_id:
                    continue
                try:
                    transaction_id = int(transaction_id)
                    item_notes = item.get('notes') or global_notes
                    result = service.approve_transaction(
                        db=db_session,
                        transaction_id=transaction_id,
                        auditor_user_id=current_user_id,
                        notes=item_notes
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

            _create_txn_approved_notifications_for_bulk(
                db_session, organization_id, current_user_id,
                [r['transaction_id'] for r in results]
            )
            return {
                'success': len(errors) == 0,
                'message': f'Bulk approve completed: {len(results)} successful, {len(errors)} failed',
                'data': {
                    'results': results,
                    'errors': errors,
                    'summary': {
                        'total_requested': len(items),
                        'successful': len(results),
                        'failed': len(errors)
                    }
                }
            }
        else:
            # Simple format - use global notes
            result = service.bulk_approve_transactions(
                db=db_session,
                transaction_ids=transaction_ids,
                auditor_user_id=current_user_id,
                notes=global_notes
            )
            _create_txn_approved_notifications_for_bulk(
                db_session, organization_id, current_user_id,
                [r['transaction_id'] for r in result.get('results', [])]
            )
            return {
                'success': result['success'],
                'message': f'Bulk approve completed: {result["summary"]["successful"]} successful, {result["summary"]["failed"]} failed',
                'data': result
            }

    except ValidationException:
        raise  # Re-raise validation errors
    except Exception as e:
        logger.error(f"Error in bulk approve transactions: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': 'Failed to bulk approve transactions',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }


def handle_bulk_reject_transactions(
    service: ManualAuditService,
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/audit/manual/transactions/bulk/reject - Bulk reject multiple pending transactions

    Expected payload:
    {
        "transaction_ids": [1, 2, 3],  // Required: array of transaction IDs
        "rejection_reason": "Optional rejection reason applied to all transactions"
    }

    OR with per-item reasons:
    {
        "items": [
            {"transaction_id": 1, "rejection_reason": "Specific reason for transaction 1"},
            {"transaction_id": 2, "rejection_reason": "Specific reason for transaction 2"}
        ]
    }
    """
    try:
        logger.info(f"Bulk rejecting transactions by user {current_user_id}")

        # Parse request data - support both formats
        transaction_ids = []
        global_rejection_reason = data.get('rejection_reason')
        items = data.get('items', [])

        if items:
            # Advanced format with per-item reasons
            transaction_ids = [item.get('transaction_id') for item in items if item.get('transaction_id')]
            if not transaction_ids:
                raise ValidationException('At least one valid transaction_id is required in items array')
        else:
            # Simple format with transaction_ids array
            transaction_ids = data.get('transaction_ids', [])
            if not transaction_ids:
                raise ValidationException('transaction_ids array is required and cannot be empty')

        # Validate transaction_ids are integers
        try:
            transaction_ids = [int(tid) for tid in transaction_ids]
        except (ValueError, TypeError):
            raise ValidationException('All transaction_ids must be valid integers')

        # If using items format, process with per-item reasons
        if items and len(items) > 0:
            results = []
            errors = []
            for item in items:
                transaction_id = item.get('transaction_id')
                if not transaction_id:
                    continue
                try:
                    transaction_id = int(transaction_id)
                    item_reason = item.get('rejection_reason') or global_rejection_reason
                    result = service.reject_transaction(
                        db=db_session,
                        transaction_id=transaction_id,
                        auditor_user_id=current_user_id,
                        rejection_reason=item_reason
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

            _create_txn_rejected_notifications_for_bulk(
                db_session, organization_id, current_user_id,
                [r['transaction_id'] for r in results]
            )
            return {
                'success': len(errors) == 0,
                'message': f'Bulk reject completed: {len(results)} successful, {len(errors)} failed',
                'data': {
                    'results': results,
                    'errors': errors,
                    'summary': {
                        'total_requested': len(items),
                        'successful': len(results),
                        'failed': len(errors)
                    }
                }
            }
        else:
            # Simple format - use global rejection reason
            result = service.bulk_reject_transactions(
                db=db_session,
                transaction_ids=transaction_ids,
                auditor_user_id=current_user_id,
                rejection_reason=global_rejection_reason
            )
            _create_txn_rejected_notifications_for_bulk(
                db_session, organization_id, current_user_id,
                [r['transaction_id'] for r in result.get('results', [])]
            )
            return {
                'success': result['success'],
                'message': f'Bulk reject completed: {result["summary"]["successful"]} successful, {result["summary"]["failed"]} failed',
                'data': result
            }

    except ValidationException:
        raise  # Re-raise validation errors
    except Exception as e:
        logger.error(f"Error in bulk reject transactions: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': 'Failed to bulk reject transactions',
            'error': f'Internal server error: {str(e)}',
            'data': None
        }