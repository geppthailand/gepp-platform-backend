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
from ....models.transactions.transaction_records import TransactionRecord

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

    # Get Vertex AI configuration from environment
    project_id = os.getenv('VERTEX_AI_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
    location = os.getenv('VERTEX_AI_LOCATION', 'us-central1')

    if not project_id:
        raise APIException('Vertex AI project ID not configured. Set VERTEX_AI_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable.')

    transaction_audit_service = TransactionAuditService(
        project_id=project_id,
        location=location
    )

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

    Resets all transactions back to pending status and ai_audit_status to null for the organization
    """
    try:
        logger.info(f"Resetting all transactions for organization {organization_id}")

        # Use bulk update SQL query for better performance
        updated_count = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None)
            )
        ).update(
            {
                Transaction.status: TransactionStatus.pending,
                Transaction.ai_audit_status: AIAuditStatus.null,
                Transaction.ai_audit_note: None,
                Transaction.reject_triggers: [],
                Transaction.warning_triggers: []
            },
            synchronize_session=False
        )

        # Commit changes
        db_session.commit()

        logger.info(f"Reset {updated_count} transactions to pending status with ai_audit_status null")

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

        # Get Gemini API key from environment
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not gemini_api_key:
            raise APIException('Gemini API key not configured')

        # Initialize service
        transaction_audit_service = TransactionAuditService(gemini_api_key)

        # Call service function to queue transactions
        result = transaction_audit_service.add_transaction_to_ai_audit_queue(
            db=db_session,
            organization_id=organization_id,
            user_id=current_user_id,
            transaction_ids=transaction_ids
        )

        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'data': {
                    'queued_count': result['queued_count'],
                    'organization_id': result['organization_id'],
                    'audit_history_id': result['audit_history_id'],
                    'transaction_ids': result.get('transaction_ids')
                }
            }
        else:
            return {
                'success': False,
                'message': result.get('message', 'Failed to queue transactions'),
                'error': result.get('error')
            }

    except APIException:
        # Re-raise API exceptions as-is
        raise
    except Exception as e:
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
    - search: str - Partial match search for transaction ID
    - date_from: str (ISO date) - Filter transactions from this date
    - date_to: str (ISO date) - Filter transactions to this date
    - district: str - Filter by origin_id (location ID used in transactions)
    - status: str - Filter by transaction status (not ai_audit_status)
    - page: int - Page number for pagination (default: 1)
    - page_size: int - Items per page (default: 100, max: 100)

    Returns comprehensive report including:
    - Summary statistics (total, approved, rejected counts and percentages) - based on ALL filtered transactions
    - Monthly trend data for charts - based on ALL filtered transactions
    - Rejection reasons breakdown - based on ALL filtered transactions
    - List of transactions with audit details - PAGINATED (100 per page, sorted by id)
    - Pagination metadata (total pages, current page, etc.)
    - Filter options for dropdowns
    """
    try:
        import json
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func, extract, String, exists
        from collections import Counter
        from ....models.subscriptions.organizations import OrganizationSetup
        
        # Import ZoneInfo for timezone handling (Python 3.9+)
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            # Fallback for Python < 3.9
            from backports.zoneinfo import ZoneInfo

        logger.info(f"Generating audit report for organization {organization_id} with filters: {query_params}")

        # Log pagination parameters for debugging
        page = int(query_params.get('page', 1))
        page_size = min(int(query_params.get('page_size', 100)), 100)
        logger.info(f"PAGINATION DEBUG: Requested page={page}, page_size={page_size}")

        # Build base query for transactions
        query = db_session.query(Transaction).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None)
            )
        )

        # Apply filters
        search = query_params.get('search')
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        district = query_params.get('district')
        status = query_params.get('status')

        # Ensure page is at least 1
        if page < 1:
            page = 1

        # Search filter - partial match on transaction ID
        if search:
            query = query.filter(Transaction.id.cast(String).contains(search))

        # Date filters - filter by TransactionRecord.transaction_date
        # Include transaction if any of its records fall within the date range
        # Use Asia/Bangkok timezone (UTC+7) as default for date-only strings
        if date_from or date_to:
            # Default timezone for date-only strings (Asia/Bangkok = UTC+7)
            default_tz = ZoneInfo('Asia/Bangkok')
            date_from_dt = None
            date_to_dt = None
            
            def parse_date_string(date_str: str, is_end_of_day: bool = False):
                """Parse date string, treating date-only strings as Asia/Bangkok timezone"""
                # Check if it's a date-only string (YYYY-MM-DD format)
                is_date_only = False
                try:
                    # Try parsing as ISO format with timezone
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    if dt.tzinfo:
                        return dt.astimezone(timezone.utc)
                except ValueError:
                    pass
                
                try:
                    # Try parsing as ISO format without timezone
                    dt = datetime.fromisoformat(date_str)
                    if dt.tzinfo:
                        return dt.astimezone(timezone.utc)
                    is_date_only = True
                except ValueError:
                    # Try parsing as date string (YYYY-MM-DD)
                    try:
                        dt = datetime.strptime(date_str, '%Y-%m-%d')
                        is_date_only = True
                    except ValueError:
                        raise ValueError(f"Invalid date format: {date_str}")
                
                # If date-only or no timezone, treat as Asia/Bangkok timezone
                if is_date_only or dt.tzinfo is None:
                    if is_end_of_day:
                        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                    else:
                        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    dt = dt.replace(tzinfo=default_tz)
                    return dt.astimezone(timezone.utc)
                else:
                    return dt.astimezone(timezone.utc)
            
            if date_from:
                if isinstance(date_from, str):
                    date_from_dt = parse_date_string(date_from, is_end_of_day=False)
                else:
                    date_from_dt = date_from
                    if date_from_dt.tzinfo is None:
                        date_from_dt = date_from_dt.replace(tzinfo=timezone.utc)
                    else:
                        date_from_dt = date_from_dt.astimezone(timezone.utc)
                    # Ensure start of day in local timezone
                    date_from_local = date_from_dt.astimezone(default_tz)
                    date_from_local = date_from_local.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_from_dt = date_from_local.astimezone(timezone.utc)
            
            if date_to:
                if isinstance(date_to, str):
                    date_to_dt = parse_date_string(date_to, is_end_of_day=True)
                else:
                    date_to_dt = date_to
                    if date_to_dt.tzinfo is None:
                        date_to_dt = date_to_dt.replace(tzinfo=timezone.utc)
                    else:
                        date_to_dt = date_to_dt.astimezone(timezone.utc)
                    # Ensure end of day in local timezone
                    date_to_local = date_to_dt.astimezone(default_tz)
                    date_to_local = date_to_local.replace(hour=23, minute=59, second=59, microsecond=999999)
                    date_to_dt = date_to_local.astimezone(timezone.utc)
            
            # Build EXISTS subquery to check if transaction has records in date range
            record_date_filter = and_(
                TransactionRecord.created_transaction_id == Transaction.id,
                TransactionRecord.is_active == True
            )
            
            if date_from_dt:
                record_date_filter = and_(
                    record_date_filter,
                    TransactionRecord.transaction_date >= date_from_dt
                )
            
            if date_to_dt:
                record_date_filter = and_(
                    record_date_filter,
                    TransactionRecord.transaction_date <= date_to_dt
                )
            
            # Use EXISTS to check if transaction has any records matching the date filter
            query = query.filter(exists().where(record_date_filter))

        # District (origin) filtering - supports composite "origin_id|tag_id|tenant_id"
        # Skip filtering if district is '' or 'all'
        if district and district != 'all':
            if '|' in district:
                try:
                    parts = district.split('|')
                    origin_id_int = int(parts[0]) if parts[0] else None
                    tag_id_int = int(parts[1]) if len(parts) > 1 and parts[1] else None
                    tenant_id_int = int(parts[2]) if len(parts) > 2 and parts[2] else None
                    if origin_id_int is not None:
                        query = query.filter(Transaction.origin_id == origin_id_int)
                    if tag_id_int is not None:
                        query = query.filter(Transaction.location_tag_id == tag_id_int)
                    if tenant_id_int is not None:
                        query = query.filter(Transaction.tenant_id == tenant_id_int)
                except (ValueError, TypeError):
                    query = query.filter(Transaction.id == -1)
            else:
                try:
                    origin_id_int = int(district)
                    query = query.filter(Transaction.origin_id == origin_id_int)
                except (ValueError, TypeError):
                    query = query.filter(Transaction.id == -1)

        # Status filter (transaction status, not ai_audit_status)
        if status:
            query = query.filter(Transaction.status == status)

        # Get all matching transactions for statistics (without pagination)
        all_transactions = query.all()

        # Get total count for pagination
        total_count = len(all_transactions)
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 0

        # Get paginated transactions sorted by id
        paginated_query = query.order_by(Transaction.id)
        offset = (page - 1) * page_size
        logger.info(f"PAGINATION DEBUG: Applying offset={offset}, limit={page_size} to query")
        paginated_transactions = paginated_query.offset(offset).limit(page_size).all()
        logger.info(f"PAGINATION DEBUG: Retrieved {len(paginated_transactions)} transactions")

        # Calculate summary statistics (based on ALL filtered transactions)
        total_transactions = len(all_transactions)
        approved_transactions = [t for t in all_transactions if t.ai_audit_status == AIAuditStatus.approved]
        rejected_transactions = [t for t in all_transactions if t.ai_audit_status == AIAuditStatus.rejected]
        queued_transactions = [t for t in all_transactions if t.ai_audit_status == AIAuditStatus.queued]

        approved_count = len(approved_transactions)
        rejected_count = len(rejected_transactions)
        queued_count = len(queued_transactions)

        approved_percentage = round((approved_count / total_transactions * 100), 2) if total_transactions > 0 else 0
        rejected_percentage = round((rejected_count / total_transactions * 100), 2) if total_transactions > 0 else 0
        queued_percentage = round((queued_count / total_transactions * 100), 2) if total_transactions > 0 else 0

        # Monthly trend data (for stacked bar chart)
        # Always show last 12 months (from 11 months ago to current month)
        from datetime import datetime, timedelta

        current_date = datetime.now()
        monthly_data = {}

        # Thai month abbreviations for display
        thai_month_names = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
                          'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

        # Generate last 12 months (from 11 months ago to current month)
        for i in range(11, -1, -1):
            # Calculate month by going back i months
            year = current_date.year
            month = current_date.month - i
            while month <= 0:
                month += 12
                year -= 1
            month_key = f"{year}-{month:02d}"
            month_idx = month - 1
            # Use Thai Buddhist year (add 543)
            buddhist_year = (year + 543) % 100  # Get last 2 digits
            # Format: month name and year on separate lines for frontend
            month_label = thai_month_names[month_idx]
            year_label = str(buddhist_year)
            monthly_data[month_key] = {
                'approved': 0,
                'rejected': 0,
                'month_label': month_label,
                'year_label': year_label
            }

        logger.info(f"Monthly data keys initialized (last 12 months): {list(monthly_data.keys())}")

        # Count transactions by month (based on ALL filtered transactions)
        approved_in_range = 0
        rejected_in_range = 0
        for transaction in all_transactions:
            if transaction.transaction_date:
                month_key = transaction.transaction_date.strftime('%Y-%m')
                # Only count if the month is in our last 12 months range
                if month_key in monthly_data:
                    # Count based on ai_audit_status
                    if transaction.ai_audit_status == AIAuditStatus.approved:
                        monthly_data[month_key]['approved'] += 1
                        approved_in_range += 1
                    elif transaction.ai_audit_status == AIAuditStatus.rejected:
                        monthly_data[month_key]['rejected'] += 1
                        rejected_in_range += 1

        logger.info(f"Transactions counted - approved: {approved_in_range}, rejected: {rejected_in_range}")

        # Sort by month and format for frontend (chronological order)
        monthly_trends = []
        for month_key in sorted(monthly_data.keys()):
            monthly_trends.append({
                'month': monthly_data[month_key]['month_label'],
                'year': monthly_data[month_key]['year_label'],
                'approved': monthly_data[month_key]['approved'],
                'rejected': monthly_data[month_key]['rejected']
            })

        logger.info(f"Monthly trends data: {monthly_trends}")

        # Rejection reasons breakdown (for pie chart)
        # Extract all reject_triggers and count occurrences
        rejection_reasons = []
        for transaction in rejected_transactions:
            if transaction.reject_triggers and isinstance(transaction.reject_triggers, list):
                rejection_reasons.extend(transaction.reject_triggers)

        # Count frequency of each rejection reason
        reason_counts = Counter(rejection_reasons)

        # Fetch rule names from audit_rules table
        from ....models.audit_rules import AuditRule
        rule_ids = list(reason_counts.keys())
        audit_rules = db_session.query(AuditRule).filter(AuditRule.rule_id.in_(rule_ids)).all()
        rule_name_map = {rule.rule_id: rule.rule_name for rule in audit_rules}

        rejection_breakdown = [
            {
                'rule_id': rule_id,
                'rule_name': rule_name_map.get(rule_id, rule_id),  # Fallback to rule_id if name not found
                'count': count
            }
            for rule_id, count in reason_counts.most_common()
        ]

        # Prepare transaction list for รายละเอียดการตรวจสอบ (PAGINATED)
        transaction_list = []
        for transaction in paginated_transactions:
            # Parse ai_audit_note if it's JSON
            audit_details = None
            reject_messages = []

            if transaction.ai_audit_note:
                try:
                    audit_details = json.loads(transaction.ai_audit_note)

                    # Extract reject_messages from compact format
                    if isinstance(audit_details, dict) and 's' in audit_details and 'v' in audit_details:
                        # Compact format: extract messages from violations
                        for violation in audit_details.get('v', []):
                            msg = violation.get('m', '')
                            if msg:
                                reject_messages.append(msg)
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
                'reject_messages': reject_messages if reject_messages else [],
                'audit_details': audit_details
            })

        # Build filter options for frontend (origin, origin+tag, origin+tenant, origin+tag+tenant, materials)
        from ....models.users.user_location import UserLocation
        from ....models.users.user_related import UserLocationTag, UserTenant
        from ....models.cores.references import Material

        # Get distinct (origin_id, location_tag_id, tenant_id) from non-deleted transactions
        combos_result = db_session.query(
            Transaction.origin_id,
            Transaction.location_tag_id,
            Transaction.tenant_id
        ).filter(
            and_(
                Transaction.organization_id == organization_id,
                Transaction.deleted_date.is_(None),
                Transaction.origin_id.isnot(None)
            )
        ).distinct().all()

        origin_ids = list({row[0] for row in combos_result if row[0] is not None})
        tag_ids = list({row[1] for row in combos_result if row[1] is not None})
        tenant_ids = list({row[2] for row in combos_result if row[2] is not None})
        # Per-origin: only tags/tenants that actually appear with that origin (for filter options)
        tags_by_origin = {}   # origin_id -> set of tag_ids
        tenants_by_origin = {}  # origin_id -> set of tenant_ids
        for origin_id, tag_id, tenant_id in combos_result:
            if origin_id is None:
                continue
            if origin_id not in tags_by_origin:
                tags_by_origin[origin_id] = set()
            if tag_id is not None:
                tags_by_origin[origin_id].add(tag_id)
            if origin_id not in tenants_by_origin:
                tenants_by_origin[origin_id] = set()
            if tenant_id is not None:
                tenants_by_origin[origin_id].add(tenant_id)

        districts = []
        origin_options = []  # Composite options: location, location·tag, location·tenant, location·tag·tenant

        if origin_ids:
            # Fetch origin location records
            origin_locations = db_session.query(UserLocation).filter(
                UserLocation.id.in_(origin_ids)
            ).all()

            # Build location paths for these origins (similar to _build_location_paths in user_service.py)
            # Query for active organization setup first, then fallback to latest
            org_setup = db_session.query(OrganizationSetup).filter(
                and_(
                    OrganizationSetup.organization_id == organization_id,
                    OrganizationSetup.is_active == True
                )
            ).first()
            
            # If no active setup found, get the latest version
            if not org_setup:
                org_setup = db_session.query(OrganizationSetup).filter(
                    OrganizationSetup.organization_id == organization_id
                ).order_by(OrganizationSetup.created_date.desc()).first()

            location_paths = {}
            if org_setup and org_setup.root_nodes:
                # Fetch ALL locations in the organization to get their names
                all_locations = db_session.query(UserLocation).filter(
                    and_(
                        UserLocation.organization_id == organization_id,
                        UserLocation.is_active == True,
                        UserLocation.deleted_date.is_(None)
                    )
                ).all()

                # Create name lookup map
                location_names = {
                    loc.id: loc.display_name or loc.name_en or loc.name_th or f"Location {loc.id}"
                    for loc in all_locations
                }

                # Build parent map from tree structure
                # key: nodeId, value: parentId
                parent_map = {}

                def build_parent_map(nodes, parent_id=None):
                    """Recursively build parent map from tree structure"""
                    for node in nodes:
                        node_id = node.get('nodeId')
                        if node_id is not None:
                            node_id = int(node_id) if isinstance(node_id, str) else node_id
                            if parent_id is not None:
                                parent_map[node_id] = parent_id
                            # Process children
                            children = node.get('children', [])
                            if children:
                                build_parent_map(children, node_id)

                # Build the parent map from root_nodes
                root_nodes = org_setup.root_nodes
                if isinstance(root_nodes, list):
                    build_parent_map(root_nodes, None)
                
                # Also build a set of all nodeIds in the tree for quick lookup
                all_node_ids_in_tree = set()
                def collect_all_node_ids(nodes):
                    """Collect all nodeIds from the tree"""
                    for node in nodes:
                        node_id = node.get('nodeId')
                        if node_id is not None:
                            node_id = int(node_id) if isinstance(node_id, str) else node_id
                            all_node_ids_in_tree.add(node_id)
                        children = node.get('children', [])
                        if children:
                            collect_all_node_ids(children)
                
                if isinstance(root_nodes, list):
                    collect_all_node_ids(root_nodes)
                
                logger.info(f"Built parent_map with {len(parent_map)} entries for organization {organization_id}")
                logger.info(f"Total nodeIds in tree: {len(all_node_ids_in_tree)}")
                logger.info(f"Origin location IDs: {[loc.id for loc in origin_locations]}")
                logger.info(f"Origin IDs in tree: {[loc.id for loc in origin_locations if loc.id in all_node_ids_in_tree]}")

                def get_ancestors(loc_id, visited=None):
                    """Get list of ancestor names from root to parent (not including current node)"""
                    if visited is None:
                        visited = set()

                    # Prevent infinite loops
                    if loc_id in visited:
                        return []
                    visited.add(loc_id)

                    parent_id = parent_map.get(loc_id)
                    if parent_id is None:
                        # This is a root node or not in tree, return empty (no ancestors)
                        return []

                    # Get parent's ancestors recursively, then add parent
                    parent_ancestors = get_ancestors(parent_id, visited)
                    parent_name = location_names.get(parent_id, f"Location {parent_id}")
                    return parent_ancestors + [parent_name]

                # Build paths only for the origin locations
                for loc in origin_locations:
                    loc_id = int(loc.id)  # Ensure it's an integer
                    
                    # Check if location is in the tree
                    if loc_id not in all_node_ids_in_tree:
                        logger.warning(f"Location {loc_id} ({loc.display_name or loc.name_en or loc.name_th}) is not in organization tree structure")
                        location_paths[loc_id] = ''
                        continue
                    
                    ancestors = get_ancestors(loc_id)

                    if ancestors:
                        location_paths[loc_id] = ', '.join(ancestors)
                        logger.info(f"Built path for location {loc_id} ({loc.display_name or loc.name_en or loc.name_th}): {location_paths[loc_id]}")
                    else:
                        # Root node - no ancestors to show
                        location_paths[loc_id] = ''
                        logger.info(f"Location {loc_id} ({loc.display_name or loc.name_en or loc.name_th}) is a root node - no path")
            else:
                logger.warning(f"No organization setup or root_nodes found for organization {organization_id}")

            # Build districts list with paths (legacy/origin-only)
            districts = []
            origin_name_by_id = {}
            for loc in origin_locations:
                loc_id = int(loc.id)
                path = location_paths.get(loc_id, '')
                name = loc.name_en or loc.name_th or loc.display_name or str(loc.id)
                origin_name_by_id[loc_id] = name
                districts.append({
                    'id': str(loc.id),
                    'name': name,
                    'path': path
                })

            # Load tag and tenant names for composite filter labels
            tag_name_by_id = {}
            if tag_ids:
                tags = db_session.query(UserLocationTag).filter(
                    and_(
                        UserLocationTag.id.in_(tag_ids),
                        UserLocationTag.deleted_date.is_(None)
                    )
                ).all()
                tag_name_by_id = {t.id: (t.name or f"Tag {t.id}") for t in tags}

            tenant_name_by_id = {}
            if tenant_ids:
                tenants = db_session.query(UserTenant).filter(
                    and_(
                        UserTenant.id.in_(tenant_ids),
                        UserTenant.deleted_date.is_(None)
                    )
                ).all()
                tenant_name_by_id = {t.id: (t.name or f"Tenant {t.id}") for t in tenants}

            # Build options: location, location·tag, location·tenant, location·tag·tenant
            # Per origin: show all 4 types using tags/tenants that appear with that origin.
            # Only show location·tag·tenant when that exact combo exists in combos_result.
            combos_set = {(r[0], r[1], r[2]) for r in combos_result}
            seen_option_ids = set()
            for origin_id in origin_ids:
                origin_name = origin_name_by_id.get(origin_id, f"Location {origin_id}")
                path = location_paths.get(int(origin_id), '') if origin_id else ''
                origin_tag_ids = list(tags_by_origin.get(origin_id, []))
                origin_tenant_ids = list(tenants_by_origin.get(origin_id, []))
                # 1) Location only
                oid = f"{origin_id}||"
                if oid not in seen_option_ids:
                    seen_option_ids.add(oid)
                    origin_options.append({'id': oid, 'name': origin_name, 'path': path})
                # 2) Location · tag
                for tag_id in origin_tag_ids:
                    tname = tag_name_by_id.get(tag_id)
                    if tname:
                        oid = f"{origin_id}|{tag_id}|"
                        if oid not in seen_option_ids:
                            seen_option_ids.add(oid)
                            origin_options.append({'id': oid, 'name': f"{origin_name} · {tname}", 'path': path})
                # 3) Location · tenant
                for tenant_id in origin_tenant_ids:
                    tname = tenant_name_by_id.get(tenant_id)
                    if tname:
                        oid = f"{origin_id}||{tenant_id}"
                        if oid not in seen_option_ids:
                            seen_option_ids.add(oid)
                            origin_options.append({'id': oid, 'name': f"{origin_name} · {tname}", 'path': path})
                # 4) Location · tag · tenant - only when that combo exists in data
                for tag_id in origin_tag_ids:
                    for tenant_id in origin_tenant_ids:
                        if (origin_id, tag_id, tenant_id) in combos_set:
                            tname = tag_name_by_id.get(tag_id)
                            tnt = tenant_name_by_id.get(tenant_id)
                            if tname and tnt:
                                oid = f"{origin_id}|{tag_id}|{tenant_id}"
                                if oid not in seen_option_ids:
                                    seen_option_ids.add(oid)
                                    origin_options.append({
                                        'id': oid,
                                        'name': f"{origin_name} · {tname} · {tnt}",
                                        'path': path
                                    })

        # Status options
        statuses = [
            {'value': 'pending', 'label': 'รอดำเนินการ'},
            {'value': 'approved', 'label': 'อนุมัติ'},
            {'value': 'rejected', 'label': 'ไม่อนุมัติ'}
        ]

        # Material options: distinct material_id from transaction records (same org, non-deleted)
        material_ids = [
            row[0] for row in db_session.query(TransactionRecord.material_id)
            .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
            .filter(
                and_(
                    Transaction.organization_id == organization_id,
                    Transaction.deleted_date.is_(None),
                    TransactionRecord.is_active == True,
                    TransactionRecord.material_id.isnot(None)
                )
            ).distinct().all()
        ]
        materials_options = []
        if material_ids:
            materials = db_session.query(Material).filter(
                Material.id.in_(material_ids),
                Material.is_active == True
            ).all()
            materials_options = [
                {
                    'id': m.id,
                    'name': m.name_en or m.name_th or f"Material {m.id}",
                    'name_en': m.name_en or '',
                    'name_th': m.name_th or ''
                }
                for m in materials
            ]

        # Sort composite options by name (building 1, building 1 · tag, building 2, ...)
        origin_options_sorted = sorted(origin_options, key=lambda x: x['name'])

        filter_options = {
            'districts': origin_options_sorted,
            'statuses': statuses,
            'materials': materials_options
        }

        # Compile final report
        report = {
            'summary': {
                'total_transactions': total_transactions,
                'approved_count': approved_count,
                'rejected_count': rejected_count,
                'queued_count': queued_count,
                'approved_percentage': approved_percentage,
                'rejected_percentage': rejected_percentage,
                'queued_percentage': queued_percentage
            },
            'monthly_trends': monthly_trends,
            'rejection_breakdown': rejection_breakdown,
            'transactions': transaction_list,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'filters_applied': {
                'search': search,
                'date_from': date_from,
                'date_to': date_to,
                'district': district,
                'status': status
            },
            'filter_options': filter_options
        }

        logger.info(f"Successfully generated audit report with {total_transactions} total transactions (page {page}/{total_pages}, showing {len(transaction_list)} transactions)")

        return {
            'success': True,
            'message': 'Audit report generated successfully',
            'data': report
        }

    except Exception as e:
        logger.error(f"Error generating audit report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise APIException(f'Failed to generate audit report: {str(e)}')