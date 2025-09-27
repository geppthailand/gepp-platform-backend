"""
Manual Audit API handlers for human-driven audit operations
"""

from typing import Dict, Any
import logging
import traceback

from .manual_audit_service import ManualAuditService

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