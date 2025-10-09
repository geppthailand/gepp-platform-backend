"""
Transaction Audit API handlers for AI-based audit operations
"""

from typing import Dict, Any
import logging
import traceback
import os
from sqlalchemy import and_, desc

from .transaction_audit_service import TransactionAuditService
from ....models.logs.transaction_audit_history import TransactionAuditHistory
from ....models.transactions.transactions import Transaction, TransactionStatus

logger = logging.getLogger(__name__)
from ....exceptions import (
    APIException,
    UnauthorizedException,
    NotFoundException,
    BadRequestException,
    ValidationException
)


def handle_transaction_audit_routes(event: Dict[str, Any], data: Dict[str, Any], **params) -> Dict[str, Any]:
    """
    Main handler for transaction audit routes
    """
    path = event.get("rawPath", "")
    method = params.get('method', 'GET')
    query_params = params.get('query_params', {})

    # Get database session from commonParams
    db_session = params.get('db_session')
    if not db_session:
        raise APIException('Database session not provided')

    # Get OpenAI API key from environment
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        raise APIException('OpenAI API key not configured')

    transaction_audit_service = TransactionAuditService(openai_api_key)

    # Extract current user info from JWT token (passed from app.py)
    current_user = params.get('current_user', {})
    current_user_id = current_user.get('user_id')
    current_user_organization_id = current_user.get('organization_id')

    try:
        # Route to specific handlers
        if path == '/api/transaction_audit/sync_ai_audit' and method == 'POST':
            return handle_sync_ai_audit(
                transaction_audit_service,
                db_session,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path == '/api/transaction_audit/audit_history' and method == 'GET':
            return handle_get_audit_history(
                db_session,
                query_params,
                current_user_organization_id
            )

        elif path == '/api/transaction_audit/reset_all' and method == 'POST':
            return handle_reset_all_transactions(
                db_session,
                data,
                current_user_organization_id
            )

        else:
            # Route not found
            raise NotFoundException(f'Transaction audit route not found: {method} {path}')

    except APIException:
        # Re-raise API exceptions as-is
        raise
    except ValidationException:
        # Re-raise validation exceptions as-is
        raise
    except Exception as e:
        # Log unexpected errors and return generic API error
        logger.error(f'Unexpected error in transaction audit handler: {str(e)}')
        logger.error(f'Traceback: {traceback.format_exc()}')
        raise APIException(f'Internal server error: {str(e)}')


def handle_sync_ai_audit(
    service: TransactionAuditService,
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/sync_ai_audit - Perform synchronous AI audit

    Expected payload:
    {
        "organization_id": <optional_int>,  # Override for multi-org users
        "filter_options": {                 # Optional filtering
            "date_from": "2025-09-01",
            "date_to": "2025-09-30",
            "transaction_ids": [1, 2, 3]   # Specific transactions to audit
        }
    }
    """
    try:
        logger.info(f"AI audit request from user {current_user_id} for organization {organization_id}")

        # Parse request data
        request_org_id = data.get('organization_id', organization_id)
        filter_options = data.get('filter_options', {})

        # Authorization check - ensure user can audit for the requested organization
        if request_org_id != organization_id and organization_id is not None:
            raise UnauthorizedException('You can only audit transactions for your own organization')

        # Perform synchronous AI audit
        audit_result = service.sync_ai_audit(
            db=db_session,
            organization_id=request_org_id
        )

        # Log audit activity
        logger.info(f"AI audit completed for organization {request_org_id}. "
                   f"Processed: {audit_result.get('processed_transactions', 0)} transactions")

        return {
            'success': audit_result['success'],
            'message': audit_result.get('message', 'AI audit completed'),
            'data': {
                'total_transactions': audit_result.get('total_transactions', 0),
                'processed_transactions': audit_result.get('processed_transactions', 0),
                'updated_transactions': audit_result.get('updated_transactions', 0),
                'audit_results': audit_result.get('audit_results', []),
                'organization_id': request_org_id,
                'audited_by_user_id': current_user_id
            },
            'error': audit_result.get('error') if not audit_result['success'] else None
        }

    except ValidationException as e:
        logger.warning(f"Validation error in AI audit: {str(e)}")
        return {
            'success': False,
            'message': 'Validation error',
            'error': str(e),
            'data': None
        }

    except UnauthorizedException as e:
        logger.warning(f"Authorization error in AI audit: {str(e)}")
        raise  # Re-raise authorization errors

    except Exception as e:
        logger.error(f"Error in AI audit handler: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return {
            'success': False,
            'message': 'AI audit failed',
            'error': f'Internal server error: {str(e)}',
            'data': {
                'total_transactions': 0,
                'processed_transactions': 0,
                'updated_transactions': 0,
                'audit_results': [],
                'organization_id': organization_id,
                'audited_by_user_id': current_user_id
            }
        }


def handle_get_audit_history(
    db_session: Any,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/transaction_audit/audit_history - Get audit history for organization

    Query parameters:
    - page: int (default: 1)
    - page_size: int (default: 20)
    - status: str (optional filter by status)
    """
    try:
        # Parse query parameters
        page = int(query_params.get('page', 1))
        page_size = int(query_params.get('page_size', 20))
        status_filter = query_params.get('status')

        logger.info(f"Fetching audit history for organization {organization_id}")

        # Build query
        query = db_session.query(TransactionAuditHistory).filter(
            and_(
                TransactionAuditHistory.organization_id == organization_id,
                TransactionAuditHistory.deleted_date.is_(None)
            )
        )

        # Apply status filter if provided
        if status_filter:
            query = query.filter(TransactionAuditHistory.status == status_filter)

        # Order by most recent first
        query = query.order_by(desc(TransactionAuditHistory.created_date))

        # Get total count
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        audit_histories = query.offset(offset).limit(page_size).all()

        # Serialize results
        history_data = [history.to_dict() for history in audit_histories]

        return {
            'success': True,
            'data': history_data,
            'meta': {
                'page': page,
                'page_size': page_size,
                'total': total_count,
                'total_pages': (total_count + page_size - 1) // page_size,
                'has_more': offset + page_size < total_count
            }
        }

    except Exception as e:
        logger.error(f"Error fetching audit history: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to fetch audit history: {str(e)}')


def handle_reset_all_transactions(
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/reset_all - Reset all transactions to pending status

    Resets all non-pending transactions back to pending status for the organization
    """
    try:
        logger.info(f"Resetting all transactions for organization {organization_id}")

        # Query transactions that are not in pending status
        transactions_to_reset = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.status != TransactionStatus.pending,
                Transaction.deleted_date.is_(None)
            )
        ).all()

        updated_count = 0

        # Reset each transaction
        for transaction in transactions_to_reset:
            transaction.status = TransactionStatus.pending
            transaction.ai_audit_status = None
            transaction.ai_audit_note = None
            updated_count += 1

        # Commit changes
        db_session.commit()

        logger.info(f"Reset {updated_count} transactions to pending status")

        return {
            'success': True,
            'message': f'Successfully reset {updated_count} transactions to pending status',
            'data': {
                'updated_count': updated_count,
                'organization_id': organization_id
            }
        }

    except Exception as e:
        db_session.rollback()
        logger.error(f"Error resetting transactions: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to reset transactions: {str(e)}')