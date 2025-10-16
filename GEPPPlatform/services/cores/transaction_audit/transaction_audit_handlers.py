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
from ....models.transactions.transactions import Transaction, TransactionStatus, AIAuditStatus

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

    # Get Gemini API key from environment
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        raise APIException('Gemini API key not configured')

    transaction_audit_service = TransactionAuditService(gemini_api_key)

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

        elif path == '/api/transaction_audit/add_ai_audit_queue' and method == 'POST':
            return handle_add_ai_audit_queue(
                db_session,
                data,
                current_user_organization_id,
                current_user_id
            )

        elif path == '/api/transaction_audit/process_queue' and method == 'POST':
            return handle_process_audit_queue(db_session)

        elif path == '/api/transaction_audit/audit_report' and method == 'GET':
            return handle_get_audit_report(
                db_session,
                query_params,
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
            transaction.ai_audit_status = AIAuditStatus.null  # Use enum value, not None
            transaction.ai_audit_note = None
            transaction.reject_triggers = []  # Clear reject triggers
            transaction.warning_triggers = []  # Clear warning triggers
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


def handle_add_ai_audit_queue(
    db_session: Any,
    data: Dict[str, Any],
    organization_id: int,
    current_user_id: int = None
) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/add_ai_audit_queue - Queue transactions for AI audit

    Changes all transactions with ai_audit_status='null' to 'queued' for the organization.
    Creates an audit history record with 'in_progress' status to be processed by cron later.

    Expected payload:
    {
        "transaction_ids": [1, 2, 3]  # Optional: specific transactions to queue
    }
    """
    try:
        logger.info(f"Adding transactions to AI audit queue for organization {organization_id}")

        # Get optional transaction IDs filter
        transaction_ids = data.get('transaction_ids', None)

        # Build base query for transactions with 'null' ai_audit_status
        query = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.ai_audit_status == AIAuditStatus.null,
                Transaction.deleted_date.is_(None)
            )
        )

        # Apply transaction IDs filter if provided
        if transaction_ids:
            query = query.filter(Transaction.id.in_(transaction_ids))

        transactions_to_queue = query.all()
        queued_count = 0
        queued_transaction_ids = []

        # Update ai_audit_status to 'queued' for each transaction
        for transaction in transactions_to_queue:
            transaction.ai_audit_status = AIAuditStatus.queued
            queued_transaction_ids.append(transaction.id)
            queued_count += 1

        # Create audit history record with 'in_progress' status
        # This will be picked up and processed by cron job later
        from datetime import datetime, timezone
        audit_history = TransactionAuditHistory(
            organization_id=organization_id,
            triggered_by_user_id=current_user_id,
            transactions=queued_transaction_ids,
            audit_info={
                'status': 'queued',
                'message': 'Audit batch queued for processing'
            },
            total_transactions=queued_count,
            processed_transactions=0,
            approved_count=0,
            rejected_count=0,
            status='in_progress',
            started_at=datetime.now(timezone.utc),
            completed_at=None
        )

        db_session.add(audit_history)

        # Commit changes
        db_session.commit()

        logger.info(f"Queued {queued_count} transactions for AI audit with audit history ID {audit_history.id}")

        return {
            'success': True,
            'message': f'Successfully queued {queued_count} transactions for AI audit',
            'data': {
                'queued_count': queued_count,
                'organization_id': organization_id,
                'audit_history_id': audit_history.id,
                'transaction_ids': queued_transaction_ids if transaction_ids else None
            }
        }

    except Exception as e:
        db_session.rollback()
        logger.error(f"Error queueing transactions for AI audit: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to queue transactions for AI audit: {str(e)}')


def handle_process_audit_queue(db_session: Any) -> Dict[str, Any]:
    """
    Handle POST /api/transaction_audit/process_queue - Process in_progress audit batches

    This endpoint manually triggers the processing of queued audit batches.
    Normally this would be called by a cron job, but can also be triggered manually for testing.

    Returns processing results including number of batches processed.
    """
    try:
        from .cron_process_audit_queue import process_audit_queue

        logger.info("Manual trigger: Processing audit queue")

        result = process_audit_queue(db_session)

        return {
            'success': result.get('success', False),
            'message': result.get('message', 'Queue processing completed'),
            'data': {
                'processed_batches': result.get('processed_batches', 0),
                'failed_batches': result.get('failed_batches', 0),
                'total_batches': result.get('total_batches', 0)
            },
            'error': result.get('error')
        }

    except Exception as e:
        logger.error(f"Error processing audit queue: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to process audit queue: {str(e)}')


def handle_get_audit_report(
    db_session: Any,
    query_params: Dict[str, Any],
    organization_id: int
) -> Dict[str, Any]:
    """
    Handle GET /api/transaction_audit/audit_report - Get comprehensive audit report with filters

    Query parameters:
    - date_from: str (ISO date) - Filter transactions from this date
    - date_to: str (ISO date) - Filter transactions to this date
    - location: str - Filter by location name
    - material_type: str - Filter by material type
    - status: str - Filter by transaction status
    - ai_audit_status: str - Filter by AI audit status (approved, rejected)

    Returns comprehensive report including:
    - Summary statistics (total, approved, rejected counts and percentages)
    - Monthly trend data for charts
    - Rejection reasons breakdown
    - List of transactions with audit details
    """
    try:
        import json
        from datetime import datetime
        from sqlalchemy import func, extract
        from collections import Counter

        logger.info(f"Generating audit report for organization {organization_id} with filters: {query_params}")

        # Build base query for transactions
        query = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None)
            )
        )

        # Apply filters
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        location = query_params.get('location')
        material_type = query_params.get('material_type')
        status = query_params.get('status')
        ai_audit_status = query_params.get('ai_audit_status')

        if date_from:
            query = query.filter(Transaction.transaction_date >= date_from)

        if date_to:
            query = query.filter(Transaction.transaction_date <= date_to)

        if status:
            query = query.filter(Transaction.status == status)

        if ai_audit_status:
            if ai_audit_status == 'approved':
                query = query.filter(Transaction.ai_audit_status == AIAuditStatus.approved)
            elif ai_audit_status == 'rejected':
                query = query.filter(Transaction.ai_audit_status == AIAuditStatus.rejected)

        # Get all matching transactions
        transactions = query.all()

        # Calculate summary statistics
        total_transactions = len(transactions)
        approved_transactions = [t for t in transactions if t.ai_audit_status == AIAuditStatus.approved]
        rejected_transactions = [t for t in transactions if t.ai_audit_status == AIAuditStatus.rejected]

        approved_count = len(approved_transactions)
        rejected_count = len(rejected_transactions)

        approved_percentage = round((approved_count / total_transactions * 100), 2) if total_transactions > 0 else 0
        rejected_percentage = round((rejected_count / total_transactions * 100), 2) if total_transactions > 0 else 0

        # Monthly trend data (for stacked bar chart)
        # Group transactions by month
        monthly_data = {}
        for transaction in transactions:
            if transaction.transaction_date:
                month_key = transaction.transaction_date.strftime('%Y-%m')
                if month_key not in monthly_data:
                    monthly_data[month_key] = {'approved': 0, 'rejected': 0}

                if transaction.ai_audit_status == AIAuditStatus.approved:
                    monthly_data[month_key]['approved'] += 1
                elif transaction.ai_audit_status == AIAuditStatus.rejected:
                    monthly_data[month_key]['rejected'] += 1

        # Sort by month and format for frontend
        monthly_trends = []
        for month in sorted(monthly_data.keys()):
            monthly_trends.append({
                'month': month,
                'approved': monthly_data[month]['approved'],
                'rejected': monthly_data[month]['rejected']
            })

        # Rejection reasons breakdown (for pie chart)
        # Extract all reject_triggers and count occurrences
        rejection_reasons = []
        for transaction in rejected_transactions:
            if transaction.reject_triggers and isinstance(transaction.reject_triggers, list):
                rejection_reasons.extend(transaction.reject_triggers)

        # Count frequency of each rejection reason
        reason_counts = Counter(rejection_reasons)
        rejection_breakdown = [
            {'rule_id': rule_id, 'count': count}
            for rule_id, count in reason_counts.most_common()
        ]

        # Prepare transaction list for รายละเอียดการตรวจสอบ
        transaction_list = []
        for transaction in transactions:
            # Parse ai_audit_note if it's JSON
            audit_details = None
            if transaction.ai_audit_note:
                try:
                    audit_details = json.loads(transaction.ai_audit_note)
                except:
                    audit_details = {'note': transaction.ai_audit_note}

            transaction_list.append({
                'id': transaction.id,
                'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
                'status': transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status),
                'ai_audit_status': transaction.ai_audit_status.value if hasattr(transaction.ai_audit_status, 'value') else None,
                'weight_kg': float(transaction.weight_kg) if transaction.weight_kg else 0,
                'total_amount': float(transaction.total_amount) if transaction.total_amount else 0,
                'reject_triggers': transaction.reject_triggers if transaction.reject_triggers else [],
                'warning_triggers': transaction.warning_triggers if transaction.warning_triggers else [],
                'audit_details': audit_details
            })

        # Compile final report
        report = {
            'summary': {
                'total_transactions': total_transactions,
                'approved_count': approved_count,
                'rejected_count': rejected_count,
                'approved_percentage': approved_percentage,
                'rejected_percentage': rejected_percentage
            },
            'monthly_trends': monthly_trends,
            'rejection_breakdown': rejection_breakdown,
            'transactions': transaction_list,
            'filters_applied': {
                'date_from': date_from,
                'date_to': date_to,
                'location': location,
                'material_type': material_type,
                'status': status,
                'ai_audit_status': ai_audit_status
            }
        }

        logger.info(f"Successfully generated audit report with {total_transactions} transactions")

        return {
            'success': True,
            'message': 'Audit report generated successfully',
            'data': report
        }

    except Exception as e:
        logger.error(f"Error generating audit report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to generate audit report: {str(e)}')